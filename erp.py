import streamlit as st
import sqlite3
import pandas as pd
import os
import hashlib
from datetime import datetime

DB_NAME = 'factory.db'
FILES_DIR = 'files'
os.makedirs(FILES_DIR, exist_ok=True)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()

        c.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT,
            last_seen TIMESTAMP
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            qty REAL,
            price REAL
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer TEXT,
            detail TEXT,
            qty INTEGER,
            price REAL,
            status TEXT,
            photo TEXT
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            username TEXT,
            action TEXT
        )''')

        # --- ADMIN FIX ---
        c.execute("SELECT password FROM users WHERE username='admin'")
        res = c.fetchone()

        if not res:
            c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                      ('admin', hash_password('admin123'), 'Адмін'))
        else:
            if res[0] == 'admin123':
                c.execute("UPDATE users SET password=? WHERE username='admin'",
                          (hash_password('admin123'),))

        conn.commit()

init_db()

def add_log(user, action):
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("INSERT INTO logs (timestamp, username, action) VALUES (?, ?, ?)",
                     (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user, action))
        conn.commit()

def login():
    st.title("🏭 Factory ERP")
    u = st.text_input("Логін")
    p = st.text_input("Пароль", type="password")

    if st.button("Увійти"):
        with sqlite3.connect(DB_NAME) as conn:
            # проба через хеш
            res = conn.execute(
                "SELECT username, role FROM users WHERE username=? AND password=?",
                (u, hash_password(p))
            ).fetchone()

            # fallback для старих паролів
            if not res:
                res_plain = conn.execute(
                    "SELECT username, role FROM users WHERE username=? AND password=?",
                    (u, p)
                ).fetchone()

                if res_plain:
                    conn.execute(
                        "UPDATE users SET password=? WHERE username=?",
                        (hash_password(p), u)
                    )
                    conn.commit()
                    res = res_plain

            if res:
                st.session_state.auth = True
                st.session_state.user = res[0]
                st.session_state.role = res[1]
                st.rerun()
            else:
                st.error("❌ Невірний логін або пароль")

if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    login()
    st.stop()

user = st.session_state.user
role = st.session_state.role

with sqlite3.connect(DB_NAME) as conn:
    conn.execute("UPDATE users SET last_seen=? WHERE username=?",
                 (datetime.now(), user))
    conn.commit()

st.sidebar.title(f"👤 {user}")
st.sidebar.write(f"Роль: {role}")

if st.sidebar.button("Вийти"):
    st.session_state.clear()
    st.rerun()

menu = ["Аналітика", "Виробництво", "Склад"]
if role == "Адмін":
    menu += ["Замовлення", "Персонал", "Логи"]

choice = st.sidebar.selectbox("Меню", menu)

conn = sqlite3.connect(DB_NAME)

if choice == "Аналітика":
    st.header("📊 Аналітика")
    df = pd.read_sql_query("SELECT status, SUM(qty) as total FROM orders GROUP BY status", conn)
    if not df.empty:
        st.bar_chart(df.set_index("status"))

elif choice == "Виробництво":
    st.header("🛠 Виробництво")
    df = pd.read_sql_query("SELECT * FROM orders", conn)

    for _, row in df.iterrows():
        with st.expander(f"#{row['id']} {row['detail']} ({row['status']})"):
            st.write(f"Замовник: {row['customer']}")
            st.write(f"Кількість: {row['qty']}")

            new_status = st.selectbox("Статус", ["Нове", "В роботі", "Готово"], key=f"s{row['id']}")
            if st.button("Оновити", key=f"b{row['id']}"):
                conn.execute("UPDATE orders SET status=? WHERE id=?", (new_status, row['id']))
                conn.commit()
                add_log(user, f"Update order {row['id']}")
                st.rerun()

elif choice == "Склад":
    st.header("📦 Склад")
    df = pd.read_sql_query("SELECT * FROM inventory", conn)
    st.dataframe(df)

elif choice == "Замовлення":
    st.header("➕ Нове замовлення")

    with st.form("order"):
        c = st.text_input("Клієнт")
        d = st.text_input("Деталь")
        q = st.number_input("Кількість", 1)
        p = st.number_input("Ціна", 0.0)

        if st.form_submit_button("Створити"):
            conn.execute(
                "INSERT INTO orders (customer, detail, qty, price, status) VALUES (?,?,?,?,?)",
                (c, d, q, p, "Нове")
            )
            conn.commit()
            st.success("OK")

conn.close()
