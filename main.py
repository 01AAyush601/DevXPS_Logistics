import streamlit as st
import auth
import report_center
import logistics_pro
import branch_expenses
import ho_expenses  # <--- FINAL IMPORT

# --- 1. GLOBAL CONFIG ---
st.set_page_config(page_title="DevXPS Logistics", layout="wide", page_icon="🚛")

# --- 2. LOGIN CHECK ---
if not auth.check_login():
    st.title("🚛 DevXPS Logistics System")
    st.info("Please log in using the sidebar to access the system.")
    st.stop()

# --- 3. LOGGED IN NAVIGATION ---
user_role = st.session_state.user_role
st.sidebar.divider()
st.sidebar.write(f"👤 Logged in as: **{st.session_state.username.upper()}**")

# Define available apps
apps = {}

if user_role == "admin":
    apps = {
        "📊 Report Center": "report",
        "📝 Logistics Entry": "entry",
        "💸 Branch Expenses": "expense_b",
        "🏛️ HO Expenses": "expense_ho"
    }
elif user_role == "viewer":
    apps = {
        "📊 Report Center": "report"
    }

# Sidebar Selection
selected_app_name = st.sidebar.radio("Go to:", list(apps.keys()))
selection = apps[selected_app_name]

# --- 4. APP ROUTING ---
if selection == "report":
    report_center.app()

elif selection == "entry":
    try:
        logistics_pro.app()
    except AttributeError:
        st.error("⚠️ Error: `logistics_pro.py` is missing the `app()` function.")

elif selection == "expense_b":
    try:
        branch_expenses.app()
    except AttributeError:
        st.error("⚠️ Error: `branch_expenses.py` is missing the `app()` function.")

elif selection == "expense_ho":
    try:
        ho_expenses.app() # <--- RUNNING THE FINAL FILE
    except AttributeError:
        st.error("⚠️ Error: `ho_expenses.py` is missing the `app()` function.")

# Logout
st.sidebar.divider()
auth.logout()