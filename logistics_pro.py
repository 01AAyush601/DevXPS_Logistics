import streamlit as st
import pandas as pd
import db_utils  # <--- NEW: Import the Cloud Manager
from datetime import datetime
import io

# --- MAIN APP LOGIC ---
def app():
    # 1. Initialize Cloud Tables (Runs once)
    db_utils.init_all_tables()

    st.title("🗄️ Logistics Master Register (Cloud ☁️)")

    # --- SIDEBAR: ALL TOOLS ---
    with st.sidebar:
        st.header("1. New Manifest Import")
        st.caption("Use this to add NEW shipments. (Existing CNs are skipped).")
        
        # --- TEMPLATE DOWNLOAD ---
        template_data = {
            "Manifest No": [], "Manifest Date": [], "CN No": [], "CN Date": [],
            "Consignor": [], "Consignee": [], "Payment Liability": [], "No. of PKGS": [],
            "Type": [], "Actual WT": [], "Consignor Invoice No": [], "From": [], "To": [],
            "Sales Type": [], "Sales Amount (₹)": []
        }
        df_template = pd.DataFrame(template_data)
        csv_template = df_template.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Get Manifest Template",
            data=csv_template,
            file_name="Manifest_Import_Template.csv",
            mime="text/csv"
        )
        
        # --- IMPORT MANIFEST ---
        uploaded_file = st.file_uploader("Upload Manifest CSV", type=["csv"], key="manifest_upload")
        
        if uploaded_file:
            if st.button("🚀 Import Manifest"):
                try:
                    df = pd.read_csv(uploaded_file)
                    
                    # Auto-Correct Headers
                    if "Type" not in df.columns and "Sales Type.1" in df.columns:
                        df = df.rename(columns={"Sales Type": "Type", "Sales Type.1": "Sales Type"})
                    
                    column_map = {
                        "Manifest No": "manifest_no", "Manifest Date": "manifest_date",
                        "CN No": "cn_no", "CN Date": "cn_date",
                        "Consignor": "consignor", "Consignee": "consignee",
                        "Payment Liability": "payment_liability", "No. of PKGS": "pkgs",
                        "Type": "type", "Actual WT": "actual_wt",
                        "Consignor Invoice No": "invoice_no", "From": "origin",
                        "To": "destination", "Sales Type": "sales_type",
                        "Sales Amount (₹)": "sales_amount"
                    }
                    
                    df.columns = [c.strip() for c in df.columns] 
                    df_renamed = df.rename(columns=column_map)
                    
                    # Date Cleaning
                    for d_col in ['manifest_date', 'cn_date']:
                        if d_col in df_renamed.columns:
                            df_renamed[d_col] = pd.to_datetime(df_renamed[d_col], dayfirst=True, errors='coerce')

                    # Connect to Cloud
                    conn = db_utils.get_db_connection()
                    cur = conn.cursor()
                    
                    rows_added = 0
                    for _, row in df_renamed.iterrows():
                        m_val = row.get('manifest_date')
                        m_date = m_val.strftime('%Y-%m-%d') if pd.notna(m_val) else None

                        c_val = row.get('cn_date')
                        c_date = c_val.strftime('%Y-%m-%d') if pd.notna(c_val) else None

                        # POSTGRES SQL SYNTAX
                        sql = """
                            INSERT INTO master_data 
                            (cn_no, manifest_no, manifest_date, cn_date, consignor, consignee, payment_liability, 
                             pkgs, type, actual_wt, invoice_no, origin, destination, sales_type, sales_amount)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (cn_no) DO NOTHING;
                        """
                        
                        data_tuple = (
                            str(row.get('cn_no', '')), str(row.get('manifest_no', '')), 
                            m_date, c_date,
                            str(row.get('consignor', '')), str(row.get('consignee', '')),
                            str(row.get('payment_liability', '')), row.get('pkgs', 0),
                            str(row.get('type', '')), row.get('actual_wt', 0),
                            str(row.get('invoice_no', '')), str(row.get('origin', '')),
                            str(row.get('destination', '')), str(row.get('sales_type', '')),
                            row.get('sales_amount', 0)
                        )
                        
                        cur.execute(sql, data_tuple)
                        if cur.statusmessage == "INSERT 0 1": # Postgres confirmation
                            rows_added += 1
                    
                    conn.commit()
                    cur.close()
                    conn.close()
                    st.success(f"Success! {rows_added} NEW records added to Cloud.")
                except Exception as e:
                    st.error(f"Import Failed: {e}")

        st.divider()

        # --- SECTION 2: BULK UPDATE ---
        st.header("2. Bulk Update Manual Data")
        
        # Update Template
        update_template_data = {"CN No": [], "Manual Figures": [], "Remarks": []}
        csv_update_temp = pd.DataFrame(update_template_data).to_csv(index=False).encode('utf-8')
        st.download_button("📥 Get Update Template", csv_update_temp, "Bulk_Update_Template.csv", "text/csv")

        update_file = st.file_uploader("Upload Update CSV", type=["csv"], key="update_upload")
        
        if update_file:
            if st.button("⚡ Update Database"):
                try:
                    df_up = pd.read_csv(update_file)
                    conn = db_utils.get_db_connection()
                    cur = conn.cursor()
                    updated_count = 0
                    
                    for _, row in df_up.iterrows():
                        cn = str(row['CN No'])
                        man_fig = row['Manual Figures'] if pd.notna(row['Manual Figures']) else 0
                        rem = row['Remarks'] if pd.notna(row['Remarks']) else ""

                        # POSTGRES UPDATE SYNTAX
                        cur.execute("""
                            UPDATE master_data 
                            SET manual_figures = %s, remarks = %s 
                            WHERE cn_no = %s
                        """, (man_fig, rem, cn))
                        
                        # Check if row was actually updated
                        if cur.rowcount > 0:
                            updated_count += 1
                    
                    conn.commit()
                    cur.close()
                    conn.close()
                    
                    if updated_count > 0:
                        st.success(f"Successfully updated {updated_count} records!")
                    else:
                        st.warning("No records matched.")
                        
                except Exception as e:
                    st.error(f"Update Failed: {e}")

        # --- DELETE SECTION ---
        st.divider()
        st.header("⚠️ Danger Zone")
        with st.expander("Delete Options"):
            del_cn = st.text_input("Delete CN No")
            if st.button("🗑️ Delete Single"):
                if del_cn:
                    conn = db_utils.get_db_connection()
                    cur = conn.cursor()
                    cur.execute("DELETE FROM master_data WHERE cn_no = %s", (del_cn,))
                    conn.commit()
                    cur.close()
                    conn.close()
                    st.success(f"Deleted {del_cn}")
                    st.rerun()

    # --- MAIN SCREEN ---
    st.header("2. Search & Edit Records")
    search_query = st.text_input("🔍 Quick Search by CN No", "")

    # LOAD DATA FROM CLOUD
    conn = db_utils.get_db_connection()
    if not conn: st.stop()

    if search_query:
        query = f"SELECT * FROM master_data WHERE cn_no ILIKE '%%{search_query}%%'" # ILIKE is case-insensitive in Postgres
    else:
        col1, col2 = st.columns(2)
        with col1: start_filter = st.date_input("From Date", datetime(2025, 1, 1))
        with col2: end_filter = st.date_input("To Date", datetime.now())
        
        query = f"SELECT * FROM master_data WHERE manifest_date >= '{start_filter}' AND manifest_date <= '{end_filter}'"

    df_master = pd.read_sql(query, conn)
    conn.close()

    if not df_master.empty:
        # Fill NA for calculation
        df_master['sales_amount'] = df_master['sales_amount'].fillna(0)
        df_master['manual_figures'] = df_master['manual_figures'].fillna(0)
        
        # Calculate Logic
        df_master['Discount'] = df_master.apply(lambda x: x['sales_amount'] - x['manual_figures'] 
                                                if (0 < x['manual_figures'] < x['sales_amount']) else 0, axis=1)
        df_master['Excess'] = df_master.apply(lambda x: x['manual_figures'] - x['sales_amount'] 
                                            if x['manual_figures'] > x['sales_amount'] else 0, axis=1)
        df_master['Due from Party'] = df_master.apply(lambda x: x['sales_amount'] 
                                                    if x['manual_figures'] == 0 else 0, axis=1)

        st.info(f"Records Found: {len(df_master)}")
        
        edited_df = st.data_editor(
            df_master,
            column_config={
                "cn_no": st.column_config.TextColumn("CN No", disabled=True),
                "manifest_no": st.column_config.TextColumn("Manifest No", disabled=True),
                "manual_figures": st.column_config.NumberColumn("Manual Recvd (₹)", required=True),
                "remarks": st.column_config.TextColumn("Remarks", width="large"),
            },
            disabled=["manifest_date", "consignor", "consignee", "Discount", "Excess", "Due from Party"],
            hide_index=True,
            use_container_width=True
        )

        if st.button("💾 Update Cloud Database"):
            conn = db_utils.get_db_connection()
            cur = conn.cursor()
            for index, row in edited_df.iterrows():
                cur.execute("""
                    UPDATE master_data 
                    SET manual_figures = %s, remarks = %s
                    WHERE cn_no = %s
                """, (row['manual_figures'], row['remarks'], row['cn_no']))
            conn.commit()
            cur.close()
            conn.close()
            st.success("Cloud Database Updated!")
            st.rerun()

        st.divider()
        if st.button("📊 Download Excel Report"):
            file_name = f"Cloud_Report_Export.xlsx"
            export_df = edited_df.drop(columns=['manifest_date', 'cn_date'], errors='ignore')
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                export_df.to_excel(writer, index=False)
            st.download_button("Download Now", data=output.getvalue(), file_name=file_name, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.warning("No records found in Cloud Database.")

if __name__ == "__main__":
    app()