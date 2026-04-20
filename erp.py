import streamlit as st
import sqlite3
import pandas as pd
import os
from datetime import datetime

# --- НАСТРОЙКИ СИСТЕМЫ ---
DB_NAME = 'factory.db'
FILES_DIR = 'files'
if not os.path.exists(FILES_DIR):
    os.makedirs(FILES_DIR)

# --- ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ---
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        # Склад
        cursor.execute('CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY, name TEXT, qty REAL, price REAL)')
        # Заказы
        cursor.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, customer TEXT, detail TEXT, qty INTEGER, price REAL, status TEXT, photo TEXT)')
        # Пользователи
        cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                          (username TEXT PRIMARY KEY, password TEXT, role TEXT, last_seen TIMESTAMP)''')
        # Логи
        cursor.execute('''CREATE TABLE IF NOT EXISTS logs 
                          (id INTEGER PRIMARY KEY, timestamp TIMESTAMP, username TEXT, action TEXT)''')
        
        # Дефолтный админ
        cursor.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES ('admin', 'admin123', 'Админ')")
        conn.commit()

init_db()

def add_log(username, action):
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("INSERT INTO logs (timestamp, username, action) VALUES (?, ?, ?)", 
                     (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), username, action))
        conn.commit()

# --- АВТОРИЗАЦИЯ ---
def check_password():
    if "authenticated" not in st.session_state:
        st.title("🏭 ERP Система Завода")
        user = st.text_input("Логин")
        pwd = st.text_input("Пароль", type="password")
        if st.button("Войти"):
            with sqlite3.connect(DB_NAME) as conn:
                res = conn.execute("SELECT username, role FROM users WHERE username=? AND password=?", (user, pwd)).fetchone()
                if res:
                    st.session_state["authenticated"] = True
                    st.session_state["username"] = res[0]
                    st.session_state["role"] = res[1]
                    st.rerun()
                else:
                    st.error("❌ Неверный логин или пароль")
        return False
    
    # Heartbeat (Обновление статуса онлайн)
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("UPDATE users SET last_seen = ? WHERE username = ?", (datetime.now(), st.session_state["username"]))
        conn.commit()
    return True

if check_password():
    st.set_page_config(page_title="Factory ERP Pro", layout="wide")
    user_role = st.session_state["role"]
    username = st.session_state["username"]

    # --- SIDEBAR ---
    st.sidebar.title(f"👤 {username}")
    st.sidebar.info(f"Роль: {user_role}")
    
    if st.sidebar.button("Выйти"):
        st.session_state.clear()
        st.rerun()

    # Список онлайн
    st.sidebar.markdown("---")
    st.sidebar.subheader("🟢 Сейчас в системе")
    with sqlite3.connect(DB_NAME) as conn:
        online_users = pd.read_sql_query(
            "SELECT username, role FROM users WHERE last_seen > datetime('now', '-5 minutes', 'localtime')", conn)
        for _, row in online_users.iterrows():
            st.sidebar.write(f"● {row['username']} ({row['role']})")

    # Меню
    menu = ["📊 Аналитика", "🛠 Производство", "📦 Склад"]
    if user_role == "Админ":
        menu += ["📝 Новый заказ", "⚙️ Персонал", "📜 Логи"]
    
    choice = st.sidebar.selectbox("Меню", menu)
    conn = sqlite3.connect(DB_NAME)

    # --- 1. АНАЛИТИКА ---
    if choice == "📊 Аналитика":
        st.header("📈 Состояние предприятия")
        if user_role == "Админ":
            df_inv = pd.read_sql_query("SELECT SUM(qty * price) as val FROM inventory", conn)
            df_ord = pd.read_sql_query("SELECT SUM(qty * price) as val FROM orders WHERE status != 'Готово'", conn)
            c1, c2 = st.columns(2)
            c1.metric("Склад (грн)", f"{df_inv['val'].iloc[0] or 0:,.2f}")
            c2.metric("В работе (грн)", f"{df_ord['val'].iloc[0] or 0:,.2f}")
        else:
            st.info("Доступ к финансовым данным только у Админа.")

    # --- 2. ПРОИЗВОДСТВО ---
    elif choice == "🛠 Производство":
        st.header("📋 Журнал производства")
        df_orders = pd.read_sql_query("SELECT * FROM orders", conn)
        for _, row in df_orders.iterrows():
            with st.expander(f"Заказ №{row['id']} | {row['customer']} | {row['detail']} ({row['status']})"):
                c1, c2 = st.columns(2)
                with c1:
                    st.write(f"Кол-во: {row['qty']} шт.")
                    if user_role == "Админ": st.write(f"Цена: {row['price']} грн")
                with c2:
                    new_status = st.selectbox("Сменить статус", ["Новое", "Обработка", "Готово"], 
                                             index=["Новое", "Обработка", "Готово"].index(row['status']), key=f"s_{row['id']}")
                    if st.button("Обновить", key=f"b_{row['id']}"):
                        conn.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, row['id']))
                        conn.commit()
                        add_log(username, f"Изменил статус заказа №{row['id']} на '{new_status}'")
                        st.rerun()

    # --- 3. СКЛАД ---
    elif choice == "📦 Склад":
        st.header("📦 Склад материалов")
        query = "SELECT * FROM inventory" if user_role == "Админ" else "SELECT name, qty FROM inventory"
        st.dataframe(pd.read_sql_query(query, conn), use_container_width=True)
        if user_role == "Админ":
            with st.expander("Добавить материал"):
                with st.form("inv"):
                    n = st.text_input("Название")
                    q = st.number_input("Кол-во", min_value=0.0)
                    p = st.number_input("Цена", min_value=0.0)
                    if st.form_submit_button("Добавить"):
                        conn.execute("INSERT INTO inventory (name, qty, price) VALUES (?,?,?)", (n, q, p))
                        conn.commit()
                        add_log(username, f"Добавил на склад: {n} ({q} шт)")
                        st.rerun()

    # --- 4. НОВЫЙ ЗАКАЗ ---
    elif choice == "📝 Новый заказ":
        st.header("🆕 Оформление заказа")
        with st.form("order"):
            cust, det = st.text_input("Заказчик"), st.text_input("Деталь")
            q, p = st.number_input("Количество", min_value=1), st.number_input("Цена продажи", min_value=0.0)
            if st.form_submit_button("Создать"):
                conn.execute("INSERT INTO orders (customer, detail, qty, price, status) VALUES (?,?,?,?,'Новое')", (cust, det, q, p))
                conn.commit()
                add_log(username, f"Создал заказ для {cust}: {det}")
                st.success("Готово!")

    # --- 5. ПЕРСОНАЛ ---
    elif choice == "⚙️ Персонал":
        st.header("👥 Управление персоналом")
        with st.form("new_user"):
            u, p, r = st.text_input("Логин"), st.text_input("Пароль"), st.selectbox("Роль", ["Админ", "Конструктор", "Рабочий"])
            if st.form_submit_button("Создать пользователя"):
                try:
                    conn.execute("INSERT INTO users (username, password, role) VALUES (?,?,?)", (u, p, r))
                    conn.commit()
                    st.success(f"Пользователь {u} создан")
                except: st.error("Логин занят")
        st.dataframe(pd.read_sql_query("SELECT username, role, last_seen FROM users", conn))

    # --- 6. ЛОГИ ---
    elif choice == "📜 Логи":
        st.header("📜 Журнал действий")
        st.dataframe(pd.read_sql_query("SELECT * FROM logs ORDER BY timestamp DESC", conn), use_container_width=True)

    conn.close()
