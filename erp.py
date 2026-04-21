import streamlit as st
import sqlite3
import pandas as pd
import os
from datetime import datetime

# --- 1. НАЛАШТУВАННЯ СТОРІНКИ ---
st.set_page_config(page_title="Factory ERP Pro", layout="wide")

# --- 2. КОНФІГУРАЦІЯ ТА БД ---
DB_NAME = 'factory.db'

def init_db():
    # З'єднуємося з базою. Якщо файлу немає, він створиться автоматично.
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Створюємо таблиці лише якщо їх ще не існує
    cursor.execute('CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY, name TEXT, qty REAL, price REAL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, customer TEXT, detail TEXT, qty INTEGER, price REAL, status TEXT, photo TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT, last_seen TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY, timestamp TIMESTAMP, username TEXT, action TEXT)')
    
    # Створюємо адміна тільки якщо таблиця користувачів порожня
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO users (username, password, role) VALUES ('admin', 'admin123', 'Адмін')")
    
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

# --- 4. ОСНОВНИЙ ІНТЕРФЕЙС ---
user_role = st.session_state["role"]
username = st.session_state["username"]
db_conn = sqlite3.connect(DB_NAME)

st.sidebar.title(f"👤 {username}")
st.sidebar.info(f"Роль: {user_role}")
if st.sidebar.button("Вийти"):
    st.session_state.clear()
    st.rerun()

menu = ["📊 Аналітика", "🛠 Виробництво", "📦 Склад"]
if user_role == "Адмін": menu += ["📝 Нове замовлення", "⚙️ Персонал", "📜 Журнал дій"]
choice = st.sidebar.selectbox("Меню", menu)

# --- 📦 РОЗДІЛ СКЛАД (З РЕДАГУВАННЯМ) ---
if choice == "📦 Склад":
    st.header("📦 Склад матеріалів")
    df_inv = pd.read_sql_query("SELECT * FROM inventory", db_conn)
    st.dataframe(df_inv, use_container_width=True)

    if user_role == "Адмін":
        st.subheader("📝 Швидке корегування залишків")
        if not df_inv.empty:
            c_adj1, c_adj2, c_adj3 = st.columns(3)
            # Вибір матеріалу
            mat_to_adj = c_adj1.selectbox("Оберіть матеріал", df_inv['name'].tolist(), key="adj_sel")
            # Поточна кількість
            current_qty = df_inv[df_inv['name'] == mat_to_adj]['qty'].values[0]
            # Поле для нової кількості
            new_qty = c_adj2.number_input(f"Кількість (зараз: {current_qty})", min_value=0.0, value=float(current_qty))
            
            if c_adj3.button("✅ Оновити"):
                db_conn.execute("UPDATE inventory SET qty = ? WHERE name = ?", (new_qty, mat_to_adj))
                db_conn.commit()
                add_log(username, f"Змінив залишок {mat_to_adj} на {new_qty}")
                st.success("Оновлено!")
                st.rerun()

        st.divider()
        col1, col2 = st.columns(2)
        with col1.expander("➕ Додати нову позицію"):
            with st.form("new_mat"):
                n = st.text_input("Назва")
                q = st.number_input("Початкова кількість", min_value=0.0)
                p = st.number_input("Ціна закупівлі", min_value=0.0)
                if st.form_submit_button("Зберегти"):
                    db_conn.execute("INSERT INTO inventory (name, qty, price) VALUES (?,?,?)", (n, q, p))
                    db_conn.commit()
                    add_log(username, f"Додав на склад: {n}")
                    st.rerun()
        
        with col2.expander("🗑️ Видалити позицію"):
            if not df_inv.empty:
                to_del = st.selectbox("Що видалити?", df_inv['name'].tolist())
                if st.button("Видалити назавжди"):
                    db_conn.execute("DELETE FROM inventory WHERE name=?", (to_del,))
                    db_conn.commit()
                    add_log(username, f"Видалив позицію: {to_del}")
                    st.rerun()

# --- 🛠 ВИРОБНИЦТВО ---
elif choice == "🛠 Виробництво":
    st.header("📋 Журнал виробництва")
    df_orders = pd.read_sql_query("SELECT * FROM orders ORDER BY id DESC", db_conn)
    for _, row in df_orders.iterrows():
        with st.expander(f"📦 №{row['id']} | {row['customer']} | {row['detail']} ({row['status']})"):
            st.write(f"Кількість: {row['qty']} | Ціна: {row['price']} грн")
            statuses = ["Нове", "Обробка", "Готово"]
            idx = statuses.index(row['status']) if row['status'] in statuses else 0
            new_s = st.selectbox("Змінити статус", statuses, index=idx, key=f"status_{row['id']}")
            if st.button("Зберегти статус", key=f"btn_{row['id']}"):
                db_conn.execute("UPDATE orders SET status=? WHERE id=?", (new_s, row['id']))
                db_conn.commit()
                add_log(username, f"Замовлення №{row['id']} -> {new_s}")
                st.rerun()

# --- 📊 АНАЛІТИКА ---
elif choice == "📊 Аналітика":
    st.header("📈 Фінансова аналітика")
    total_inv = pd.read_sql_query("SELECT SUM(qty * price) as s FROM inventory", db_conn)['s'].iloc[0] or 0
    total_ord = pd.read_sql_query("SELECT SUM(qty * price) as s FROM orders WHERE status != 'Готово'", db_conn)['s'].iloc[0] or 0
    c1, c2 = st.columns(2)
    c1.metric("Капітал у складі", f"{total_inv:,.2f} грн")
    c2.metric("Очікуваний дохід", f"{total_ord:,.2f} грн")

# --- 📝 НОВЕ ЗАМОВЛЕННЯ ---
elif choice == "📝 Нове замовлення":
    st.header("🆕 Нове замовлення")
    with st.form("order_form"):
        cust = st.text_input("Клієнт")
        det = st.text_input("Виріб")
        q_o = st.number_input("Кількість", min_value=1)
        p_o = st.number_input("Ціна продажу", min_value=0.0)
        if st.form_submit_button("Додати"):
            db_conn.execute("INSERT INTO orders (customer, detail, qty, price, status) VALUES (?,?,?,?,'Нове')", (cust, det, q_o, p_o))
            db_conn.commit()
            add_log(username, f"Нове замовлення: {cust}")
            st.success("Додано!")

# --- ⚙️ ПЕРСОНАЛ ---
elif choice == "⚙️ Персонал":
    st.header("👥 Персонал")
    users = pd.read_sql_query("SELECT username, role FROM users", db_conn)
    st.table(users)
    with st.expander("➕ Додати користувача"):
        u = st.text_input("Логін")
        p = st.text_input("Пароль")
        r = st.selectbox("Роль", ["Робочий", "Конструктор", "Адмін"])
        if st.button("Створити акаунт"):
            try:
                db_conn.execute("INSERT INTO users (username, password, role) VALUES (?,?,?)", (u, p, r))
                db_conn.commit()
                st.success("Готово")
                st.rerun()
            except: st.error("Помилка (можливо, логін зайнятий)")

# --- 📜 ЖУРНАЛ ДІЙ ---
elif choice == "📜 Журнал дій":
    st.header("📜 Журнал усіх подій")
    logs = pd.read_sql_query("SELECT timestamp, username, action FROM logs ORDER BY id DESC LIMIT 200", db_conn)
    st.dataframe(logs, use_container_width=True)

db_conn.close()

