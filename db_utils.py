import streamlit as st
import psycopg2
import pandas as pd

# --- CONNECT TO SUPABASE ---
def get_db_connection():
    """Establishes a connection to the Supabase PostgreSQL database."""
    try:
        # Load secrets from .streamlit/secrets.toml
        secrets = st.secrets["connections"]["supabase"]
        
        conn = psycopg2.connect(
            host=secrets["host"],
            database=secrets["database"],
            user=secrets["username"],
            password=secrets["password"],
            port=secrets["port"]
        )
        return conn
    except Exception as e:
        st.error(f"❌ Connection to Cloud Database failed: {e}")
        return None

# --- INITIALIZE TABLES (Run Once) ---
def init_all_tables():
    """Creates the tables in Supabase if they don't exist."""
    conn = get_db_connection()
    if not conn: return
    
    try:
        cur = conn.cursor()
        
        # 1. Master Logistics Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS master_data (
                cn_no TEXT PRIMARY KEY,
                manifest_no TEXT,
                manifest_date DATE,
                cn_date DATE,
                consignor TEXT,
                consignee TEXT,
                payment_liability TEXT,
                pkgs REAL,
                type TEXT,
                actual_wt REAL,
                invoice_no TEXT,
                origin TEXT,
                destination TEXT,
                sales_type TEXT,
                sales_amount REAL,
                manual_figures REAL DEFAULT 0,
                remarks TEXT DEFAULT ''
            );
        """)

        # 2. Branch Expenses Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS branch_expenses (
                manifest_no TEXT PRIMARY KEY,
                manifest_date DATE,
                origin TEXT,
                destination TEXT,
                rent REAL DEFAULT 0,
                vehicle REAL DEFAULT 0,
                thela REAL DEFAULT 0,
                remarks TEXT DEFAULT ''
            );
        """)

        # 3. HO Expenses Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ho_expenses (
                entry_date DATE PRIMARY KEY,
                rent REAL DEFAULT 0,
                vehicle REAL DEFAULT 0,
                thela REAL DEFAULT 0,
                remarks TEXT DEFAULT ''
            );
        """)

        # 4. Settings Table (Hub & Spoke)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS branch_mappings (
                id SERIAL PRIMARY KEY,
                child_branch TEXT UNIQUE,
                parent_branch TEXT
            );
        """)

        conn.commit()
        cur.close()
        conn.close()
        # st.toast("✅ Cloud Database Connected & Tables Verified!")
        
    except Exception as e:
        st.error(f"Table Creation Failed: {e}")

# --- HELPER: ADD COLUMN (Safe) ---
def add_column_if_not_exists(table, col_name, col_type="REAL DEFAULT 0"):
    """Adds a column to a Postgres table if it doesn't exist."""
    conn = get_db_connection()
    if not conn: return
    try:
        cur = conn.cursor()
        cur.execute(f"""
            ALTER TABLE {table} 
            ADD COLUMN IF NOT EXISTS "{col_name}" {col_type};
        """)
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass # Ignore if it exists or fails