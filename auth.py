import streamlit as st

# --- CONFIGURATION ---
USERS = {
    "admin": "admin",
    "viewer": "viewer"
}

PASSWORDS = {
    "admin": "admin123",
    "viewer": "view123"
}

def check_login():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.user_role = None
        st.session_state.username = None

    if not st.session_state.logged_in:
        st.sidebar.title("🔒 Secure Login")
        username = st.sidebar.text_input("Username")
        password = st.sidebar.text_input("Password", type="password")

        if st.sidebar.button("Login", type="primary"):
            if username in USERS and PASSWORDS.get(username) == password:
                st.session_state.logged_in = True
                st.session_state.user_role = USERS[username]
                st.session_state.username = username
                st.rerun()
            else:
                st.sidebar.error("Incorrect credentials")
        return False

    return True

def logout():
    if st.sidebar.button("Log out"):
        st.session_state.logged_in = False
        st.session_state.user_role = None
        st.session_state.username = None
        st.rerun()