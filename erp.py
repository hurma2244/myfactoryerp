import streamlit as st
import sqlite3
import pandas as pd
import os
import requests
from datetime import datetime, timedelta

# --- 1. НАЛАШТУВАННЯ СТОРІНКИ ---
st.set_page_config(page_title="Factory ERP Pro (Safe Mode)", layout="wide")

DB_NAME = 'factory.db'
TG_TOKEN = "8743391673:AAGPXg-5-87Y881bO5XWhftEPPugKNK4y88"
TG_CHAT_ID = "-1003848428987"

# --- 2. СИСТЕМА БЕКАПІВ ТА ПОВІДОМЛЕНЬ ---
def send_db_backup():
    """Відправляє файл бази даних у Telegram"""
    url = f"https://telegram.org{TG_TOKEN}/sendDocument"
    try:
        with open(DB_NAME, 'rb') as f:
            requests.post(url, data={'chat_id': TG_CHAT_ID, 'caption': f"📦 Авто-бекап: {datetime.now().strftime('%d.%m %H:%M')}"}, files={'document': f})
    except: pass

def send_file_to_tg(file_bytes, file_name, caption):
    """Відправляє креслення у Telegram"""
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
    st.title("🏭 ERP Система (SQLite + TG Backup)")
    
    with st.expander("🔄 ВІДНОВИТИ ДАНІ (якщо база зникла)"):
        st.info("Завантажте останній файл factory.db з вашого Telegram-каналу")
        up_db = st.file_uploader("Виберіть файл .db", type="db")
        if up_db and st.button("Завантажити та відновити"):
            with open(DB_NAME, "wb") as f:
                f.write(up_db.getbuffer())
            st.success("Базу успішно відновлено! Перезавантажте сторінку.")
            st.stop()

    u = st.text_input("Логін").strip()
    p = st.text_input("Пароль", type="password").strip()
    if st.button("Увійти"):
        conn = sqlite3.connect(DB_NAME)
        res = conn.execute("SELECT username, role FROM users WHERE username=? AND password=?", (u, p)).fetchone()
        if res:
            st.session_state["auth"], st.session_state["user"], st.session_state["role"] = True, res[0], res[1]
            st.rerun()
        else: st.error("❌ Невірний логін або пароль")
    st.stop()

# Оновлення активності онлайн
with sqlite3.connect(DB_NAME) as conn:
    conn.execute("UPDATE users SET last_seen = ? WHERE username = ?", (datetime.now(), st.session_state["user"]))
    conn.commit()

# --- 5. SIDEBAR ТА ОНЛАЙН ---
user_role = st.session_state["role"]
username = st.session_state["user"]
db_conn = sqlite3.connect(DB_NAME)

st.sidebar.title(f"👤 {username}")
st.sidebar.info(f"Роль: {user_role}")

# Список онлайн
st.sidebar.subheader("🟢 Зараз у системі")
five_mins_ago = datetime.now() - timedelta(minutes=5)
online_users = pd.read_sql_query("SELECT username, role FROM users WHERE last_seen > ?", db_conn, params=(five_mins_ago,))
for _, row in online_users.iterrows():
    st.sidebar.write(f"● {row['username']} ({row['role']})")

if st.sidebar.button("Вийти з системи"):
    st.session_state.clear()
    st.rerun()

menu = ["📊 Аналітика", "🛠 Виробництво", "📦 Склад"]
if user_role == "Адмін": menu += ["📝 Нове замовлення", "⚙️ Персонал"]
choice = st.sidebar.selectbox("Меню", menu)

# --- 6. РОЗДІЛИ ---

# --- СКЛАД (З усіма функціями) ---
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
            new_qty = c2.number_input("Нова кількість", value=cur_qty)
            if c3.button("✅ Оновити"):
                db_conn.execute("UPDATE inventory SET qty=? WHERE name=?", (new_qty, mat_name))
                db_conn.commit()
                send_db_backup()
                st.rerun()
        
        col1, col2 = st.columns(2)
        with col1.expander("➕ Додати нову позицію"):
            with st.form("add_mat"):
                n, q, p = st.text_input("Назва"), st.number_input("К-ть", min_value=0.0), st.number_input("Ціна")
                if st.form_submit_button("Зберегти"):
                    db_conn.execute("INSERT INTO inventory (name, qty, price) VALUES (?,?,?)", (n, q, p))
                    db_conn.commit()
                    send_db_backup()
                    st.rerun()
        with col2.expander("🗑️ Видалити позицію"):
            if not df_inv.empty:
                to_del = st.selectbox("Що видалити?", df_inv['name'].tolist())
                if st.button("🚨 Видалити назавжди"):
                    db_conn.execute("DELETE FROM inventory WHERE name=?", (to_del,))
                    db_conn.commit()
                    send_db_backup()
                    st.rerun()

# --- ПЕРСОНАЛ ---
elif choice == "⚙️ Персонал" and user_role == "Адмін":
    st.header("👥 Керування персоналом")
    df_users = pd.read_sql_query("SELECT username, role FROM users", db_conn)
    st.table(df_users)
    
    c1, c2 = st.columns(2)
    with c1.expander("➕ Додати працівника"):
        with st.form("u_add"):
            u, p, r = st.text_input("Логін"), st.text_input("Пароль"), st.selectbox("Роль", ["Робочий", "Конструктор", "Адмін"])
            if st.form_submit_button("Створити"):
                try:
                    db_conn.execute("INSERT INTO users VALUES (?,?,?,?)", (u, p, r, datetime.now()))
                    db_conn.commit()
                    send_db_backup()
                    st.rerun()
                except: st.error("Логін зайнятий")
    with c2.expander("📝 Редагувати / Видалити"):
        target = st.selectbox("Користувач", df_users['username'].tolist())
        if target != 'admin':
            new_role = st.selectbox("Нова роль", ["Робочий", "Конструктор", "Адмін"], key="nr")
            if st.button("💾 Зберегти зміни"):
                db_conn.execute("UPDATE users SET role=? WHERE username=?", (new_role, target))
                db_conn.commit()
                send_db_backup()
                st.rerun()
            if st.button("🗑️ Видалити акаунт"):
                db_conn.execute("DELETE FROM users WHERE username=?", (target,))
                db_conn.commit()
                send_db_backup()
                st.rerun()

# --- АНАЛІТИКА ---
elif choice == "📊 Аналітика" and user_role == "Адмін":
    st.header("📈 Аналітика")
    total_inv = pd.read_sql_query("SELECT SUM(qty * price) as s FROM inventory", db_conn)['s'].iloc[0] or 0
    total_ord = pd.read_sql_query("SELECT SUM(qty * price) as s FROM orders WHERE status != 'Готово'", db_conn)['s'].iloc[0] or 0
    c1, c2 = st.columns(2)
    c1.metric("Капітал на складі", f"{total_inv:,.2f} грн")
    c2.metric("Очікуваний дохід", f"{total_ord:,.2f} грн")

# --- НОВЕ ЗАМОВЛЕННЯ ---
elif choice == "📝 Нове замовлення" and user_role == "Адмін":
    st.header("🆕 Нове замовлення")
    with st.form("n_ord", clear_on_submit=True):
        c, d, q, p = st.text_input("Клієнт"), st.text_input("Деталь"), st.number_input("К-ть", min_value=1), st.number_input("Ціна")
        files = st.file_uploader("Креслення", accept_multiple_files=True)
        if st.form_submit_button("Створити"):
            has_f = False
            if files:
                has_f = True
                for f in files: send_file_to_tg(f.getvalue(), f.name, f"🆕 Замовлення {c}: {d}")
            db_conn.execute("INSERT INTO orders (customer, detail, qty, price, status, has_files) VALUES (?,?,?,?,'Нове',?)", (c, d, q, p, has_f))
            db_conn.commit()
            send_db_backup()
            st.success("✅ Створено! Базу збережено.")

# --- ВИРОБНИЦТВО ---
elif choice == "🛠 Виробництво":
    st.header("🛠 Виробництво")
    df_o = pd.read_sql_query("SELECT * FROM orders ORDER BY id DESC", db_conn)
    for _, row in df_o.iterrows():
        with st.expander(f"📦 №{row['id']} | {row['customer']} | {row['detail']} ({row['status']})"):
            c1, c2 = st.columns(2)
            with c1:
                st.write(f"Кількість: {row['qty']} шт.")
                if row['has_files']: st.info("📂 Файли в Telegram")
                if user_role == "Адмін": 
                    st.write(f"Ціна: {row['price']} грн")
                    if st.button("🗑️ Видалити", key=f"del{row['id']}"):
                        db_conn.execute("DELETE FROM orders WHERE id=?", (row['id'],))
                        db_conn.commit()
                        send_db_backup()
                        st.rerun()
            with c2:
                new_s = st.selectbox("Статус", ["Нове", "Обробка", "Готово"], index=["Нове", "Обробка", "Готово"].index(row['status']), key=f"s{row['id']}")
                if st.button("💾 Оновити", key=f"b{row['id']}"):
                    db_conn.execute("UPDATE orders SET status=? WHERE id=?", (new_s, row['id']))
                    db_conn.commit()
                    send_db_backup()
                    st.rerun()

db_conn.close()
