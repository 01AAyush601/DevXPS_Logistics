import streamlit as st
import pandas as pd
import db_utils
from datetime import datetime, date
import io

# --- MAIN APP LOGIC ---
def app():
    db_utils.init_all_tables()

    st.title("🏢 Head Office (HO) Expense Register (Cloud ☁️)")

    # --- SIDEBAR: TOOLS ---
    with st.sidebar:
        st.header("1. Add/Edit Daily Entry")
        selected_date = st.date_input("Select Date", date.today())
        
        if st.button("📝 Create/Edit Entry"):
            date_str = selected_date.strftime('%Y-%m-%d')
            # Create row if missing (Postgres)
            conn = db_utils.get_db_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO ho_expenses (entry_date) VALUES (%s) ON CONFLICT DO NOTHING", (date_str,))
            conn.commit()
            cur.close()
            conn.close()
            st.success(f"Entry for {date_str} is ready.")

        st.divider()
        st.header("2. Add Expense Type")
        new_col = st.text_input("New Expense Name (e.g. Electricity)")
        if st.button("➕ Add Column"):
            if new_col:
                clean_name = new_col.strip().replace(" ", "_").lower()
                db_utils.add_column_if_not_exists("ho_expenses", clean_name)
                st.success(f"Added '{clean_name}'")
                st.rerun()

    # --- MAIN SCREEN ---
    st.header("Daily Expense Log")

    conn = db_utils.get_db_connection()
    if not conn: st.stop()

    col1, col2 = st.columns(2)
    start_date = col1.date_input("From Date", date(2025, 1, 1), key="ho_start")
    end_date = col2.date_input("To Date", date.today(), key="ho_end")

    query = f"SELECT * FROM ho_expenses WHERE entry_date >= '{start_date}' AND entry_date <= '{end_date}'"
    df_expenses = pd.read_sql(query, conn)
    conn.close()

    if not df_expenses.empty:
        non_expense_cols = ['entry_date', 'remarks']
        expense_cols = [c for c in df_expenses.columns if c not in non_expense_cols]
        
        df_expenses[expense_cols] = df_expenses[expense_cols].fillna(0)
        df_expenses['TOTAL_HO'] = df_expenses[expense_cols].sum(axis=1)
        
        display_cols = ['entry_date'] + expense_cols + ['TOTAL_HO', 'remarks']
        
        st.info(f"Showing {len(df_expenses)} entries.")
        edited_df = st.data_editor(
            df_expenses[display_cols],
            column_config={
                "entry_date": st.column_config.DateColumn("Date", disabled=True, format="DD-MM-YYYY"),
                "TOTAL_HO": st.column_config.NumberColumn("💰 Total", disabled=True, format="₹ %.2f"),
                "remarks": st.column_config.TextColumn("📝 Remarks", width="large"),
            },
            hide_index=True,
            use_container_width=True
        )
        
        if st.button("💾 Save Changes"):
            conn = db_utils.get_db_connection()
            cur = conn.cursor()
            
            save_cols = expense_cols + ['remarks']
            
            for index, row in edited_df.iterrows():
                d_str = row['entry_date'].strftime('%Y-%m-%d')
                set_clauses = [f'"{col}" = %s' for col in save_cols]
                sql = f"""
                    UPDATE ho_expenses 
                    SET {", ".join(set_clauses)}
                    WHERE entry_date = %s
                """
                values = [row[col] for col in save_cols]
                values.append(d_str)
                
                cur.execute(sql, values)
                
            conn.commit()
            cur.close()
            conn.close()
            st.success("Updated Successfully!")
            st.rerun()
            
        st.divider()
        if st.button("📊 Export to Excel"):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                edited_df.to_excel(writer, index=False)
            st.download_button("Download", output.getvalue(), "HO_Expenses_Cloud.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    else:
        st.warning("No entries found. Create one from the sidebar.")

if __name__ == "__main__":
    app()