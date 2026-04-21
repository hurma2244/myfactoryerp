import streamlit as st
import sqlite3
import pandas as pd
import os
from datetime import datetime

# --- 1. НАЛАШТУВАННЯ СТОРІНКИ ---
st.set_page_config(page_title="Factory ERP Pro", layout="wide")

# --- 2. КОНФІГУРАЦІЯ СИСТЕМИ ---
DB_NAME = 'factory.db'
FILES_DIR = 'files'
if not os.path.exists(FILES_DIR):
    os.makedirs(FILES_DIR)

# --- 3. ІНІЦІАЛІЗАЦІЯ БАЗИ ДАНИХ ---
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY, name TEXT, qty REAL, price REAL)')
        cursor.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, customer TEXT, detail TEXT, qty INTEGER, price REAL, status TEXT, photo TEXT)')
        cursor.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT, last_seen TIMESTAMP)')
        cursor.execute('CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY, timestamp TIMESTAMP, username TEXT, action TEXT)')
        
        # Примусове оновлення адміна для входу
        cursor.execute("INSERT OR REPLACE INTO users (username, password, role) VALUES ('admin', 'admin123', 'Адмін')")
        conn.commit()

init_db()

def add_log(username, action):
    try:
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute("INSERT INTO logs (timestamp, username, action) VALUES (?, ?, ?)", 
                         (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), username, action))
            conn.commit()
    except: pass

# --- 4. АВТОРИЗАЦІЯ ---
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
                    add_log(res[0], "Увійшов у систему")
                    st.rerun()
                else:
                    st.error("❌ Невірний логін або пароль")
        return False
    return True

if check_password():
    user_role = st.session_state["role"]
    username = st.session_state["username"]
    db_conn = sqlite3.connect(DB_NAME)

    # --- SIDEBAR ---
    st.sidebar.title(f"👤 {username}")
    st.sidebar.info(f"Роль: {user_role}")
    if st.sidebar.button("Вийти"):
        st.session_state.clear()
        st.rerun()

    menu = ["📊 Аналітика", "🛠 Виробництво", "📦 Склад"]
    if user_role == "Адмін": menu += ["📝 Нове замовлення", "⚙️ Персонал", "📜 Журнал дій"]
    choice = st.sidebar.selectbox("Меню", menu)

    # --- ЛОГІКА РОЗДІЛІВ ---

    if choice == "📊 Аналітика":
        st.header("📈 Аналітика")
        df_inv = pd.read_sql_query("SELECT SUM(qty * price) as val FROM inventory", db_conn)
        df_ord = pd.read_sql_query("SELECT SUM(qty * price) as val FROM orders WHERE status != 'Готово'", db_conn)
        c1, c2 = st.columns(2)
        v_inv = df_inv['val'].iloc[0] if not df_inv.empty and df_inv['val'].iloc[0] else 0
        v_ord = df_ord['val'].iloc[0] if not df_ord.empty and df_ord['val'].iloc[0] else 0
        c1.metric("Склад (грн)", f"{v_inv:,.2f}")
        c2.metric("В роботі (грн)", f"{v_ord:,.2f}")

    elif choice == "🛠 Виробництво":
        st.header("📋 Виробництво")
        df_orders = pd.read_sql_query("SELECT * FROM orders", db_conn)
        for _, row in df_orders.iterrows():
            with st.expander(f"📦 №{row['id']} | {row['customer']} | {row['detail']}"):
                statuses = ["Нове", "Обробка", "Готово"]
                new_status = st.selectbox("Статус", statuses, index=statuses.index(row['status']) if row['status'] in statuses else 0, key=f"s{row['id']}")
                if st.button("Оновити", key=f"b{row['id']}"):
                    db_conn.execute("UPDATE orders SET status=? WHERE id=?", (new_status, row['id']))
                    db_conn.commit()
                    st.rerun()

    elif choice == "📦 Склад":
        st.header("📦 Склад матеріалів")
        df_inv = pd.read_sql_query("SELECT * FROM inventory", db_conn)
        st.dataframe(df_inv, use_container_width=True)

        if user_role == "Адмін":
            # --- ПОВЕРНУТИЙ БЛОК РЕДАГУВАННЯ ---
            st.subheader("📝 Швидке корегування залишків")
            if not df_inv.empty:
                cadj1, cadj2, cadj3 = st.columns(3)
                mat_adj = cadj1.selectbox("Оберіть матеріал", df_inv['name'].tolist())
                cur_q = df_inv[df_inv['name'] == mat_adj]['qty'].iloc[0]
                new_q = cadj2.number_input(f"Нова кількість (було: {cur_q})", min_value=0.0, value=float(cur_q))
                if cadj3.button("Оновити кількість"):
                    db_conn.execute("UPDATE inventory SET qty = ? WHERE name = ?", (new_q, mat_adj))
                    db_conn.commit()
                    add_log(username, f"Змінив залишок {mat_adj} на {new_q}")
                    st.rerun()
            
            st.divider()
            c1, c2 = st.columns(2)
            with c1.expander("➕ Додати новий"):
                with st.form("add_inv"):
                    n = st.text_input("Назва")
                    q = st.number_input("Кількість", min_value=0.0)
                    p = st.number_input("Ціна закупівлі", min_value=0.0)
                    if st.form_submit_button("Зберегти"):
                        db_conn.execute("INSERT INTO inventory (name, qty, price) VALUES (?,?,?)", (n, q, p))
                        db_conn.commit()
                        st.rerun()
            with c2.expander("🗑️ Видалити позицію"):
                target = st.selectbox("Матеріал", df_inv['name'].tolist() if not df_inv.empty else [])
                if st.button("Видалити"):
                    db_conn.execute("DELETE FROM inventory WHERE name=?", (target,))
                    db_conn.commit()
                    st.rerun()

    elif choice == "📝 Нове замовлення":
        st.header("🆕 Нове замовлення")
        with st.form("n_ord"):
            c, d = st.text_input("Замовник"), st.text_input("Виріб")
            qo, po = st.number_input("Кількість", min_value=1), st.number_input("Ціна", min_value=0.0)
            if st.form_submit_button("Створити"):
                db_conn.execute("INSERT INTO orders (customer, detail, qty, price, status) VALUES (?,?,?,?,'Нове')", (c, d, qo, po))
                db_conn.commit()
                st.success("Додано!")

    elif choice == "⚙️ Персонал":
        st.header("👥 Персонал")
        all_u = pd.read_sql_query("SELECT username, role FROM users", db_conn)
        st.table(all_u)
        with st.expander("➕ Додати працівника"):
            with st.form("u_add"):
                u, p, r = st.text_input("Логін"), st.text_input("Пароль"), st.selectbox("Роль", ["Робочий", "Конструктор", "Адмін"])
                if st.form_submit_button("Створити"):
                    try:
                        db_conn.execute("INSERT INTO users (username, password, role) VALUES (?,?,?)", (u, p, r))
                        db_conn.commit()
                        st.rerun()
                    except: st.error("Логін зайнятий")

    elif choice == "📜 Журнал дій":
        st.header("📜 Журнал")
        df_l = pd.read_sql_query("SELECT timestamp, username, action FROM logs ORDER BY id DESC LIMIT 100", db_conn)
        st.dataframe(df_l, use_container_width=True)

    db_conn.close()

