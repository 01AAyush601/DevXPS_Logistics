import streamlit as st
import pandas as pd
import db_utils
from datetime import datetime, timedelta

def app():
    st.set_page_config(layout="wide", page_title="Logistics Pro")
    st.title("🗄️ Logistics Master Register")

    # --- SIDEBAR: ALL IMPORT TOOLS ---
    with st.sidebar:
        st.header("🛠️ Tools Menu")
        
        # --- TOOL 1: NEW IMPORT ---
        with st.expander("📂 1. Import New Manifest", expanded=False):
            st.caption("Add NEW shipments from Excel.")
            
            # Template
            df_new = pd.DataFrame({"Manifest No": [], "Manifest Date": [], "CN No": [], "Sales Amount (₹)": [], "Actual WT": []})
            st.download_button("📥 Get Import Template", df_new.to_csv(index=False).encode('utf-8'), "New_Manifest_Template.csv", "text/csv")
            
            # Upload
            new_file = st.file_uploader("Upload Manifest CSV", type=["csv"], key="new_upload")
            if new_file and st.button("🚀 Run Import"):
                try:
                    df = pd.read_csv(new_file, dtype={'Actual WT': str})
                    # Rename & Clean
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

                    # Batch Insert
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
                            ON CONFLICT DO NOTHING; -- Prevents crashing if CN exists
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
                    st.rerun()
                except Exception as e:
                    st.error(f"Import Error: {e}")

        # --- TOOL 2: BULK UPDATE (This is what you asked for) ---
        with st.expander("⚡ 2. Bulk Update (Manual/Sales)", expanded=True):
            st.caption("Update Manual Recvd, Remarks, or Fix Sales Amount using CN No.")
            
            # Template for Update
            df_upd = pd.DataFrame({"CN No": [], "Manual Recvd": [], "Sales Amount": [], "Remarks": []})
            st.download_button("📥 Get Update Template", df_upd.to_csv(index=False).encode('utf-8'), "Update_Template.csv", "text/csv")
            
            # Upload Update File
            update_file = st.file_uploader("Upload Update CSV", type=["csv"], key="update_upload")
            
            if update_file and st.button("🔄 Start Bulk Update"):
                try:
                    df_u = pd.read_csv(update_file)
                    
                    # Progress Bar
                    prog_bar = st.progress(0)
                    total_rows = len(df_u)
                    
                    for index, row in df_u.iterrows():
                        cn = str(row['CN No'])
                        
                        # Build Dynamic Update Query
                        updates = []
                        params = []
                        
                        # Only update columns that have values (not empty)
                        if 'Manual Recvd' in row and pd.notna(row['Manual Recvd']):
                            updates.append("manual_figures = %s")
                            params.append(float(row['Manual Recvd']))
                            
                        if 'Sales Amount' in row and pd.notna(row['Sales Amount']):
                            updates.append("sales_amount = %s")
                            params.append(float(row['Sales Amount']))
                            
                        if 'Remarks' in row and pd.notna(row['Remarks']):
                            updates.append("remarks = %s")
                            params.append(str(row['Remarks']))

                        if updates:
                            # Add CN to params for the WHERE clause
                            params.append(cn)
                            
                            sql = f"UPDATE logistics_entries SET {', '.join(updates)} WHERE cn_no = %s"
                            db_utils.run_query(sql, tuple(params))
                        
                        prog_bar.progress((index + 1) / total_rows)
                        
                    st.success(f"✅ Successfully updated {total_rows} records!")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"Update Error: {e}")

    # --- MAIN SCREEN: REGISTER GRID ---

    # 1. Search & Filter
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        search_query = st.text_input("🔍 Search (CN No, Party Name)", placeholder="Enter CN No...")
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
            # --- CALCULATIONS ---
            df_main['sales_amount'] = pd.to_numeric(df_main['sales_amount'], errors='coerce').fillna(0)
            df_main['manual_figures'] = pd.to_numeric(df_main['manual_figures'], errors='coerce').fillna(0)

            # Auto-Calculate Logic
            df_main['Discount'] = df_main.apply(lambda x: x['sales_amount'] - x['manual_figures'] 
                                                if (0 < x['manual_figures'] < x['sales_amount']) else 0, axis=1)
            
            df_main['Excess'] = df_main.apply(lambda x: x['manual_figures'] - x['sales_amount'] 
                                              if x['manual_figures'] > x['sales_amount'] else 0, axis=1)
            
            df_main['Due Amount'] = df_main.apply(lambda x: x['sales_amount'] 
                                                  if x['manual_figures'] == 0 else 0, axis=1)

            # Display Columns
            cols_to_show = [
                "cn_no", "manifest_date", "consignor", "consignee", "actual_wt", 
                "sales_amount", "manual_figures", "remarks", 
                "Discount", "Excess", "Due Amount"
            ]
            df_display = df_main[cols_to_show].copy()

            # 3. Interactive Grid
            st.info(f"Showing {len(df_main)} records.")
            
            edited_df = st.data_editor(
                df_display,
                column_config={
                    "cn_no": st.column_config.TextColumn("CN No", disabled=True),
                    "sales_amount": st.column_config.NumberColumn("Bill Amount (₹)", disabled=False), # Editable in Grid too!
                    "manual_figures": st.column_config.NumberColumn("✅ Manual Recvd (₹)", required=True),
                    "remarks": st.column_config.TextColumn("✍️ Remarks"),
                    "Discount": st.column_config.NumberColumn("Discount", disabled=True),
                    "Excess": st.column_config.NumberColumn("Excess", disabled=True),
                    "Due Amount": st.column_config.NumberColumn("Due", disabled=True),
                },
                disabled=["cn_no", "manifest_date", "consignor", "consignee", "actual_wt", "Discount", "Excess", "Due Amount"],
                use_container_width=True,
                hide_index=True,
                height=600
            )

            # 4. Save Grid Changes Button
            st.write("###")
            if st.button("💾 Save Grid Changes", type="primary"):
                progress = st.progress(0)
                total = len(edited_df)
                
                for index, row in edited_df.iterrows():
                    cn = row['cn_no']
                    man_fig = row['manual_figures']
                    sales_fig = row['sales_amount']
                    rem = row['remarks']
                    
                    # Update both Manual AND Sales Amount (if edited in grid)
                    db_utils.run_query(
                        "UPDATE logistics_entries SET manual_figures = %s, sales_amount = %s, remarks = %s WHERE cn_no = %s", 
                        (man_fig, sales_fig, rem, cn)
                    )
                    progress.progress((index + 1) / total)
                
                st.success("✅ Updates Saved!")
                st.rerun()

        else:
            st.warning("No records found.")

    except Exception as e:
        st.error(f"Error loading data: {e}")

if __name__ == "__main__":
    app()
