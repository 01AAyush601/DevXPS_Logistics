import streamlit as st
import pandas as pd
import db_utils
import io
from datetime import datetime, timedelta

def app():
    # Page Config (Optional, but looks better)
    st.caption("🚀 Cloud Logistics System | v2.0")

    # --- SIDEBAR: IMPORT TOOLS ---
    with st.sidebar:
        st.header("📂 Import Center")
        
        # 1. TEMPLATE DOWNLOAD
        st.subheader("1. Get Template")
        template_data = {
            "Manifest No": [], "Manifest Date": [], "CN No": [], "CN Date": [],
            "Consignor": [], "Consignee": [], "Payment Liability": [], "No. of PKGS": [],
            "Type": [], "Actual WT": [], "Invoice No": [], "From": [], "To": [],
            "Sales Type": [], "Sales Amount (₹)": []
        }
        df_temp = pd.DataFrame(template_data)
        csv_temp = df_temp.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Excel Template", csv_temp, "Manifest_Template.csv", "text/csv")

        st.divider()

        # 2. FAST UPLOAD
        st.subheader("2. Upload Manifest")
        uploaded_file = st.file_uploader("Select CSV File", type=["csv"])
        
        if uploaded_file:
            # Load Data (Force Weight as String)
            df = pd.read_csv(uploaded_file, dtype={'Actual WT': str})
            st.toast(f"Loaded {len(df)} rows!", icon="📄")
            
            if st.button("🚀 Run Fast Import", type="primary"):
                try:
                    # Rename columns to match database
                    # (Mapping CSV Headers -> Database Columns)
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

                    # Clean Dates & Nulls
                    df['manifest_date'] = pd.to_datetime(df['manifest_date'], dayfirst=True).dt.date
                    df['cn_date'] = pd.to_datetime(df['cn_date'], dayfirst=True).dt.date
                    df = df.fillna("")

                    # --- FAST BATCH INSERT ---
                    progress_bar = st.progress(0)
                    chunk_size = 500
                    total_rows = len(df)
                    chunks = [df[i:i + chunk_size] for i in range(0, total_rows, chunk_size)]
                    
                    for i, chunk in enumerate(chunks):
                        placeholders = ",".join(["(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"] * len(chunk))
                        
                        # Note: We use 'logistics_entries' table
                        query = f"""
                            INSERT INTO logistics_entries (
                                manifest_no, manifest_date, cn_no, cn_date, 
                                consignor, consignee, payment_liability, 
                                no_of_pkgs, pkg_type, actual_wt, 
                                consignor_invoice_no, dispatch_from, dispatch_to, 
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
                                row['sales_type'], row['sales_amount'], 
                                st.session_state.username
                            ])

                        db_utils.run_query(query, tuple(flat_data))
                        progress_bar.progress(min((i + 1) * chunk_size, total_rows) / total_rows)

                    st.success(f"✅ Imported {total_rows} records successfully!")
                    st.balloons()
                    
                except Exception as e:
                    st.error(f"Import Failed: {e}")

    # --- MAIN SCREEN: EXCEL GRID VIEW ---
    st.title("🗄️ Logistics Master Register")

    # 1. Filters
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        search_query = st.text_input("🔍 Search (CN No, Party Name, etc.)", placeholder="Type to search...")
    with col2:
        start_date = st.date_input("From Date", datetime.now() - timedelta(days=30))
    with col3:
        end_date = st.date_input("To Date", datetime.now())

    # 2. Fetch Data
    try:
        if search_query:
            # Search mode
            query = f"""
                SELECT * FROM logistics_entries 
                WHERE cn_no ILIKE '%%{search_query}%%' 
                OR consignor ILIKE '%%{search_query}%%' 
                OR consignee ILIKE '%%{search_query}%%'
                ORDER BY cn_date DESC
            """
            df_main = db_utils.fetch_data(query)
        else:
            # Date Filter mode
            query = f"""
                SELECT * FROM logistics_entries 
                WHERE manifest_date >= '{start_date}' AND manifest_date <= '{end_date}'
                ORDER BY manifest_date DESC
            """
            df_main = db_utils.fetch_data(query)

        # 3. Display Data Editor (Excel Grid)
        if not df_main.empty:
            st.info(f"Showing {len(df_main)} records.")
            
            # Allow editing specific columns
            edited_df = st.data_editor(
                df_main,
                column_config={
                    "cn_no": st.column_config.TextColumn("CN No", disabled=True),
                    "sales_amount": st.column_config.NumberColumn("Sales Amount (₹)", format="₹%d"),
                    "actual_wt": "Weight",
                    "pkg_type": "Type"
                },
                disabled=["id", "created_at", "manifest_no"], # Protect ID columns
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic" # Allow adding/deleting rows if needed
            )

            # 4. Save Changes Button (Optional Feature)
            # (If you edit the grid, this detects changes. 
            #  Full update logic can be complex, so this is a view-first mode.)
            
            st.divider()
            
            # 5. Export Button
            if st.button("📊 Export to Excel"):
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    edited_df.to_excel(writer, index=False)
                st.download_button(
                    label="Download Excel",
                    data=output.getvalue(),
                    file_name=f"Logistics_Report_{datetime.now().date()}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

        else:
            st.warning("No records found. Try adjusting the filters or upload a file.")

    except Exception as e:
        st.error(f"Error loading data: {e}")
