import streamlit as st
import sqlite3
import pandas as pd
import os
from datetime import datetime, timedelta

# --- 1. НАЛАШТУВАННЯ СТОРІНКИ ---
st.set_page_config(page_title="Factory ERP Pro", layout="wide")

# --- 2. КОНФІГУРАЦІЯ ТА ПАПКИ ---
DB_NAME = 'factory.db'
UPLOAD_DIR = 'files'
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# --- 3. ІНІЦІАЛІЗАЦІЯ БД (З ВИПРАВЛЕННЯМ ПОМИЛКИ) ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Створюємо основні таблиці
    cursor.execute('CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY, name TEXT, qty REAL, price REAL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, customer TEXT, detail TEXT, qty INTEGER, price REAL, status TEXT, file_path TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT, last_seen TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY, timestamp TIMESTAMP, username TEXT, action TEXT)')
    
    # --- ВИПРАВЛЕННЯ ПОМИЛКИ ТУТ ---
    # Спробуємо додати колонку file_path, якщо її немає (для старих БД)
    try:
        cursor.execute('ALTER TABLE orders ADD COLUMN file_path TEXT')
    except sqlite3.OperationalError:
        pass # Колонка вже існує, нічого не робимо
    # -------------------------------

    # Створюємо адміна за замовчуванням
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

# --- 4. АВТОРИЗАЦІЯ ---
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

# --- 5. SIDEBAR ---
user_role = st.session_state["role"]
username = st.session_state["username"]
db_conn = sqlite3.connect(DB_NAME)

st.sidebar.title(f"👤 {username}")
st.sidebar.info(f"Роль: {user_role}")

# Список онлайн
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
if user_role == "Адмін": 
    menu += ["📝 Нове замовлення", "⚙️ Персонал", "📜 Журнал дій"]
choice = st.sidebar.selectbox("Меню", menu)

# --- 6. РОЗДІЛИ ---

if choice == "📦 Склад":
    st.header("📦 Склад матеріалів")
    query = "SELECT name, qty, price FROM inventory" if user_role == "Адмін" else "SELECT name, qty FROM inventory"
    df_inv = pd.read_sql_query(query, db_conn)
    st.dataframe(df_inv, use_container_width=True)

    if user_role == "Адмін":
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

elif choice == "🛠 Виробництво":
    st.header("📋 Журнал виробництва")
    df_orders = pd.read_sql_query("SELECT * FROM orders ORDER BY id DESC", db_conn)
    for _, row in df_orders.iterrows():
        status_color = "🟢" if row['status'] == "Готово" else "🟡" if row['status'] == "Обробка" else "⚪"
        with st.expander(f"{status_color} №{row['id']} | {row['customer']} | {row['detail']}"):
            c1, c2 = st.columns(2)
            with c1:
                st.write(f"**Кількість:** {row['qty']} шт.")
                if row['file_path'] and os.path.exists(row['file_path']):
                    file_name = os.path.basename(row['file_path'])
                    with open(row['file_path'], "rb") as f:
                        st.download_button(f"📥 Скачати: {file_name}", f, file_name=file_name, key=f"dl_{row['id']}")
                else:
                    st.info("Тех. документація відсутня")
                
                if user_role == "Адмін":
                    st.write(f"**Ціна:** {row['price']} грн")
            with c2:
                statuses = ["Нове", "Обробка", "Готово"]
                idx = statuses.index(row['status']) if row['status'] in statuses else 0
                new_s = st.selectbox("Статус", statuses, index=idx, key=f"ord_{row['id']}")
                if st.button("Оновити статус", key=f"btn_{row['id']}"):
                    db_conn.execute("UPDATE orders SET status=? WHERE id=?", (new_s, row['id']))
                    db_conn.commit()
                    add_log(username, f"Замовлення №{row['id']} -> {new_s}")
                    st.rerun()

elif choice == "📊 Аналітика":
    st.header("📈 Фінансова аналітика")
    if user_role == "Адмін":
        inv_val = pd.read_sql_query("SELECT SUM(qty * price) as s FROM inventory", db_conn)['s'].iloc[0] or 0
        ord_val = pd.read_sql_query("SELECT SUM(qty * price) as s FROM orders WHERE status != 'Готово'", db_conn)['s'].iloc[0] or 0
        st.columns(2)[0].metric("Склад", f"{inv_val:,.2f} грн")
        st.columns(2)[1].metric("В роботі", f"{ord_val:,.2f} грн")
    else:
        st.warning("Доступ обмежений")

elif choice == "📝 Нове замовлення" and user_role == "Адмін":
    st.header("🆕 Реєстрація замовлення")
    with st.form("new_o", clear_on_submit=True):
        c, d = st.text_input("Замовник"), st.text_input("Виріб")
        qo, po = st.number_input("Кількість", min_value=1), st.number_input("Ціна продажу", min_value=0.0)
        uploaded_file = st.file_uploader("Завантажити креслення (PNG, PDF, TXT, SolidWorks, NC)", type=["png", "pdf", "txt", "bin", "sldprt", "sldasm", "slddrw", "nc", "tap"])
        
        if st.form_submit_button("Додати"):
            file_path = None
            if uploaded_file:
                file_path = os.path.join(UPLOAD_DIR, uploaded_file.name)
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
            
            db_conn.execute("INSERT INTO orders (customer, detail, qty, price, status, file_path) VALUES (?,?,?,?,'Нове',?)", 
                            (c, d, qo, po, file_path))
            db_conn.commit()
            add_log(username, f"Нове замовлення: {c}")
            st.success("Успішно додано!")

elif choice == "⚙️ Персонал" and user_role == "Адмін":
    st.header("👥 Персонал")
    st.table(pd.read_sql_query("SELECT username, role FROM users", db_conn))
    with st.expander("➕ Реєстрація"):
        with st.form("u_reg"):
            u, p, r = st.text_input("Логін"), st.text_input("Пароль"), st.selectbox("Роль", ["Робочий", "Конструктор", "Адмін"])
            if st.form_submit_button("Створити"):
                try:
                    db_conn.execute("INSERT INTO users (username, password, role, last_seen) VALUES (?,?,?,?)", (u, p, r, datetime.now()))
                    db_conn.commit()
                    st.rerun()
                except: st.error("Логін зайнятий")

elif choice == "📜 Журнал дій" and user_role == "Адмін":
    st.header("📜 Журнал")
    st.dataframe(pd.read_sql_query("SELECT timestamp, username, action FROM logs ORDER BY id DESC LIMIT 100", db_conn), use_container_width=True)

db_conn.close()
