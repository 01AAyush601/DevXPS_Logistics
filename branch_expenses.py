import streamlit as st
import pandas as pd
import db_utils  # <--- Cloud Manager
from datetime import datetime
import io

# --- MAIN APP LOGIC ---
def app():
    # Ensure tables exist
    db_utils.init_all_tables()

    st.title("💰 Branch Expense Manager (Cloud ☁️)")

    # --- SIDEBAR: TOOLS ---
    with st.sidebar:
        st.header("1. Import Manifests")
        st.info("Note: This will UPDATE/OVERWRITE existing records if the Manifest No matches.")
        
        # --- TEMPLATE DOWNLOAD ---
        # Get current columns from Cloud DB
        conn = db_utils.get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM branch_expenses LIMIT 0")
            db_cols = [desc[0] for desc in cur.description]
            conn.close()
        else:
            db_cols = []

        col_mapping = {
            "manifest_no": "Manifest No",
            "manifest_date": "Manifest Date",
            "origin": "From",
            "destination": "To",
            "remarks": "Remarks"
        }
        
        template_headers = {}
        for col in db_cols:
            if col in col_mapping:
                template_headers[col_mapping[col]] = []
            else:
                template_headers[col.capitalize()] = []

        df_template = pd.DataFrame(template_headers)
        csv_template = df_template.to_csv(index=False).encode('utf-8')
        
        st.download_button("📥 Get Template", csv_template, "Expense_Template.csv", "text/csv")
        st.divider()

        # --- UPLOAD SECTION ---
        uploaded_file = st.file_uploader("Upload Manifest CSV", type=["csv"], key="expense_upload")
        
        if uploaded_file:
            if st.button("🚀 Import & Update"):
                try:
                    df = pd.read_csv(uploaded_file)
                    
                    standard_map = {
                        "Manifest No": "manifest_no", "Manifest Date": "manifest_date",
                        "From": "origin", "To": "destination", "Remarks": "remarks"
                    }
                    
                    conn = db_utils.get_db_connection()
                    cur = conn.cursor()
                    rows_processed = 0
                    
                    # Get valid DB columns again to be safe
                    cur.execute("SELECT * FROM branch_expenses LIMIT 0")
                    valid_db_cols = [desc[0] for desc in cur.description]
                    
                    for _, row in df.iterrows():
                        row_data = {}
                        
                        # 1. Process Standard Columns
                        for csv_header, db_col in standard_map.items():
                            if csv_header in df.columns:
                                val = row[csv_header]
                                if db_col == 'manifest_date':
                                    val = pd.to_datetime(val, dayfirst=True, errors='coerce')
                                    val = val.strftime('%Y-%m-%d') if pd.notna(val) else None
                                row_data[db_col] = val
                        
                        # 2. Process Expense Columns
                        for col in valid_db_cols:
                            if col not in standard_map.values():
                                csv_match = next((h for h in df.columns if h.strip().lower() == col.lower()), None)
                                if csv_match:
                                    val = row[csv_match]
                                    try:
                                        val = float(val) if pd.notna(val) else 0
                                    except:
                                        val = 0
                                    row_data[col] = val
                                else:
                                    row_data[col] = 0

                        # 3. Construct SQL (Postgres Syntax)
                        cols = list(row_data.keys())
                        vals = list(row_data.values())
                        
                        col_names = ", ".join([f'"{c}"' for c in cols])
                        placeholders = ", ".join(["%s"] * len(cols))
                        
                        # Construct UPDATE clause for conflict
                        update_clause = ", ".join([f'"{c}" = EXCLUDED."{c}"' for c in cols if c != 'manifest_no'])
                        
                        sql = f"""
                            INSERT INTO branch_expenses ({col_names})
                            VALUES ({placeholders})
                            ON CONFLICT (manifest_no) 
                            DO UPDATE SET {update_clause};
                        """
                        
                        cur.execute(sql, vals)
                        rows_processed += 1
                    
                    conn.commit()
                    cur.close()
                    conn.close()
                    st.success(f"Success! Processed {rows_processed} records.")
                
                except Exception as e:
                    st.error(f"Import Error: {e}")

        st.divider()
        
        # --- DYNAMIC COLUMN ADDER ---
        st.header("2. Add Expense Type")
        new_col = st.text_input("New Expense Name (e.g. Tea)")
        if st.button("➕ Add Column"):
            if new_col:
                clean_name = new_col.strip().replace(" ", "_").lower()
                db_utils.add_column_if_not_exists("branch_expenses", clean_name)
                st.success(f"Added '{clean_name}'")
                st.rerun()

    # --- MAIN SCREEN ---
    st.header("Expense Entry Register")

    # 1. Load Data
    conn = db_utils.get_db_connection()
    if not conn: st.stop()
    
    col1, col2 = st.columns(2)
    start_date = col1.date_input("From Date", datetime(2025, 1, 1), key="exp_start")
    end_date = col2.date_input("To Date", datetime.now(), key="exp_end")

    query = f"SELECT * FROM branch_expenses WHERE manifest_date >= '{start_date}' AND manifest_date <= '{end_date}'"
    df_expenses = pd.read_sql(query, conn)
    conn.close()

    if not df_expenses.empty:
        # 2. Identify Expense Columns
        info_cols = ['manifest_no', 'manifest_date', 'origin', 'destination', 'remarks']
        expense_cols = [c for c in df_expenses.columns if c not in info_cols]
        
        # 3. Calculate TOTAL
        df_expenses[expense_cols] = df_expenses[expense_cols].fillna(0)
        df_expenses['TOTAL_EXPENSE'] = df_expenses[expense_cols].sum(axis=1)
        
        # Reorder
        display_cols = ['manifest_no', 'manifest_date', 'origin', 'destination'] + expense_cols + ['TOTAL_EXPENSE', 'remarks']
        
        # 4. Editor
        st.info(f"Showing {len(df_expenses)} records.")
        edited_df = st.data_editor(
            df_expenses[display_cols],
            column_config={
                "manifest_no": st.column_config.TextColumn("Manifest No", disabled=True),
                "TOTAL_EXPENSE": st.column_config.NumberColumn("💰 Total", disabled=True, format="₹ %.2f"),
                "remarks": st.column_config.TextColumn("📝 Remarks", width="large"),
            },
            hide_index=True,
            use_container_width=True
        )
        
        # 5. Save Changes
        if st.button("💾 Save Expenses"):
            conn = db_utils.get_db_connection()
            cur = conn.cursor()
            
            save_cols = expense_cols + ['remarks']
            
            for index, row in edited_df.iterrows():
                set_clauses = [f'"{col}" = %s' for col in save_cols]
                sql = f"""
                    UPDATE branch_expenses 
                    SET {", ".join(set_clauses)}
                    WHERE manifest_no = %s
                """
                values = [row[col] for col in save_cols]
                values.append(row['manifest_no'])
                
                cur.execute(sql, values)
                
            conn.commit()
            cur.close()
            conn.close()
            st.success("Updated Successfully!")
            st.rerun()
            
        # 6. Export
        st.divider()
        if st.button("📊 Export to Excel"):
            file_name = f"Branch_Expenses_Cloud.xlsx"
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                edited_df.to_excel(writer, index=False)
            st.download_button("Download", output.getvalue(), file_name, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.warning("No records found in Cloud DB.")

if __name__ == "__main__":
    app()