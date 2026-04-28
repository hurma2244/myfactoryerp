import streamlit as st
import sqlite3
import pandas as pd
import os
import requests
from datetime import datetime, timedelta

# --- 1. НАЛАШТУВАННЯ ---
st.set_page_config(page_title="Factory ERP Pro (Safe Mode)", layout="wide")

DB_NAME = 'factory.db'
TG_TOKEN = "8743391673:AAGPXg-5-87Y881bO5XWhftEPPugKNK4y88"
TG_CHAT_ID = "-1003848428987"

# --- 2. ФУНКЦІЇ ТЕЛЕГРАМ (БЕКАП) ---
def send_db_to_telegram():
    """Надсилає файл бази даних у Телеграм як бекап"""
    url = f"https://telegram.org{TG_TOKEN}/sendDocument"
    try:
        with open(DB_NAME, 'rb') as f:
            requests.post(url, data={'chat_id': TG_CHAT_ID, 'caption': f"📦 Backup: {datetime.now().strftime('%Y-%m-%d %H:%M')}"}, files={'document': f})
    except: pass

def send_file_to_telegram(file_bytes, file_name, caption):
    """Надсилає креслення у Телеграм"""
    url = f"https://telegram.org{TG_TOKEN}/sendDocument"
    try:
        requests.post(url, data={'chat_id': TG_CHAT_ID, 'caption': caption}, files={'document': (file_name, file_bytes)})
    except: pass

# --- 3. ІНІЦІАЛІЗАЦІЯ БД ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY, name TEXT, qty REAL, price REAL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, customer TEXT, detail TEXT, qty INTEGER, price REAL, status TEXT, has_files BOOLEAN)')
    cursor.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT, last_seen TIMESTAMP)')
    
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO users VALUES ('admin', 'admin123', 'Адмін', ?)", (datetime.now(),))
    conn.commit()
    conn.close()

init_db()

# --- 4. АВТОРИЗАЦІЯ ---
if "auth" not in st.session_state:
    st.title("🏭 ERP Factory (Safe Mode)")
    # Функція відновлення бази (якщо файл зник)
    with st.expander("🔄 Відновити базу з бекапу"):
        up_db = st.file_uploader("Завантажте файл factory.db з Telegram", type="db")
        if up_db and st.button("Відновити"):
            with open(DB_NAME, "wb") as f:
                f.write(up_db.getbuffer())
            st.success("Базу відновлено! Перезавантажте сторінку.")
            st.stop()

    u = st.text_input("Логін").strip()
    p = st.text_input("Пароль", type="password").strip()
    if st.button("Увійти"):
        conn = sqlite3.connect(DB_NAME)
        res = conn.execute("SELECT username, role FROM users WHERE username=? AND password=?", (u, p)).fetchone()
        if res:
            st.session_state["auth"], st.session_state["user"], st.session_state["role"] = True, res[0], res[1]
            st.rerun()
        else: st.error("Помилка входу")
    st.stop()

# --- 5. ІНТЕРФЕЙС ---
user_role = st.session_state["role"]
username = st.session_state["user"]
db_conn = sqlite3.connect(DB_NAME)

st.sidebar.title(f"👤 {username}")
if st.sidebar.button("Вихід"):
    st.session_state.clear()
    st.rerun()

menu = ["📊 Аналітика", "🛠 Виробництво", "📦 Склад"]
if user_role == "Адмін": menu += ["📝 Нове замовлення", "⚙️ Персонал"]
choice = st.sidebar.selectbox("Меню", menu)

# --- СКЛАД ---
if choice == "📦 Склад":
    st.header("📦 Склад")
    df = pd.read_sql("SELECT * FROM inventory", db_conn)
    st.dataframe(df, use_container_width=True)
    if user_role == "Адмін":
        with st.form("add_inv"):
            n, q, p = st.text_input("Назва"), st.number_input("К-ть"), st.number_input("Ціна")
            if st.form_submit_button("Зберегти"):
                db_conn.execute("INSERT INTO inventory (name, qty, price) VALUES (?,?,?)", (n, q, p))
                db_conn.commit()
                send_db_to_telegram() # БЕКАП!
                st.rerun()

# --- НОВЕ ЗАМОВЛЕННЯ ---
elif choice == "📝 Нове замовлення":
    st.header("📝 Нове замовлення")
    with st.form("n_ord", clear_on_submit=True):
        c, d = st.text_input("Клієнт"), st.text_input("Виріб")
        qo, po = st.number_input("К-ть", min_value=1), st.number_input("Ціна")
        files = st.file_uploader("Файли", accept_multiple_files=True)
        if st.form_submit_button("Створити"):
            has_f = False
            if files:
                has_f = True
                for f in files:
                    send_file_to_telegram(f.getvalue(), f.name, f"🆕 Файл для {c}: {d}")
            db_conn.execute("INSERT INTO orders (customer, detail, qty, price, status, has_files) VALUES (?,?,?,?,'Нове',?)", (c, d, qo, po, has_f))
            db_conn.commit()
            send_db_to_telegram() # БЕКАП!
            st.success("Створено!")

# --- ВИРОБНИЦТВО ---
elif choice == "🛠 Виробництво":
    st.header("🛠 Виробництво")
    df_o = pd.read_sql("SELECT * FROM orders ORDER BY id DESC", db_conn)
    for _, row in df_o.iterrows():
        with st.expander(f"📦 №{row['id']} | {row['customer']} | {row['detail']} ({row['status']})"):
            if row['has_files']: st.info("📂 Файли в Telegram")
            new_s = st.selectbox("Статус", ["Нове", "Обробка", "Готово"], index=["Нове", "Обробка", "Готово"].index(row['status']), key=f"s{row['id']}")
            if st.button("Зберегти", key=f"b{row['id']}"):
                db_conn.execute("UPDATE orders SET status=? WHERE id=?", (new_s, row['id']))
                db_conn.commit()
                send_db_to_telegram() # БЕКАП!
                st.rerun()

db_conn.close()

