import streamlit as st
import sqlite3
import pandas as pd
import os
from datetime import datetime, timedelta

# --- 1. НАЛАШТУВАННЯ СТОРІНКИ ---
st.set_page_config(page_title="Factory ERP Pro", layout="wide")

# --- 2. КОНФІГУРАЦІЯ БД ---
DB_NAME = 'factory.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY, name TEXT, qty REAL, price REAL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, customer TEXT, detail TEXT, qty INTEGER, price REAL, status TEXT, photo TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT, last_seen TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY, timestamp TIMESTAMP, username TEXT, action TEXT)')
    
    # Створюємо адміна тільки якщо таблиця порожня
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO users (username, password, role, last_seen) VALUES ('admin', 'admin123', 'Адмін', ?)", (datetime.now(),))
    conn.commit()
    conn.close()

init_db()

def add_log(username, action):
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("INSERT INTO logs (timestamp, username, action) VALUES (?, ?, ?)", 
                     (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), str(username), action))
        conn.commit()

# --- 3. АВТОРИЗАЦІЯ ---
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
    st.stop()

# Оновлення статусу "Онлайн"
with sqlite3.connect(DB_NAME) as conn:
    conn.execute("UPDATE users SET last_seen = ? WHERE username = ?", (datetime.now(), st.session_state["username"]))
    conn.commit()

# --- 4. SIDEBAR ---
user_role = st.session_state["role"]
username = st.session_state["username"]
db_conn = sqlite3.connect(DB_NAME)

st.sidebar.title(f"👤 {username}")
st.sidebar.info(f"Роль: {user_role}")

# БЛОК "ХТО ОНЛАЙН"
st.sidebar.markdown("---")
st.sidebar.subheader("🟢 Зараз у системі")
five_mins_ago = datetime.now() - timedelta(minutes=5)
online_users = pd.read_sql_query("SELECT username, role FROM users WHERE last_seen > ?", db_conn, params=(five_mins_ago,))
for _, row in online_users.iterrows():
    st.sidebar.write(f"● {row['username']} ({row['role']})")

if st.sidebar.button("Вийти"):
    st.session_state.clear()
    st.rerun()

menu = ["📊 Аналітика", "🛠 Виробництво", "📦 Склад"]
if user_role == "Адмін": menu += ["📝 Нове замовлення", "⚙️ Персонал", "📜 Журнал дій"]
choice = st.sidebar.selectbox("Меню", menu)

# --- 5. РОЗДІЛИ ---

if choice == "📦 Склад":
    st.header("📦 Склад матеріалів")
    df_inv = pd.read_sql_query("SELECT * FROM inventory", db_conn)
    st.dataframe(df_inv, use_container_width=True)

    if user_role == "Адмін":
        # ПОВЕРНУТО РЕДАГУВАННЯ
        st.subheader("📝 Швидке корегування залишків")
        if not df_inv.empty:
            c1, c2, c3 = st.columns(3)
            mat_name = c1.selectbox("Матеріал", df_inv['name'].tolist())
            cur_qty = float(df_inv[df_inv['name'] == mat_name]['qty'].values[0])
            new_qty = c2.number_input(f"Нова кількість (було: {cur_qty})", min_value=0.0, value=cur_qty)
            if c3.button("✅ Оновити"):
                db_conn.execute("UPDATE inventory SET qty = ? WHERE name = ?", (new_qty, mat_name))
                db_conn.commit()
                add_log(username, f"Змінив залишок {mat_name} на {new_qty}")
                st.rerun()
        
        st.divider()
        col1, col2 = st.columns(2)
        with col1.expander("➕ Додати позицію"):
            with st.form("add_form"):
                n = st.text_input("Назва")
                q = st.number_input("Кількість", min_value=0.0)
                p = st.number_input("Ціна", min_value=0.0)
                if st.form_submit_button("Зберегти"):
                    db_conn.execute("INSERT INTO inventory (name, qty, price) VALUES (?,?,?)", (n, q, p))
                    db_conn.commit()
                    st.rerun()
        with col2.expander("🗑️ Видалити позицію"):
            if not df_inv.empty:
                d_name = st.selectbox("Що видалити?", df_inv['name'].tolist(), key="del_sel")
                if st.button("Видалити назавжди"):
                    db_conn.execute("DELETE FROM inventory WHERE name=?", (d_name,))
                    db_conn.commit()
                    st.rerun()

elif choice == "🛠 Виробництво":
    st.header("📋 Журнал виробництва")
    df_orders = pd.read_sql_query("SELECT * FROM orders ORDER BY id DESC", db_conn)
    for _, row in df_orders.iterrows():
        with st.expander(f"📦 №{row['id']} | {row['customer']} | {row['detail']} ({row['status']})"):
            st.write(f"Кількість: {row['qty']} | Ціна: {row['price']} грн")
            statuses = ["Нове", "Обробка", "Готово"]
            new_s = st.selectbox("Змінити статус", statuses, index=statuses.index(row['status']) if row['status'] in statuses else 0, key=f"ord_{row['id']}")
            if st.button("Зберегти", key=f"btn_{row['id']}"):
                db_conn.execute("UPDATE orders SET status=? WHERE id=?", (new_s, row['id']))
                db_conn.commit()
                add_log(username, f"Замовлення №{row['id']} -> {new_s}")
                st.rerun()

elif choice == "📊 Аналітика":
    st.header("📈 Фінанси")
    inv_val = pd.read_sql_query("SELECT SUM(qty * price) as s FROM inventory", db_conn)['s'].iloc[0] or 0
    ord_val = pd.read_sql_query("SELECT SUM(qty * price) as s FROM orders WHERE status != 'Готово'", db_conn)['s'].iloc[0] or 0
    st.columns(2)[0].metric("Склад", f"{inv_val:,.2f} грн")
    st.columns(2)[1].metric("В роботі", f"{ord_val:,.2f} грн")

elif choice == "📝 Нове замовлення":
    st.header("🆕 Нове замовлення")
    with st.form("new_o"):
        c, d = st.text_input("Замовник"), st.text_input("Виріб")
        qo, po = st.number_input("Кількість", min_value=1), st.number_input("Ціна за од.", min_value=0.0)
        if st.form_submit_button("Створити"):
            db_conn.execute("INSERT INTO orders (customer, detail, qty, price, status) VALUES (?,?,?,?,'Нове')", (c, d, qo, po))
            db_conn.commit()
            st.success("Додано!")

elif choice == "⚙️ Персонал":
    st.header("👥 Персонал")
    st.table(pd.read_sql_query("SELECT username, role FROM users", db_conn))
    with st.expander("➕ Додати працівника"):
        u = st.text_input("Логін")
        p = st.text_input("Пароль")
        r = st.selectbox("Роль", ["Робочий", "Конструктор", "Адмін"])
        if st.button("Створити"):
            try:
                db_conn.execute("INSERT INTO users (username, password, role, last_seen) VALUES (?,?,?,?)", (u, p, r, datetime.now()))
                db_conn.commit()
                st.rerun()
            except: st.error("Помилка (логін зайнятий)")

elif choice == "📜 Журнал дій":
    st.header("📜 Журнал")
    st.dataframe(pd.read_sql_query("SELECT timestamp, username, action FROM logs ORDER BY id DESC LIMIT 100", db_conn), use_container_width=True)

db_conn.close()

