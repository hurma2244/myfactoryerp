import streamlit as st
import sqlite3
import pandas as pd
import os
import shutil
from datetime import datetime, timedelta

# --- 1. НАСТРОЙКИ СТРАНИЦЫ ---
st.set_page_config(page_title="Factory ERP Pro", layout="wide")

# --- 2. КОНФИГУРАЦИЯ ---
DB_NAME = 'factory.db'
UPLOAD_DIR = 'order_files'
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# --- 3. ИНИЦИАЛИЗАЦИЯ БД ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY, name TEXT, qty REAL, price REAL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, customer TEXT, detail TEXT, qty INTEGER, price REAL, status TEXT, file_path TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT, last_seen TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY, timestamp TIMESTAMP, username TEXT, action TEXT)')
    
    try:
        cursor.execute('ALTER TABLE orders ADD COLUMN file_path TEXT')
    except sqlite3.OperationalError:
        pass

    # Принудительный сброс пароля админа для входа
    cursor.execute("INSERT OR REPLACE INTO users (username, password, role, last_seen) VALUES ('admin', 'admin123', 'Адмін', ?)", (datetime.now(),))
    conn.commit()
    conn.close()

init_db()

def add_log(username, action):
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("INSERT INTO logs (timestamp, username, action) VALUES (?, ?, ?)", 
                     (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), str(username), action))
        conn.commit()

# --- 4. АВТОРИЗАЦИЯ ---
if "authenticated" not in st.session_state:
    st.title("🏭 ERP Система Заводу")
    u_in = st.text_input("Логін").strip()
    p_in = st.text_input("Пароль", type="password").strip()
    if st.button("Увійти"):
        with sqlite3.connect(DB_NAME) as conn:
            res = conn.execute("SELECT username, role FROM users WHERE username=? AND password=?", (u_in, p_in)).fetchone()
            if res:
                st.session_state["authenticated"] = True
                st.session_state["username"] = res[0]
                st.session_state["role"] = res[1]
                add_log(res[0], "Увійшов у систему")
                st.rerun()
            else:
                st.error("❌ Невірний логін або пароль")
    st.stop()

# Обновление онлайна
with sqlite3.connect(DB_NAME) as conn:
    conn.execute("UPDATE users SET last_seen = ? WHERE username = ?", (datetime.now(), st.session_state["username"]))
    conn.commit()

# --- 5. ИНТЕРФЕЙС ---
user_role = st.session_state["role"]
username = st.session_state["username"]
db_conn = sqlite3.connect(DB_NAME)

st.sidebar.title(f"👤 {username}")
st.sidebar.info(f"Роль: {user_role}")

st.sidebar.subheader("🟢 Онлайн")
five_mins_ago = datetime.now() - timedelta(minutes=5)
online_users = pd.read_sql_query("SELECT username FROM users WHERE last_seen > ?", db_conn, params=(five_mins_ago,))
for u in online_users['username']:
    st.sidebar.write(f"● {u}")

if st.sidebar.button("Вийти"):
    st.session_state.clear()
    st.rerun()

menu = ["📊 Аналітика", "🛠 Виробництво", "📦 Склад"]
if user_role == "Адмін": menu += ["📝 Нове замовлення", "⚙️ Персонал", "📜 Журнал дій"]
choice = st.sidebar.selectbox("Меню", menu)

# --- ЛОГИКА РАЗДЕЛОВ ---

if choice == "📊 Аналітика":
    st.header("📈 Фінанси")
    if user_role == "Адмін":
        t_inv = pd.read_sql_query("SELECT SUM(qty * price) as s FROM inventory", db_conn)['s'].iloc[0] or 0
        t_ord = pd.read_sql_query("SELECT SUM(qty * price) as s FROM orders WHERE status != 'Готово'", db_conn)['s'].iloc[0] or 0
        st.metric("Вартість складу", f"{t_inv:,.2f} грн")
        st.metric("В роботі", f"{t_ord:,.2f} грн")
    else: st.warning("Доступ обмежено")

elif choice == "🛠 Виробництво":
    st.header("📋 Виробництво")
    df_orders = pd.read_sql_query("SELECT * FROM orders ORDER BY id DESC", db_conn)
    for _, row in df_orders.iterrows():
        with st.expander(f"📦 №{row['id']} | {row['customer']} | {row['detail']} ({row['status']})"):
            c1, c2 = st.columns(2)
            with c1:
                st.write(f"Кількість: {row['qty']} шт.")
                if row['file_path'] and os.path.exists(row['file_path']):
                    if os.path.isdir(row['file_path']):
                        for f_name in os.listdir(row['file_path']):
                            f_p = os.path.join(row['file_path'], f_name)
                            with open(f_p, "rb") as fb:
                                st.download_button(f"📥 {f_name}", fb, file_name=f_name, key=f"dl_{row['id']}_{f_name}")
                    else:
                        f_n = os.path.basename(row['file_path'])
                        with open(row['file_path'], "rb") as fb:
                            st.download_button(f"📥 {f_n}", fb, file_name=f_n, key=f"dl_s_{row['id']}")
                if user_role == "Адмін":
                    st.write(f"Ціна: {row['price']} грн")
                    if st.button("🗑️ ВИДАЛИТИ ЗАМОВЛЕННЯ", key=f"del_{row['id']}"):
                        if row['file_path'] and os.path.exists(row['file_path']):
                            if os.path.isdir(row['file_path']): shutil.rmtree(row['file_path'])
                            else: os.remove(row['file_path'])
                        db_conn.execute("DELETE FROM orders WHERE id=?", (row['id'],))
                        db_conn.commit()
                        st.rerun()
            with c2:
                statuses = ["Нове", "Обробка", "Готово"]
                idx = statuses.index(row['status']) if row['status'] in statuses else 0
                new_s = st.selectbox("Статус", statuses, index=idx, key=f"st_{row['id']}")
                if st.button("Зберегти", key=f"bt_{row['id']}"):
                    db_conn.execute("UPDATE orders SET status=? WHERE id=?", (new_s, row['id']))
                    db_conn.commit()
                    st.rerun()

elif choice == "📦 Склад":
    st.header("📦 Склад матеріалів")
    query = "SELECT name, qty, price FROM inventory" if user_role == "Адмін" else "SELECT name, qty FROM inventory"
    df_inv = pd.read_sql_query(query, db_conn)
    st.dataframe(df_inv, use_container_width=True)

    if user_role == "Адмін":
        st.subheader("📝 Швидке корегування залишків")
        if not df_inv.empty:
            c1, c2, c3 = st.columns(3)
            mat_name = c1.selectbox("Оберіть матеріал", df_inv['name'].tolist())
            cur_qty = float(df_inv[df_inv['name'] == mat_name]['qty'].iloc[0])
            new_qty = c2.number_input(f"Нова к-ть (було {cur_qty})", value=cur_qty)
            if c3.button("✅ Оновити"):
                db_conn.execute("UPDATE inventory SET qty=? WHERE name=?", (new_qty, mat_name))
                db_conn.commit()
                st.rerun()

        st.divider()
        col1, col2 = st.columns(2)
        with col1.expander("➕ Додати позицію"):
            with st.form("add_mat"):
                n = st.text_input("Назва")
                q = st.number_input("Кількість", min_value=0.0)
                p = st.number_input("Ціна закупки", min_value=0.0)
                if st.form_submit_button("Зберегти"):
                    db_conn.execute("INSERT INTO inventory (name, qty, price) VALUES (?,?,?)", (n, q, p))
                    db_conn.commit()
                    st.rerun()
        with col2.expander("🗑️ Видалити позицію"):
            if not df_inv.empty:
                to_del = st.selectbox("Матеріал для видалення", df_inv['name'].tolist(), key="del_s")
                if st.button("🚨 Видалити остаточно"):
                    db_conn.execute("DELETE FROM inventory WHERE name=?", (to_del,))
                    db_conn.commit()
                    st.rerun()

elif choice == "📝 Нове замовлення" and user_role == "Адмін":
    st.header("🆕 Нове замовлення")
    with st.form("new_order", clear_on_submit=True):
        c, d = st.text_input("Замовник"), st.text_input("Виріб")
        qo, po = st.number_input("Кількість", min_value=1), st.number_input("Ціна продажу", min_value=0.0)
        uploaded_files = st.file_uploader("Файли (SW, PDF, NC...)", accept_multiple_files=True)
        if st.form_submit_button("Створити"):
            order_path = None
            if uploaded_files:
                order_path = os.path.join(UPLOAD_DIR, f"order_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                os.makedirs(order_path)
                for f in uploaded_files:
                    with open(os.path.join(order_path, f.name), "wb") as fs:
                        fs.write(f.getbuffer())
            db_conn.execute("INSERT INTO orders (customer, detail, qty, price, status, file_path) VALUES (?,?,?,?,'Нове',?)", (c, d, qo, po, order_path))
            db_conn.commit()
            st.success("Додано!")

elif choice == "⚙️ Персонал" and user_role == "Адмін":
    st.header("👥 Персонал")
    st.table(pd.read_sql_query("SELECT username, role FROM users", db_conn))
    with st.form("u_add"):
        u, p, r = st.text_input("Логін"), st.text_input("Пароль"), st.selectbox("Роль", ["Робочий", "Конструктор", "Адмін"])
        if st.form_submit_button("Додати"):
            try:
                db_conn.execute("INSERT INTO users (username, password, role, last_seen) VALUES (?,?,?,?)", (u, p, r, datetime.now()))
                db_conn.commit()
                st.rerun()
            except: st.error("Логін зайнятий")

elif choice == "📜 Журнал дій" and user_role == "Адмін":
    st.header("📜 Журнал")
    st.dataframe(pd.read_sql_query("SELECT * FROM logs ORDER BY id DESC LIMIT 100", db_conn), use_container_width=True)

db_conn.close()

