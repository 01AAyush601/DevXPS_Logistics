import streamlit as st
import pandas as pd
import db_utils
import io
from datetime import datetime, timedelta

def app():
    st.set_page_config(layout="wide") # Use full screen width
    st.title("🗄️ Logistics Master Register")

    # --- SIDEBAR: IMPORT TOOLS ---
    with st.sidebar:
        st.header("📂 Import Center")
        st.caption("Use this to add new Manifests.")
        
        # 1. TEMPLATE
        df_temp = pd.DataFrame({"Manifest No": [], "Manifest Date": [], "CN No": [], "Sales Amount (₹)": [], "Actual WT": []})
        csv_temp = df_temp.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Get Template", csv_temp, "Template.csv", "text/csv")
        
        st.divider()

        # 2. UPLOAD
        uploaded_file = st.file_uploader("Upload CSV", type=["csv"])
        if uploaded_file and st.button("🚀 Run Import"):
            try:
                df = pd.read_csv(uploaded_file, dtype={'Actual WT': str})
                
                # Basic Rename & Clean
                df = df.rename(columns={
                    "Manifest No": "manifest_no", "Manifest Date": "manifest_date",
                    "CN No": "cn_no", "CN Date": "cn_date",
                    "Consignor": "consignor", "Consignee": "consignee",
                    "Payment Liability": "payment_liability", "No. of PKGS": "no_of_pkgs",
                    "Type": "pkg_type", "Actual WT": "actual_wt",
                    "Consignor Invoice No": "consignor_invoice_no",
                    "From": "dispatch_from", "To": "dispatch_to",
                    "Sales Type": "sales_type", "Sales Amount (₹)": "sales_amount"
                })
                df['manifest_date'] = pd.to_datetime(df['manifest_date'], dayfirst=True).dt.date
                df['cn_date'] = pd.to_datetime(df['cn_date'], dayfirst=True).dt.date
                df = df.fillna("")

                # Insert Loop
                progress = st.progress(0)
                chunk_size = 500
                chunks = [df[i:i + chunk_size] for i in range(0, len(df), chunk_size)]
                
                for i, chunk in enumerate(chunks):
                    placeholders = ",".join(["(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"] * len(chunk))
                    query = f"""
                        INSERT INTO logistics_entries (
                            manifest_no, manifest_date, cn_no, cn_date, consignor, consignee, payment_liability, 
                            no_of_pkgs, pkg_type, actual_wt, consignor_invoice_no, dispatch_from, dispatch_to, 
                            sales_type, sales_amount, created_by
                        ) VALUES {placeholders}
                    """
                    flat_data = []
                    for _, row in chunk.iterrows():
                        flat_data.extend([
                            row['manifest_no'], row['manifest_date'], row['cn_no'], row['cn_date'],
                            row['consignor'], row['consignee'], row['payment_liability'],
                            row['no_of_pkgs'], row['pkg_type'], str(row['actual_wt']),
                            row['consignor_invoice_no'], row['dispatch_from'], row['dispatch_to'],
                            row['sales_type'], row['sales_amount'], st.session_state.username
                        ])
                    db_utils.run_query(query, tuple(flat_data))
                    progress.progress(min((i + 1) * chunk_size, len(df)) / len(df))
                
                st.success("Import Complete!")
            except Exception as e:
                st.error(f"Error: {e}")

    # --- MAIN SCREEN: REGISTER & RECONCILIATION ---

    # 1. Filters
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        search_query = st.text_input("🔍 Search (CN No, Party Name)", placeholder="Type CN No...")
    with col2:
        start_date = st.date_input("From Date", datetime.now() - timedelta(days=30))
    with col3:
        end_date = st.date_input("To Date", datetime.now())

    # 2. Fetch Data
    try:
        if search_query:
            query = f"SELECT * FROM logistics_entries WHERE cn_no ILIKE '%%{search_query}%%' OR consignor ILIKE '%%{search_query}%%' ORDER BY cn_date DESC"
        else:
            query = f"SELECT * FROM logistics_entries WHERE manifest_date >= '{start_date}' AND manifest_date <= '{end_date}' ORDER BY manifest_date DESC"
        
        df_main = db_utils.fetch_data(query)

        if not df_main.empty:
            # --- CALCULATIONS (The Math You Requested) ---
            df_main['sales_amount'] = pd.to_numeric(df_main['sales_amount'], errors='coerce').fillna(0)
            df_main['manual_figures'] = pd.to_numeric(df_main['manual_figures'], errors='coerce').fillna(0)

            # Logic:
            # Discount = Sales - Manual (if Manual is paid but less than Sales)
            # Excess = Manual - Sales (if Manual is more than Sales)
            # Due = Sales (if Manual is 0)
            
            df_main['Discount'] = df_main.apply(lambda x: x['sales_amount'] - x['manual_figures'] 
                                                if (0 < x['manual_figures'] < x['sales_amount']) else 0, axis=1)
            
            df_main['Excess'] = df_main.apply(lambda x: x['manual_figures'] - x['sales_amount'] 
                                              if x['manual_figures'] > x['sales_amount'] else 0, axis=1)
            
            df_main['Due Amount'] = df_main.apply(lambda x: x['sales_amount'] 
                                                  if x['manual_figures'] == 0 else 0, axis=1)

            # Reorder Columns for better view
            cols_to_show = [
                "cn_no", "manifest_date", "consignor", "consignee", "actual_wt", 
                "sales_amount", "manual_figures", "remarks", 
                "Discount", "Excess", "Due Amount"
            ]
            # Keep other columns hidden in valid_df but available
            df_display = df_main[cols_to_show].copy()

            # 3. Data Editor
            st.info(f"Showing {len(df_main)} records.")
            
            edited_df = st.data_editor(
                df_display,
                column_config={
                    "cn_no": st.column_config.TextColumn("CN No", disabled=True),
                    "sales_amount": st.column_config.NumberColumn("Bill Amount (₹)", disabled=True),
                    "manual_figures": st.column_config.NumberColumn("✅ Manual Recvd (₹)", required=True),
                    "remarks": st.column_config.TextColumn("✍️ Remarks"),
                    "Discount": st.column_config.NumberColumn("Discount", disabled=True),
                    "Excess": st.column_config.NumberColumn("Excess", disabled=True),
                    "Due Amount": st.column_config.NumberColumn("Due", disabled=True),
                },
                disabled=["cn_no", "manifest_date", "consignor", "consignee", "actual_wt", "sales_amount", "Discount", "Excess", "Due Amount"],
                use_container_width=True,
                hide_index=True,
                height=500
            )

            # 4. SAVE CHANGES BUTTON
            st.write("###")
            if st.button("💾 Save Changes to Cloud", type="primary"):
                # We compare edited_df with df_main to find changes in 'manual_figures' or 'remarks'
                # For simplicity, we can just update all displayed rows (or optimize to only changed ones)
                
                progress = st.progress(0)
                total = len(edited_df)
                
                for index, row in edited_df.iterrows():
                    # Only update if manual figures or remarks exist
                    cn = row['cn_no']
                    man_fig = row['manual_figures']
                    rem = row['remarks']
                    
                    # Update Query
                    upd_query = f"""
                        UPDATE logistics_entries 
                        SET manual_figures = {man_fig}, remarks = '{rem}'
                        WHERE cn_no = '{cn}'
                    """
                    # Note: Ideally use parameterized queries, but this is safe for numeric/internal loop
                    db_utils.run_query("UPDATE logistics_entries SET manual_figures = %s, remarks = %s WHERE cn_no = %s", (man_fig, rem, cn))
                    
                    progress.progress((index + 1) / total)
                
                st.success("✅ Database Updated Successfully!")
                st.rerun()

        else:
            st.warning("No records found.")

    except Exception as e:
        st.error(f"Error: {e}")

if __name__ == "__main__":
    app()
