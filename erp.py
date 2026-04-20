import streamlit as st
import sqlite3
import pandas as pd
import os
from datetime import datetime

# --- НАЛАШТУВАННЯ СИСТЕМИ ---
DB_NAME = 'factory.db'
FILES_DIR = 'files'
if not os.path.exists(FILES_DIR):
    os.makedirs(FILES_DIR)

# --- ІНІЦІАЛІЗАЦІЯ БАЗИ ДАНИХ ---
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        # Склад
        cursor.execute('CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY, name TEXT, qty REAL, price REAL)')
        # Замовлення
        cursor.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, customer TEXT, detail TEXT, qty INTEGER, price REAL, status TEXT, photo TEXT)')
        # Користувачі
        cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                          (username TEXT PRIMARY KEY, password TEXT, role TEXT, last_seen TIMESTAMP)''')
        # Логи
        cursor.execute('''CREATE TABLE IF NOT EXISTS logs 
                          (id INTEGER PRIMARY KEY, timestamp TIMESTAMP, username TEXT, action TEXT)''')
        
        # Дефолтний адмін
        cursor.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES ('admin', 'admin123', 'Адмін')")
        conn.commit()

init_db()

def add_log(username, action):
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("INSERT INTO logs (timestamp, username, action) VALUES (?, ?, ?)", 
                     (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), username, action))
        conn.commit()

# --- АВТОРИЗАЦІЯ ---
def check_password():
    if "authenticated" not in st.session_state:
        st.title("🏭 ERP Система Заводу")
        user = st.text_input("Логін")
        pwd = st.text_input("Пароль", type="password")
        if st.button("Увійти"):
            with sqlite3.connect(DB_NAME) as conn:
                res = conn.execute("SELECT username, role FROM users WHERE username=? AND password=?", (user, pwd)).fetchone()
                if res:
                    st.session_state["authenticated"] = True
                    st.session_state["username"] = res[0]
                    st.session_state["role"] = res[1]
                    st.rerun()
                else:
                    st.error("❌ Невірний логін або пароль")
        return False
    
    # Heartbeat (Оновлення статусу онлайн)
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
    
    if st.sidebar.button("Вийти"):
        st.session_state.clear()
        st.rerun()

    # Список онлайн
    st.sidebar.markdown("---")
    st.sidebar.subheader("🟢 Зараз у системі")
    with sqlite3.connect(DB_NAME) as conn:
        online_users = pd.read_sql_query(
            "SELECT username, role FROM users WHERE last_seen > datetime('now', '-5 minutes', 'localtime')", conn)
        for _, row in online_users.iterrows():
            st.sidebar.write(f"● {row['username']} ({row['role']})")

    # Меню
    menu = ["📊 Аналітика", "🛠 Виробництво", "📦 Склад"]
    if user_role == "Адмін":
        menu += ["📝 Нове замовлення", "⚙️ Персонал", "📜 Журнал дій"]
    
    choice = st.sidebar.selectbox("Меню", menu)
    db_conn = sqlite3.connect(DB_NAME)

    # --- 1. АНАЛІТИКА ---
    if choice == "📊 Аналітика":
        st.header("📈 Стан підприємства")
        if user_role == "Адмін":
            df_inv = pd.read_sql_query("SELECT SUM(qty * price) as val FROM inventory", db_conn)
            df_ord = pd.read_sql_query("SELECT SUM(qty * price) as val FROM orders WHERE status != 'Готово'", db_conn)
            c1, c2 = st.columns(2)
            c1.metric("Вартість складу (грн)", f"{df_inv['val'].iloc[0] or 0:,.2f}")
            c2.metric("Замовлення в роботі (грн)", f"{df_ord['val'].iloc[0] or 0:,.2f}")
        else:
            st.info("Доступ до фінансових даних має лише Адмін.")

    # --- 2. ВИРОБНИЦТВО ---
    elif choice == "🛠 Виробництво":
        st.header("📋 Журнал виробництва")
        df_orders = pd.read_sql_query("SELECT * FROM orders", db_conn)
        for _, row in df_orders.iterrows():
            with st.expander(f"Замовлення №{row['id']} | {row['customer']} | {row['detail']} ({row['status']})"):
                c1, c2 = st.columns(2)
                with c1:
                    st.write(f"Кількість: {row['qty']} шт.")
                    if user_role == "Адмін": st.write(f"Ціна: {row['price']} грн")
                with c2:
                    statuses = ["Нове", "Обробка", "Готово"]
                    current_idx = statuses.index(row['status']) if row['status'] in statuses else 0
                    new_status = st.selectbox("Змінити статус", statuses, index=current_idx, key=f"s_{row['id']}")
                    if st.button("Оновити статус", key=f"b_{row['id']}"):
                        db_conn.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, row['id']))
                        db_conn.commit()
                        add_log(username, f"Змінив статус замовлення №{row['id']} на '{new_status}'")
                        st.rerun()

    # --- 3. СКЛАД ---
    elif choice == "📦 Склад":
        st.header("📦 Склад матеріалів")
        q = "SELECT * FROM inventory" if user_role == "Адмін" else "SELECT name, qty FROM inventory"
        st.dataframe(pd.read_sql_query(q, db_conn), use_container_width=True)
        if user_role == "Адмін":
            with st.expander("➕ Додати матеріал"):
                with st.form("inv"):
                    n = st.text_input("Назва")
                    qty = st.number_input("Кількість", min_value=0.0)
                    pr = st.number_input("Ціна закупівлі", min_value=0.0)
                    if st.form_submit_button("Зберегти"):
                        db_conn.execute("INSERT INTO inventory (name, qty, price) VALUES (?,?,?)", (n, qty, pr))
                        db_conn.commit()
                        add_log(username, f"Додав на склад: {n} ({qty} шт)")
                        st.rerun()

    # --- 4. НОВЕ ЗАМОВЛЕННЯ ---
    elif choice == "📝 Нове замовлення":
        st.header("🆕 Оформлення замовлення")
        with st.form("order"):
            cust = st.text_input("Замовник")
            det = st.text_input("Виріб")
            q_ord = st.number_input("Кількість", min_value=1)
            p_ord = st.number_input("Ціна продажу (за шт)", min_value=0.0)
            if st.form_submit_button("Запустити у виробництво"):
                db_conn.execute("INSERT INTO orders (customer, detail, qty, price, status) VALUES (?,?,?,?,'Нове')", (cust, det, q_ord, p_ord))
                db_conn.commit()
                add_log(username, f"Створив замовлення: {det} для {cust}")
                st.success("Замовлення додано!")

    # --- 5. ПЕРСОНАЛ ---
    elif choice == "⚙️ Персонал":
        st.header("👥 Керування доступом")
        with st.expander("➕ Зареєструвати працівника"):
            with st.form("reg"):
                u, p, r = st.text_input("Логін"), st.text_input("Пароль", type="password"), st.selectbox("Роль", ["Адмін", "Конструктор", "Робочий"])
                if st.form_submit_button("Створити акаунт"):
                    try:
                        db_conn.execute("INSERT INTO users (username, password, role) VALUES (?,?,?)", (u, p, r))
                        db_conn.commit()
                        add_log(username, f"Створив користувача {u}")
                        st.success("Готово!")
                        st.rerun()
                    except: st.error("Цей логін вже зайнятий")

        st.divider()
        st.subheader("📝 Редагування даних")
        all_u = pd.read_sql_query("SELECT username, role FROM users", db_conn)
        target = st.selectbox("Кого редагуємо?", all_u['username'].tolist())
        
        c1, c2 = st.columns(2)
        with c1:
            edit_name = st.text_input("Новий логін", value=target)
            edit_role = st.selectbox("Нова роль", ["Адмін", "Конструктор", "Робочий"], 
                                     index=["Адмін", "Конструктор", "Робочий"].index(all_u[all_u['username']==target]['role'].iloc[0]))
        with c2:
            edit_pass = st.text_input("Новий пароль (залиште порожнім, якщо не змінюєте)")

        if st.button("💾 Зберегти зміни"):
            if edit_pass:
                db_conn.execute("UPDATE users SET username=?, password=?, role=? WHERE username=?", (edit_name, edit_pass, edit_role, target))
            else:
                db_conn.execute("UPDATE users SET username=?, role=? WHERE username=?", (edit_name, edit_role, target))
            db_conn.execute("UPDATE logs SET username=? WHERE username=?", (edit_name, target))
            db_conn.commit()
            add_log(username, f"Змінив дані користувача {target}")
            st.rerun()

        if st.button("🗑 Видалити працівника"):
            if target != username:
                db_conn.execute("DELETE FROM users WHERE username=?", (target,))
                db_conn.commit()
                add_log(username, f"Видалив користувача {target}")
                st.rerun()
            else: st.error("Себе видаляти не можна!")

    # --- 6. ЖУРНАЛ ДІЙ ---
    elif choice == "📜 Журнал дій":
        st.header("📜 Журнал активності персоналу")
        df_l = pd.read_sql_query("SELECT timestamp as 'Час', username as 'Користувач', action as 'Дія' FROM logs ORDER BY timestamp DESC LIMIT 100", db_conn)
        st.table(df_l)

    db_conn.close()

