import streamlit as st
import pandas as pd
import db_utils

# --- MAIN APP ---

def app():
    st.title("📝 Logistics Data Entry & Import")

    # Tabs for Manual Entry vs Bulk Import
    tab1, tab2 = st.tabs(["📂 Bulk Import (CSV)", "✍️ Manual Entry"])

    # -------------------------------------------------------------------------
    # TAB 1: FAST BULK IMPORT ⚡
    # -------------------------------------------------------------------------
    with tab1:
        st.subheader("Upload Monthly Manifest CSV")
        
        uploaded_file = st.file_uploader("Choose a CSV file", type=["csv"])
        
        if uploaded_file is not None:
            try:
                # 1. Load the CSV (Force 'Actual WT' as String)
                df = pd.read_csv(uploaded_file, dtype={'Actual WT': str})

                # 2. Rename Columns to match Database
                df = df.rename(columns={
                    "Manifest No": "manifest_no",
                    "Manifest Date": "manifest_date",
                    "CN No": "cn_no",
                    "CN Date": "cn_date",
                    "Consignor": "consignor",
                    "Consignee": "consignee",
                    "Payment Liability": "payment_liability",
                    "No. of PKGS": "no_of_pkgs",
                    "Type": "pkg_type",
                    "Actual WT": "actual_wt",
                    "Consignor Invoice No": "consignor_invoice_no",
                    "From": "dispatch_from",
                    "To": "dispatch_to",
                    "Sales Type": "sales_type",
                    "Sales Amount (₹)": "sales_amount"
                })

                # 3. Clean Data (Dates & Empty Values)
                df['manifest_date'] = pd.to_datetime(df['manifest_date'], dayfirst=True).dt.date
                df['cn_date'] = pd.to_datetime(df['cn_date'], dayfirst=True).dt.date
                df = df.fillna("")  # Replace NaN with empty strings

                # 4. Preview
                st.write(f"### Ready to Upload {len(df)} Rows")
                st.dataframe(df.head())

                # 5. FAST UPLOAD BUTTON
                if st.button("🚀 Fast Upload to Database", type="primary"):
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    # --- BATCH CONFIGURATION ---
                    chunk_size = 500  # Upload 500 rows at a time (Much faster)
                    total_rows = len(df)
                    chunks = [df[i:i + chunk_size] for i in range(0, total_rows, chunk_size)]
                    
                    # --- BATCH INSERT LOOP ---
                    for i, chunk in enumerate(chunks):
                        
                        # 1. Create placeholders: "(%s, %s, ...), (%s, %s, ...)"
                        # We have 16 columns (including created_by)
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

                        # 2. Flatten the data for the query
                        flat_data = []
                        for _, row in chunk.iterrows():
                            flat_data.extend([
                                row['manifest_no'], row['manifest_date'], row['cn_no'], row['cn_date'],
                                row['consignor'], row['consignee'], row['payment_liability'],
                                row['no_of_pkgs'], row['pkg_type'], str(row['actual_wt']), # Ensure string
                                row['consignor_invoice_no'], row['dispatch_from'], row['dispatch_to'],
                                row['sales_type'], row['sales_amount'], 
                                st.session_state.username
                            ])

                        # 3. Run ONE query for the whole chunk
                        try:
                            db_utils.run_query(query, tuple(flat_data))
                        except Exception as e:
                            st.error(f"Error in batch {i}: {e}")
                            break

                        # Update Progress
                        progress = min((i + 1) * chunk_size, total_rows)
                        progress_bar.progress(progress / total_rows)
                        status_text.text(f"Uploaded {progress}/{total_rows} rows...")

                    st.success(f"✅ Successfully uploaded {total_rows} entries in seconds!")
                    st.balloons()

            except Exception as e:
                st.error(f"Error processing file: {e}")

    # -------------------------------------------------------------------------
    # TAB 2: MANUAL ENTRY
    # -------------------------------------------------------------------------
    with tab2:
        with st.form("entry_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                manifest_no = st.text_input("Manifest No")
                manifest_date = st.date_input("Manifest Date")
                cn_no = st.text_input("CN No")
                cn_date = st.date_input("CN Date")
                consignor = st.text_input("Consignor")
                consignee = st.text_input("Consignee")
                payment_liability = st.selectbox("Payment Liability", ["Consignor", "Consignee"])
            
            with col2:
                no_of_pkgs = st.number_input("No. of PKGS", min_value=1, step=1)
                pkg_type = st.selectbox("Type", ["Box", "Bag", "Carton", "Bundle", "Drum", "Nag"])
                
                # Text Input for Weight (To match Database)
                actual_wt = st.text_input("Actual WT (e.g., 10kg, 0.00 FIXED)")
                
                consignor_invoice_no = st.text_input("Invoice No")
                dispatch_from = st.text_input("From (City)")
                dispatch_to = st.text_input("To (City)")
                sales_type = st.selectbox("Sales Type", ["TO PAY", "PAID", "TO BE BILLED"])
                sales_amount = st.number_input("Sales Amount (₹)", min_value=0.0, step=1.0)

            submitted = st.form_submit_button("💾 Save Entry")
            
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
                        st.success("✅ Entry Saved Successfully!")
                    except Exception as e:
                        st.error(f"Database Error: {e}")
