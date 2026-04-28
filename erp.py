import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import requests
from datetime import datetime

# --- 1. НАСТРОЙКИ ---
st.set_page_config(page_title="Factory ERP", layout="wide")

# ВСТАВЬТЕ СКОПИРОВАННУЮ ССЫЛКУ СЮДА ПОЛНОСТЬЮ
DB_URI = "postgresql://postgres.sumpnxmxpdzwchanewnj:qWeRtY1234Qrohjt@://supabase.com"


engine = create_engine(DB_URI, pool_pre_ping=True)

# --- 2. ПРОВЕРКА ПОДКЛЮЧЕНИЯ И СОЗДАНИЕ ТАБЛИЦ ---
def init_db():
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS inventory (id SERIAL PRIMARY KEY, name TEXT, qty REAL, price REAL);
                CREATE TABLE IF NOT EXISTS orders (id SERIAL PRIMARY KEY, customer TEXT, detail TEXT, qty INTEGER, price REAL, status TEXT);
                CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT, last_seen TIMESTAMP);
                
                INSERT INTO users (username, password, role) 
                VALUES ('admin', 'admin123', 'Адмін') 
                ON CONFLICT (username) DO NOTHING;
            """))
            conn.commit()
    except Exception as e:
        st.error(f"Ошибка базы: {e}")

init_db()

# --- 3. ВХОД ---
if "auth" not in st.session_state:
    st.title("🏭 ERP Cloud")
    u = st.text_input("Логин")
    p = st.text_input("Пароль", type="password")
    if st.button("Войти"):
        with engine.connect() as conn:
            res = conn.execute(text("SELECT username, role FROM users WHERE username=:u AND password=:p"), {"u":u, "p":p}).fetchone()
            if res:
                st.session_state["auth"] = True
                st.session_state["user"] = res[0]
                st.session_state["role"] = res[1]
                st.rerun()
            else:
                st.error("Ошибка входа")
    st.stop()

# --- 4. КОНТЕНТ (СКЛАД) ---
st.sidebar.title(f"👤 {st.session_state['user']}")
if st.sidebar.button("Выход"):
    st.session_state.clear()
    st.rerun()

menu = ["📦 Склад", "🛠 Производство"]
choice = st.sidebar.selectbox("Меню", menu)

if choice == "📦 Склад":
    st.header("📦 Склад")
    df = pd.read_sql("SELECT * FROM inventory", engine)
    st.dataframe(df, use_container_width=True)
    
    with st.expander("Добавить товар"):
        with st.form("add"):
            n = st.text_input("Название")
            q = st.number_input("Кол-во", min_value=0.0)
            if st.form_submit_button("Сохранить"):
                with engine.connect() as conn:
                    conn.execute(text("INSERT INTO inventory (name, qty) VALUES (:n, :q)"), {"n":n, "q":q})
                    conn.commit()
                st.rerun()

