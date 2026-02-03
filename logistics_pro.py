import streamlit as st
import pandas as pd
import db_utils
from datetime import datetime

# --- MAIN APP ---

def app():
    st.title("📝 Logistics Data Entry")

    # RESTORED: Tabs Layout (Manual Entry is First)
    tab1, tab2 = st.tabs(["✍️ Manual Entry", "📂 Bulk Import (CSV)"])

    # -------------------------------------------------------------------------
    # TAB 1: MANUAL ENTRY (The UI you prefer)
    # -------------------------------------------------------------------------
    with tab1:
        st.subheader("New Logistics Entry")
        
        with st.form("entry_form", clear_on_submit=True):
            # 2-Column Layout for clean entry
            col1, col2 = st.columns(2)
            
            with col1:
                manifest_no = st.text_input("Manifest No")
                manifest_date = st.date_input("Manifest Date", datetime.now())
                cn_no = st.text_input("CN No")
                cn_date = st.date_input("CN Date", datetime.now())
                consignor = st.text_input("Consignor")
                consignee = st.text_input("Consignee")
                payment_liability = st.selectbox("Payment Liability", ["Consignor", "Consignee"])
            
            with col2:
                no_of_pkgs = st.number_input("No. of PKGS", min_value=1, step=1)
                pkg_type = st.selectbox("Type", ["Box", "Bag", "Carton", "Bundle", "Drum", "Nag"])
                
                # Weight is TEXT (Accepts '10kg' or '0.00 FIXED')
                actual_wt = st.text_input("Actual WT (e.g., 10kg, 0.00 FIXED)")
                
                consignor_invoice_no = st.text_input("Invoice No")
                dispatch_from = st.text_input("From (City)")
                dispatch_to = st.text_input("To (City)")
                sales_type = st.selectbox("Sales Type", ["TO PAY", "PAID", "TO BE BILLED"])
                sales_amount = st.number_input("Sales Amount (₹)", min_value=0.0, step=1.0)

            submitted = st.form_submit_button("💾 Save Entry", type="primary")
            
            if submitted:
                if not manifest_no or not cn_no:
                    st.error("⚠️ Manifest No and CN No are required!")
                else:
                    query = """
                        INSERT INTO logistics_entries (
                            manifest_no, manifest_date, cn_no, cn_date, 
                            consignor, consignee, payment_liability, 
                            no_of_pkgs, pkg_type, actual_wt, 
                            consignor_invoice_no, dispatch_from, dispatch_to, 
                            sales_type, sales_amount, created_by
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    data = (
                        manifest_no, manifest_date, cn_no, cn_date, 
                        consignor, consignee, payment_liability, 
                        no_of_pkgs, pkg_type, actual_wt, 
                        consignor_invoice_no, dispatch_from, dispatch_to, 
                        sales_type, sales_amount, st.session_state.username
                    )
                    
                    try:
                        db_utils.run_query(query, data)
                        st.success(f"✅ Entry {cn_no} Saved Successfully!")
                    except Exception as e:
                        st.error(f"Database Error: {e}")

    # -------------------------------------------------------------------------
    # TAB 2: FAST BULK IMPORT (With Template Download)
    # -------------------------------------------------------------------------
    with tab2:
        st.subheader("Upload Monthly Manifest CSV")
        
        # 1. Download Template Button
        template_data = {
            "Manifest No": [], "Manifest Date": [], "CN No": [], "CN Date": [],
            "Consignor": [], "Consignee": [], "Payment Liability": [], "No. of PKGS": [],
            "Type": [], "Actual WT": [], "Consignor Invoice No": [], "From": [], "To": [],
            "Sales Type": [], "Sales Amount (₹)": []
        }
        df_template = pd.DataFrame(template_data)
        csv_template = df_template.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Excel Template",
            data=csv_template,
            file_name="Manifest_Import_Template.csv",
            mime="text/csv"
        )
        
        st.divider()

        # 2. File Upload
        uploaded_file = st.file_uploader("Choose a CSV file", type=["csv"])
        
        if uploaded_file is not None:
            try:
                # Load CSV (Force Weight as String)
                df = pd.read_csv(uploaded_file, dtype={'Actual WT': str})

                # Rename Columns
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

                # Clean Date format
                df['manifest_date'] = pd.to_datetime(df['manifest_date'], dayfirst=True).dt.date
                df['cn_date'] = pd.to_datetime(df['cn_date'], dayfirst=True).dt.date
                df = df.fillna("")

                st.info(f"📄 Ready to Upload {len(df)} Rows")
                
                # 3. FAST UPLOAD BUTTON
                if st.button("🚀 Fast Upload to Database", type="primary"):
                    progress_bar = st.progress(0)
                    chunk_size = 500
                    total_rows = len(df)
                    chunks = [df[i:i + chunk_size] for i in range(0, total_rows, chunk_size)]
                    
                    for i, chunk in enumerate(chunks):
                        # Create SQL placeholders
                        placeholders = ",".join(["(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"] * len(chunk))
                        
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

                        try:
                            db_utils.run_query(query, tuple(flat_data))
                        except Exception as e:
                            st.error(f"Error in batch {i}: {e}")
                            break
                        
                        progress_bar.progress(min((i + 1) * chunk_size, total_rows) / total_rows)

                    st.success(f"✅ Success! Uploaded {total_rows} entries.")
                    st.balloons()

            except Exception as e:
                st.error(f"Error processing file: {e}")
