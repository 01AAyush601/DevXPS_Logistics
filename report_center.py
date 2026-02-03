import streamlit as st
import pandas as pd
import db_utils  # <--- Cloud Manager
import io
from datetime import datetime, date, timedelta

# --- 1. SAFE IMPORT FOR PLOTLY ---
try:
    import plotly.express as px
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

# --- 2. HELPER FUNCTIONS (Cloud) ---

def get_parent_map():
    conn = db_utils.get_db_connection()
    if not conn: return {}
    try:
        df = pd.read_sql("SELECT child_branch, parent_branch FROM branch_mappings", conn)
        conn.close()
        if not df.empty:
            return dict(zip(df['child_branch'], df['parent_branch']))
        return {}
    except Exception:
        if conn: conn.close()
        return {}

def add_mapping(child, parent):
    child = child.strip().upper()
    parent = parent.strip().upper()
    if not child or not parent: return False
    
    conn = db_utils.get_db_connection()
    if not conn: return False
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO branch_mappings (child_branch, parent_branch) 
            VALUES (%s, %s)
            ON CONFLICT (child_branch) 
            DO UPDATE SET parent_branch = EXCLUDED.parent_branch
        """, (child, parent))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error saving setting: {e}")
        return False

def delete_mapping(child):
    conn = db_utils.get_db_connection()
    if not conn: return
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM branch_mappings WHERE child_branch = %s", (child,))
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass

def load_data(start, end):
    conn = db_utils.get_db_connection()
    if not conn: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    try:
        # 1. Logistics Data
        q_log = f"SELECT * FROM master_data WHERE manifest_date >= '{start}' AND manifest_date <= '{end}'"
        df_log = pd.read_sql(q_log, conn)
        
        # 2. Branch Expenses
        q_branch = f"SELECT * FROM branch_expenses WHERE manifest_date >= '{start}' AND manifest_date <= '{end}'"
        df_branch = pd.read_sql(q_branch, conn)
        
        # 3. HO Expenses
        q_ho = f"SELECT * FROM ho_expenses WHERE entry_date >= '{start}' AND entry_date <= '{end}'"
        df_ho = pd.read_sql(q_ho, conn)
        
        conn.close()
        
        # --- PRE-PROCESSING ---
        if not df_log.empty:
            df_log['manifest_date'] = pd.to_datetime(df_log['manifest_date'])
            if 'cn_date' in df_log.columns: df_log['cn_date'] = pd.to_datetime(df_log['cn_date'])
            df_log['sales_amount'] = pd.to_numeric(df_log['sales_amount'], errors='coerce').fillna(0)
            df_log['manual_figures'] = pd.to_numeric(df_log['manual_figures'], errors='coerce').fillna(0)
            if 'sales_type' in df_log.columns:
                df_log['sales_type'] = df_log['sales_type'].astype(str).str.strip().str.upper()

        if not df_branch.empty:
            df_branch['manifest_date'] = pd.to_datetime(df_branch['manifest_date'])
            info_cols = ['manifest_no', 'manifest_date', 'origin', 'destination', 'remarks']
            exp_cols = [c for c in df_branch.columns if c not in info_cols]
            
            rent_col = next((c for c in exp_cols if c.lower() == 'rent'), None)
            vehicle_col = next((c for c in exp_cols if c.lower() == 'vehicle'), None)
            
            df_branch[exp_cols] = df_branch[exp_cols].apply(pd.to_numeric, errors='coerce').fillna(0)
            
            df_branch['Total_Rent'] = df_branch[rent_col] if rent_col else 0
            df_branch['Total_Vehicle'] = df_branch[vehicle_col] if vehicle_col else 0
            
            other_cols = [c for c in exp_cols if c not in [rent_col, vehicle_col]]
            df_branch['Total_Other_Exp'] = df_branch[other_cols].sum(axis=1)
            
            real_exp_cols = [c for c in exp_cols if 'transfer' not in c.lower()]
            transfer_cols = [c for c in exp_cols if 'transfer' in c.lower()]
            
            df_branch['Total_Real_Exp'] = df_branch[real_exp_cols].sum(axis=1)
            df_branch['Total_Transfer_HO'] = df_branch[transfer_cols].sum(axis=1) if transfer_cols else 0

        if not df_ho.empty:
            df_ho['entry_date'] = pd.to_datetime(df_ho['entry_date'])
            info_cols_ho = ['entry_date', 'remarks']
            exp_cols_ho = [c for c in df_ho.columns if c not in info_cols_ho]
            
            df_ho[exp_cols_ho] = df_ho[exp_cols_ho].apply(pd.to_numeric, errors='coerce').fillna(0)
            df_ho['Total_HO_Exp'] = df_ho[exp_cols_ho].sum(axis=1)

        return df_log, df_branch, df_ho

    except Exception as e:
        st.error(f"Data Load Error: {e}")
        if conn: conn.close()
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

# --- 3. REPORT GENERATION ---

def generate_report_1(df_log, df_branch, df_ho):
    HO_NAME = "Patna Jamal Road (HO)"
    PARENT_MAP = get_parent_map() 

    if df_log.empty: return pd.DataFrame()
    df = df_log.copy()
    
    name_map = {
        'PATNA (JAMAL ROAD)': HO_NAME, 'Patna (Jamal Road)': HO_NAME, 'PATNA JAMAL ROAD': HO_NAME,
        'Madhubani': 'MADHUBANI', 'Darbhanga': 'DARBHANGA', 'Motihari': 'MOTIHARI', 'Raxaul': 'RAXAUL'
    }
    if 'destination' in df.columns:
        df['destination'] = df['destination'].str.strip().replace(name_map)
    if not df_branch.empty and 'destination' in df_branch.columns:
         df_branch['destination'] = df_branch['destination'].str.strip().replace(name_map)

    def get_receipt_loc(row):
        return HO_NAME if row['sales_type'] in ['PAID', 'BILLED', 'TO BE BILLED'] else (row['destination'] if row['destination'] else "Unknown")
    df['Receipt_Loc'] = df.apply(get_receipt_loc, axis=1)
    
    df['Discount'] = df.apply(lambda x: (x['sales_amount'] - x['manual_figures']) if (x['manual_figures'] > 0 and x['manual_figures'] < x['sales_amount']) else 0, axis=1)
    df['Due_From_Party'] = df.apply(lambda x: x['sales_amount'] if x['manual_figures'] == 0 else 0, axis=1)
    
    sales_agg = df.groupby(['destination', 'sales_type'])['sales_amount'].sum().unstack(fill_value=0)
    for col in ['PAID', 'TO PAY', 'TO BE BILLED']:
        if col not in sales_agg.columns: sales_agg[col] = 0
    sales_agg['Total Sales'] = sales_agg.sum(axis=1)
    
    receipt_agg = df.groupby('Receipt_Loc')[['manual_figures', 'Discount', 'Due_From_Party']].sum()
    receipt_agg.rename(columns={'manual_figures': 'Total Receipts'}, inplace=True)
    
    rent_agg, vehicle_agg, other_agg, expense_agg, transfer_agg = [], [], [], [], []
    
    if not df_branch.empty:
        g = df_branch.groupby('destination')
        rent_agg.append(g['Total_Rent'].sum())
        vehicle_agg.append(g['Total_Vehicle'].sum())
        other_agg.append(g['Total_Other_Exp'].sum())
        expense_agg.append(g['Total_Real_Exp'].sum())
        transfer_agg.append(g['Total_Transfer_HO'].sum())
    
    if not df_ho.empty:
        expense_agg.append(pd.Series({HO_NAME: df_ho['Total_HO_Exp'].sum()}))
    else:
        for agg in [rent_agg, vehicle_agg, other_agg, expense_agg]: agg.append(pd.Series({HO_NAME: 0}))
    
    def make_df(l, n): return pd.concat(l).groupby(level=0).sum().to_frame(name=n) if l else pd.DataFrame(columns=[n])
    
    df_rent = make_df(rent_agg, 'Rent')
    df_vehicle = make_df(vehicle_agg, 'Vehicle')
    df_other = make_df(other_agg, 'Other Expenses')
    df_total = make_df(expense_agg, 'Total Expenses')
    df_trans = make_df(transfer_agg, 'Sent to HO')
    
    all_branches = set(sales_agg.index) | set(receipt_agg.index) | set(df_total.index) | set(df_trans.index) | {HO_NAME}
    final_df = pd.DataFrame(index=list(all_branches))
    final_df.index.name = 'Branch'
    final_df = final_df.join([sales_agg, receipt_agg, df_rent, df_vehicle, df_other, df_total, df_trans], how='left').fillna(0)
    
    final_df.rename(columns={'PAID': 'Paid Sales', 'TO PAY': 'To Pay Sales'}, inplace=True)
    if 'Billed Sales' in final_df.columns: final_df.drop(columns=['Billed Sales'], inplace=True)

    final_df['Net Cash to Collect'] = final_df['Total Receipts'] - final_df['Total Expenses'] - final_df['Sent to HO']
    
    for child, parent in PARENT_MAP.items():
        if child in final_df.index and parent in final_df.index:
            final_df.at[parent, 'Net Cash to Collect'] += final_df.at[child, 'Net Cash to Collect']
            final_df.at[child, 'Net Cash to Collect'] = 0
            
    if HO_NAME in final_df.index: final_df.at[HO_NAME, 'Net Cash to Collect'] += final_df['Sent to HO'].sum()
    
    if HO_NAME in final_df.index:
        final_df = pd.concat([final_df.loc[[HO_NAME]], final_df.drop(HO_NAME).sort_index()])
    else:
        final_df = final_df.sort_index()
    
    final_df = pd.concat([final_df, final_df.sum(numeric_only=True).rename('GRAND TOTAL').to_frame().T])
    return final_df

def generate_report_2(df_log):
    if df_log.empty: return pd.DataFrame()
    df = df_log.copy()
    
    df['Discount'] = df.apply(lambda x: (x['sales_amount'] - x['manual_figures']) if (x['manual_figures'] > 0 and x['manual_figures'] < x['sales_amount']) else 0, axis=1)
    df['Excess'] = df.apply(lambda x: (x['manual_figures'] - x['sales_amount']) if x['manual_figures'] > x['sales_amount'] else 0, axis=1)
    df['Due_From_Party'] = df.apply(lambda x: x['sales_amount'] if x['manual_figures'] == 0 else 0, axis=1)
    
    sales = df.pivot_table(index=['manifest_no', 'manifest_date', 'origin', 'destination'], columns='sales_type', values='sales_amount', aggfunc='sum', fill_value=0).reset_index()
    for c in ['TO PAY', 'PAID', 'TO BE BILLED']: 
        if c not in sales.columns: sales[c] = 0
        
    adj = df.groupby(['manifest_no', 'destination'])[['manual_figures', 'Discount', 'Due_From_Party', 'Excess']].sum().reset_index()
    final = pd.merge(sales, adj, on=['manifest_no', 'destination'], how='left')
    
    final['Sum'] = final['TO PAY'] + final['PAID'] + final['TO BE BILLED']
    final.rename(columns={'manifest_no': 'Manifest No', 'manifest_date': 'Manifest Date', 'origin': 'From', 'destination': 'To', 'TO PAY': 'To Pay', 'PAID': 'Paid', 'TO BE BILLED': 'To Be Billed', 'manual_figures': 'Receipt', 'Due_From_Party': 'Due from Party'}, inplace=True)
    
    final['Manifest Date'] = final['Manifest Date'].dt.strftime('%d-%m-%Y')
    cols = ['Manifest No', 'Manifest Date', 'From', 'To', 'To Pay', 'Paid', 'To Be Billed', 'Sum', 'Receipt', 'Discount', 'Due from Party', 'Excess']
    final = final[[c for c in cols if c in final.columns]]
    
    total = final.sum(numeric_only=True)
    total['Manifest No'] = 'GRAND TOTAL'
    return pd.concat([final, pd.DataFrame([total])], ignore_index=True)

def generate_report_3(df_log):
    if df_log.empty: return pd.DataFrame()
    mask = df_log['manual_figures'] == 0
    df_due = df_log[mask].copy()
    
    if df_due.empty: return pd.DataFrame()
    
    df_due['Manifest Date'] = df_due['manifest_date'].dt.strftime('%d-%m-%Y')
    if 'payment_liability' not in df_due.columns: df_due['payment_liability'] = "Unknown"
    
    summary = df_due.groupby('payment_liability').agg({
        'sales_amount': 'sum',
        'cn_no': lambda x: ', '.join(x.astype(str).unique())
    }).reset_index()
    
    summary.rename(columns={'payment_liability': 'Party Name', 'sales_amount': 'Total Due Amount', 'cn_no': 'Pending CN Nos'}, inplace=True)
    summary.sort_values(by='Total Due Amount', ascending=False, inplace=True)
    
    total_due = summary['Total Due Amount'].sum()
    total_row = pd.DataFrame([{'Party Name': 'GRAND TOTAL', 'Total Due Amount': total_due, 'Pending CN Nos': ''}])
    
    return pd.concat([summary, total_row], ignore_index=True)

def generate_report_5(df_log, df_branch, df_ho):
    if df_log.empty: return pd.DataFrame(columns=["Category", "Description", "Amount"])
    
    income = df_log['sales_amount'].sum()
    df_log['Discount'] = df_log.apply(lambda x: (x['sales_amount'] - x['manual_figures']) if (x['manual_figures'] > 0 and x['manual_figures'] < x['sales_amount']) else 0, axis=1)
    total_discount = df_log['Discount'].sum()
    branch_exp = df_branch['Total_Real_Exp'].sum() if not df_branch.empty else 0
    ho_exp = df_ho['Total_HO_Exp'].sum() if not df_ho.empty else 0
    
    data = [
        {"Category": "REVENUE", "Description": "Total Sales", "Amount": income},
        {"Category": "EXPENSE", "Description": "Branch Expenses", "Amount": -branch_exp},
        {"Category": "EXPENSE", "Description": "HO Overheads", "Amount": -ho_exp},
        {"Category": "EXPENSE", "Description": "Discounts", "Amount": -total_discount},
        {"Category": "NET PROFIT", "Description": "Net Business Profit", "Amount": income - branch_exp - ho_exp - total_discount}
    ]
    return pd.DataFrame(data)

def generate_excel_master(r1, r2, r3, df_log, df_branch, df_ho, start, end):
    output = io.BytesIO()
    period = f"Period: {start.strftime('%d-%b-%Y')} to {end.strftime('%d-%b-%Y')}"
    timestamp = f"Generated: {datetime.now().strftime('%d-%b-%Y %I:%M %p')}"
    
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        wb = writer.book
        title_fmt = wb.add_format({'bold': True, 'font_size': 16, 'font_color': 'white', 'bg_color': '#1F4E78'})
        
        def create_sheet(sheet_name, df, title_text):
            if df.empty: return
            df.to_excel(writer, sheet_name=sheet_name, startrow=3)
            ws = writer.sheets[sheet_name]
            ws.write('A1', title_text, title_fmt)
            ws.write('A2', f"{period} | {timestamp}")
            
        create_sheet('Branch_Summary', r1, "EXECUTIVE BRANCH SUMMARY")
        create_sheet('Manifest_Comp', r2, "MANIFEST COMPARISON REPORT")
        create_sheet('Due_Summary', r3, "OUTSTANDING DUES SUMMARY")
        if not df_log.empty: create_sheet('Master_Data', df_log, "FULL MASTER DATA")
        
    return output.getvalue()

# --- 4. MAIN APP ---
def app():
    st.sidebar.header("📅 Report Period")

    if "start_d" not in st.session_state: st.session_state.start_d = date.today().replace(day=1)
    if "end_d" not in st.session_state: st.session_state.end_d = date.today()

    b1, b2 = st.sidebar.columns(2)
    if b1.button("📅 This Month"):
        st.session_state.start_d = date.today().replace(day=1)
        st.session_state.end_d = date.today()
        st.rerun()
    if b2.button("🗓️ Today"):
        st.session_state.start_d = date.today()
        st.session_state.end_d = date.today()
        st.rerun()

    start_date = st.sidebar.date_input("From Date", st.session_state.start_d)
    end_date = st.sidebar.date_input("To Date", st.session_state.end_d)

    if st.sidebar.button("🔄 Refresh Report", type="primary"): st.rerun()

    df_log, df_branch, df_ho = load_data(start_date, end_date)

    st.title("📊 Executive Report Center (Cloud)")
    st.markdown(f"**Period:** {start_date.strftime('%d-%b-%Y')} to {end_date.strftime('%d-%b-%Y')}")

    # METRICS
    col1, col2, col3 = st.columns(3)
    r5 = generate_report_5(df_log, df_branch, df_ho)
    if not r5.empty:
        rev = r5.loc[0, 'Amount']
        exp = r5[r5['Amount'] < 0].iloc[:-1]['Amount'].sum()
        net = r5.iloc[-1]['Amount']
        col1.metric("Revenue", f"₹ {rev:,.0f}")
        col2.metric("Expenses", f"₹ {abs(exp):,.0f}")
        col3.metric("Net Profit", f"₹ {net:,.0f}")

    r1 = generate_report_1(df_log, df_branch, df_ho)
    r2 = generate_report_2(df_log)
    r3 = generate_report_3(df_log)

    tabs = st.tabs(["📄 Branch Summary", "📑 Manifest Comp", "⚠️ Due Summary", "💰 P&L", "🗄️ Master Data", "⚙️ Settings"])

    with tabs[0]:
        if not r1.empty:
            st.dataframe(r1, use_container_width=True)
            if HAS_PLOTLY:
                chart_df = r1.iloc[:-1].reset_index()
                if 'Branch' not in chart_df.columns: chart_df.rename(columns={chart_df.columns[0]: 'Branch'}, inplace=True)
                fig = px.bar(chart_df, x='Branch', y=['Paid Sales', 'To Pay Sales', 'Rent', 'Total Expenses'], title="Branch Performance")
                st.plotly_chart(fig, use_container_width=True)
        else: st.info("No Data")

    with tabs[1]:
        st.dataframe(r2, use_container_width=True, hide_index=True) if not r2.empty else st.info("No Data")

    with tabs[2]:
        st.dataframe(r3, use_container_width=True, hide_index=True) if not r3.empty else st.success("No Outstanding Dues!")

    with tabs[3]:
        st.dataframe(r5, use_container_width=True) if not r5.empty else st.info("No Data")

    with tabs[4]:
        st.dataframe(df_log, use_container_width=True) if not df_log.empty else st.info("No Master Data")

    with tabs[5]:
        st.header("⚙️ Hub & Spoke Configuration")
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1: child_in = st.text_input("Sub Branch")
        with c2: parent_in = st.text_input("Main Hub")
        with c3:
            st.write("")
            if st.button("➕ Add"):
                if add_mapping(child_in, parent_in):
                    st.success("Saved!")
                    st.rerun()

        current_map = get_parent_map()
        if current_map:
            map_df = pd.DataFrame(list(current_map.items()), columns=['Sub Branch', 'Main Hub'])
            st.dataframe(map_df, use_container_width=True)
            del_target = st.selectbox("Select Rule to Delete", map_df['Sub Branch'].tolist())
            if st.button("🗑️ Delete"):
                delete_mapping(del_target)
                st.success("Deleted.")
                st.rerun()

    if not r1.empty:
        st.sidebar.divider()
        excel_data = generate_excel_master(r1, r2, r3, df_log, df_branch, df_ho, start_date, end_date)
        st.sidebar.download_button("📥 Download Full Report", excel_data, f"Executive_Report_{start_date}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

if __name__ == "__main__":
    app()