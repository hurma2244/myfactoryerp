import streamlit as st
import sqlite3
import pandas as pd
import os
import hashlib
from datetime import datetime

# --- CONFIG ---
DB_NAME = "factory.db"
FILES_DIR = "files"

os.makedirs(FILES_DIR, exist_ok=True)

# --- SECURITY ---
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# --- DB ---
def get_conn():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        password TEXT,
        role TEXT,
        last_seen TIMESTAMP
    )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        qty REAL,
        price REAL
    )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer TEXT,
        detail TEXT,
        qty INTEGER,
        price REAL,
        status TEXT,
        photo TEXT
    )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        username TEXT,
        action TEXT
    )
    ''')

    # admin
    c.execute("SELECT * FROM users WHERE username='admin'")
    if not c.fetchone():
        c.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?)",
            ("admin", hash_password("admin123"), "Адмін", datetime.now())
        )

    conn.commit()
    conn.close()

init_db()

# --- LOG ---
def log(user, action):
    conn = get_conn()
    conn.execute(
        "INSERT INTO logs (timestamp, username, action) VALUES (?, ?, ?)",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user, action)
    )
    conn.commit()
    conn.close()

# --- AUTH ---
def login():
    st.title("🏭 Factory ERP")

    user = st.text_input("Логін")
    pwd = st.text_input("Пароль", type="password")

    if st.button("Увійти"):
        conn = get_conn()
        res = conn.execute(
            "SELECT username, role FROM users WHERE username=? AND password=?",
            (user, hash_password(pwd))
        ).fetchone()
        conn.close()

        if res:
            st.session_state["user"] = res[0]
            st.session_state["role"] = res[1]
            st.rerun()
        else:
            st.error("❌ Невірні дані")

# --- CHECK AUTH ---
if "user" not in st.session_state:
    login()
    st.stop()

user = st.session_state["user"]
role = st.session_state["role"]

# update last_seen
conn = get_conn()
conn.execute("UPDATE users SET last_seen=? WHERE username=?", (datetime.now(), user))
conn.commit()
conn.close()

# --- UI ---
st.set_page_config(layout="wide")

st.sidebar.title(f"👤 {user}")
st.sidebar.write(role)

if st.sidebar.button("Вийти"):
    st.session_state.clear()
    st.rerun()

menu = ["Аналітика", "Виробництво", "Склад"]
if role == "Адмін":
    menu += ["Нове замовлення", "Персонал", "Логи"]

choice = st.sidebar.selectbox("Меню", menu)

conn = get_conn()

# --- АНАЛІТИКА ---
if choice == "Аналітика":
    st.header("📊 Аналітика")

    if role == "Адмін":
        inv = pd.read_sql("SELECT SUM(qty*price) as val FROM inventory", conn)
        ords = pd.read_sql("SELECT SUM(qty*price) as val FROM orders WHERE status!='Готово'", conn)

        c1, c2 = st.columns(2)
        c1.metric("Склад", f"{inv['val'][0] or 0:.2f} грн")
        c2.metric("В роботі", f"{ords['val'][0] or 0:.2f} грн")

        df = pd.read_sql("SELECT status, COUNT(*) as cnt FROM orders GROUP BY status", conn)
        st.bar_chart(df.set_index("status"))

    else:
        st.info("Тільки для адміна")

# --- ВИРОБНИЦТВО ---
elif choice == "Виробництво":
    st.header("🛠 Замовлення")

    df = pd.read_sql("SELECT * FROM orders", conn)

    for _, r in df.iterrows():
        with st.expander(f"#{r['id']} | {r['detail']} | {r['status']}"):

            st.write(f"Клієнт: {r['customer']}")
            st.write(f"Кількість: {r['qty']}")

            if role == "Адмін":
                st.write(f"Ціна: {r['price']}")

            statuses = ["Нове", "В роботі", "Контроль", "Готово"]
            new_status = st.selectbox("Статус", statuses, key=r['id'])

            if st.button("Оновити", key=f"b{r['id']}"):
                conn.execute("UPDATE orders SET status=? WHERE id=?", (new_status, r['id']))
                conn.commit()
                log(user, f"Змінив статус #{r['id']} -> {new_status}")
                st.rerun()

# --- СКЛАД ---
elif choice == "Склад":
    st.header("📦 Склад")

    df = pd.read_sql("SELECT * FROM inventory", conn)
    st.dataframe(df)

    if role == "Адмін":

        with st.expander("➕ Додати"):
            with st.form("add"):
                n = st.text_input("Назва")
                q = st.number_input("Кількість", 0.0)
                p = st.number_input("Ціна", 0.0)

                if st.form_submit_button("OK"):
                    conn.execute("INSERT INTO inventory (name, qty, price) VALUES (?,?,?)", (n, q, p))
                    conn.commit()
                    log(user, f"Додав {n}")
                    st.rerun()

        with st.expander("🗑 Видалити"):
            if not df.empty:
                mid = st.selectbox("ID", df["id"])
                if st.button("DEL"):
                    conn.execute("DELETE FROM inventory WHERE id=?", (mid,))
                    conn.commit()
                    log(user, f"Видалив ID {mid}")
                    st.rerun()

# --- НОВЕ ЗАМОВЛЕННЯ ---
elif choice == "Нове замовлення":
    st.header("➕ Нове замовлення")

    with st.form("ord"):
        c = st.text_input("Клієнт")
        d = st.text_input("Деталь")
        q = st.number_input("Кількість", 1)
        p = st.number_input("Ціна", 0.0)

        file = st.file_uploader("Фото", type=["jpg", "png"])

        path = None
        if file:
            path = os.path.join(FILES_DIR, file.name)
            with open(path, "wb") as f:
                f.write(file.getbuffer())

        if st.form_submit_button("Створити"):
            conn.execute(
                "INSERT INTO orders (customer, detail, qty, price, status, photo) VALUES (?,?,?,?,?,?)",
                (c, d, q, p, "Нове", path)
            )
            conn.commit()
            log(user, f"Створив замовлення {d}")
            st.success("OK")

# --- ПЕРСОНАЛ ---
elif choice == "Персонал":
    st.header("👥 Персонал")

    with st.form("reg"):
        u = st.text_input("Логін")
        p = st.text_input("Пароль", type="password")
        r = st.selectbox("Роль", ["Адмін", "Робочий", "Конструктор"])

        if st.form_submit_button("Створити"):
            try:
                conn.execute(
                    "INSERT INTO users VALUES (?, ?, ?, ?)",
                    (u, hash_password(p), r, datetime.now())
                )
                conn.commit()
                log(user, f"Новий користувач {u}")
                st.success("OK")
            except:
                st.error("Є такий логін")

# --- ЛОГИ ---
elif choice == "Логи":
    st.header("📜 Логи")

    df = pd.read_sql("SELECT * FROM logs ORDER BY id DESC LIMIT 100", conn)
    st.dataframe(df)

conn.close()


