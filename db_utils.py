import streamlit as st
import psycopg2
import pandas as pd

def get_db_connection():
    """
    Establishes a connection to the Supabase PostgreSQL database.
    """
    return psycopg2.connect(
        host=st.secrets["connections"]["supabase"]["host"],
        port=st.secrets["connections"]["supabase"]["port"],
        database=st.secrets["connections"]["supabase"]["database"],
        user=st.secrets["connections"]["supabase"]["username"],
        password=st.secrets["connections"]["supabase"]["password"]
    )

def run_query(query, params=None):
    """
    Executes a query (INSERT, UPDATE, DELETE) that changes data.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(query, params)
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def fetch_data(query, params=None):
    """
    Executes a SELECT query and returns a Pandas DataFrame.
    """
    conn = get_db_connection()
    try:
        return pd.read_sql(query, conn, params=params)
    finally:
        conn.close()
