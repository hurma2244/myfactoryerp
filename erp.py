import streamlit as st
import sqlite3
import pandas as pd
import os
import requests
from datetime import datetime, timedelta

# --- 1. КОНФІГУРАЦІЯ ---
st.set_page_config(page_title="Factory ERP Pro (Safe Mode)", layout="wide")

DB_NAME = 'factory.db'
TG_TOKEN = "8743391673:AAGPXg-5-87Y881bO5XWhftEPPugKNK4y88"
TG_CHAT_ID = "-1003964597358"

# --- 2. ФУНКЦІЇ TELEGRAM (ЗАХИСТ ВІД ПОМИЛОК) ---
def send_db_backup():
    """Надсилає актуальну базу в Telegram, збираючи адресу по частинах"""
    p1, p2, p3 = "https://api.", "telegram.org/bot", "/sendDocument"
    full_url = f"{p1}{p2}{TG_TOKEN}{p3}"
    try:
        if os.path.exists(DB_NAME):
            with open(DB_NAME, 'rb') as f:
                r = requests.post(
                    full_url, 
                    data={'chat_id': TG_CHAT_ID, 'caption': f"📦 Backup: {datetime.now().strftime('%d.%m %H:%M')}"}, 
                    files={'document': f},
                    timeout=15
                )
            if r.status_code == 200: return True, "Успішно"
            else: return False, f"Помилка {r.status_code}: {r.text}"
        return False, "Файл бази не знайдено"
    except Exception as e: return False, str(e)

def send_file_to_tg(file_bytes, file_name, caption):
    """Надсилає креслення у Telegram"""
    p1, p2, p3 = "https://api.", "telegram.org/bot", "/sendDocument"
    full_url = f"{p1}{p2}{TG_TOKEN}{p3}"
    try:
        requests.post(full_url, data={'chat_id': TG_CHAT_ID, 'caption': caption}, files={'document': (file_name, file_bytes)})
    except: pass

# --- 3. ІНІЦІАЛІЗАЦІЯ БД ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY, name TEXT, qty REAL, price REAL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, customer TEXT, detail TEXT, qty INTEGER, price REAL, status TEXT, has_files BOOLEAN)')
    cursor.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT, last_seen TIMESTAMP)')
    
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone() == 0:
        cursor.execute("INSERT INTO users VALUES ('admin', 'admin123', 'Адмін', ?)", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))
    conn.commit()
    conn.close()

init_db()

# --- 4. АВТОРИЗАЦІЯ ТА ВІДНОВЛЕННЯ ---
if "auth" not in st.session_state:
    st.title("🏭 ERP Factory (Safe Mode)")
    
    with st.expander("🔄 ВІДНОВИТИ ДАНІ (якщо база зникла)"):
        st.info("Завантажте останній файл factory.db з вашого Telegram-каналу")
        up_db = st.file_uploader("Виберіть файл .db", type="db")
        if up_db and st.button("Завантажити та відновити"):
            with open(DB_NAME, "wb") as f: f.write(up_db.getbuffer())
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
db_conn = sqlite3.connect(DB_NAME)
db_conn.execute("UPDATE users SET last_seen = ? WHERE username = ?", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), st.session_state["user"]))
db_conn.commit()

# --- 5. SIDEBAR ТА ОНЛАЙН ---
user_role = st.session_state["role"]
username = st.session_state["user"]

st.sidebar.title(f"👤 {username}")
st.sidebar.info(f"Роль: {user_role}")

# Список онлайн (Виправлено)
st.sidebar.subheader("🟢 Зараз у системі")
five_mins_ago = (datetime.now() - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
try:
    online_data = pd.read_sql_query("SELECT username FROM users WHERE last_seen > ?", db_conn, params=(five_mins_ago,))
    if not online_data.empty:
        for u in online_data['username']:
            st.sidebar.write(f"● **{u}**")
    else: st.sidebar.write("Тільки ви")
except: st.sidebar.write("Оновлення...")

if st.sidebar.button("Вийти"):
    st.session_state.clear()
    st.rerun()

st.sidebar.markdown("---")
if st.sidebar.button("📤 Перевірити Telegram"):
    success, msg = send_db_backup()
    if success: st.sidebar.success("✅ Файл у Telegram!")
    else: st.sidebar.error(f"❌ {msg}")

menu = ["📊 Аналітика", "🛠 Виробництво", "📦 Склад"]
if user_role == "Адмін": menu += ["📝 Нове замовлення", "⚙️ Персонал"]
choice = st.sidebar.selectbox("Меню", menu)

# --- 6. РОЗДІЛИ ---

if choice == "📦 Склад":
    st.header("📦 Склад")
    query = "SELECT name, qty, price FROM inventory ORDER BY name" if user_role == "Адмін" else "SELECT name, qty FROM inventory ORDER BY name"
    df_inv = pd.read_sql_query(query, db_conn)
    st.dataframe(df_inv, use_container_width=True)

    if user_role == "Адмін":
        st.subheader("📝 Корегування")
        if not df_inv.empty:
            c1, c2, c3 = st.columns(3)
            mat = c1.selectbox("Матеріал", df_inv['name'].tolist())
            cur_q = float(df_inv[df_inv['name'] == mat]['qty'].iloc[0])
            new_q = c2.number_input("Нова к-ть", value=cur_q)
            if c3.button("✅ Оновити"):
                db_conn.execute("UPDATE inventory SET qty=? WHERE name=?", (new_q, mat))
                db_conn.commit()
                send_db_backup()
                st.rerun()
        
        col1, col2 = st.columns(2)
        with col1.expander("➕ Додати"):
            with st.form("add_mat"):
                n, q, p = st.text_input("Назва"), st.number_input("К-ть"), st.number_input("Ціна")
                if st.form_submit_button("Зберегти"):
                    db_conn.execute("INSERT INTO inventory (name, qty, price) VALUES (?,?,?)", (n, q, p))
                    db_conn.commit()
                    send_db_backup()
                    st.rerun()
        with col2.expander("🗑️ Видалити"):
            if not df_inv.empty:
                to_del = st.selectbox("Що видалити?", df_inv['name'].tolist())
                if st.button("Видалити назавжди"):
                    db_conn.execute("DELETE FROM inventory WHERE name=?", (to_del,))
                    db_conn.commit()
                    send_db_backup()
                    st.rerun()

elif choice == "🛠 Виробництво":
    st.header("🛠 Виробництво")
    df_o = pd.read_sql_query("SELECT * FROM orders ORDER BY id DESC", db_conn)
    for _, row in df_o.iterrows():
        with st.expander(f"📦 №{row['id']} | {row['customer']} | {row['detail']} ({row['status']})"):
            c1, c2 = st.columns(2)
            with c1:
                st.write(f"Кількість: {row['qty']} шт.")
                if row['has_files']: st.info("📂 Креслення в Telegram")
                if user_role == "Адмін": 
                    st.write(f"Ціна: {row['price']} грн")
                    if st.button("Видалити замовлення", key=f"del{row['id']}"):
                        db_conn.execute("DELETE FROM orders WHERE id=?", (row['id'],))
                        db_conn.commit()
                        send_db_backup()
                        st.rerun()
            with c2:
                new_s = st.selectbox("Статус", ["Нове", "Обробка", "Готово"], index=["Нове", "Обробка", "Готово"].index(row['status']), key=f"s{row['id']}")
                if st.button("Зберегти", key=f"b{row['id']}"):
                    db_conn.execute("UPDATE orders SET status=? WHERE id=?", (new_s, row['id']))
                    db_conn.commit()
                    send_db_backup()
                    st.rerun()

elif choice == "📝 Нове замовлення":
    st.header("🆕 Нове замовлення")
    with st.form("n_ord", clear_on_submit=True):
        c, d, q, p = st.text_input("Клієнт"), st.text_input("Виріб"), st.number_input("К-ть", min_value=1), st.number_input("Ціна")
        files = st.file_uploader("Файли", accept_multiple_files=True)
        if st.form_submit_button("Створити"):
            has_f = False
            if files:
                has_f = True
                for f in files: send_file_to_tg(f.getvalue(), f.name, f"🆕 Замовлення {c}: {d}")
            db_conn.execute("INSERT INTO orders (customer, detail, qty, price, status, has_files) VALUES (?,?,?,?,'Нове',?)", (c, d, q, p, has_f))
            db_conn.commit()
            send_db_backup()
            st.success("✅ Створено!")

elif choice == "⚙️ Персонал":
    st.header("👥 Персонал")
    users = pd.read_sql_query("SELECT username, role FROM users", db_conn)
    st.table(users)
    col1, col2 = st.columns(2)
    with col1.expander("➕ Додати"):
        u, p, r = st.text_input("Логін"), st.text_input("Пароль"), st.selectbox("Роль", ["Робочий", "Конструктор", "Адмін"])
        if st.button("Створити"):
            db_conn.execute("INSERT INTO users VALUES (?,?,?,?)", (u, p, r, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            db_conn.commit()
            send_db_backup()
            st.rerun()
    with col2.expander("📝 Редагувати / Видалити"):
        target = st.selectbox("Користувач", users['username'].tolist())
        if target != 'admin':
            new_login = st.text_input("Новий логін", value=target)
            new_r = st.selectbox("Нова роль", ["Робочий", "Конструктор", "Адмін"], key="nr")
            if st.button("💾 Зберегти"):
                db_conn.execute("UPDATE users SET username=?, role=? WHERE username=?", (new_login, new_r, target))
                db_conn.commit()
                send_db_backup()
                st.rerun()
            if st.button("🗑️ Видалити"):
                db_conn.execute("DELETE FROM users WHERE username=?", (target,))
                db_conn.commit()
                send_db_backup()
                st.rerun()

elif choice == "📊 Аналітика":
    st.header("📈 Фінанси")
    inv_v = pd.read_sql_query("SELECT SUM(qty * price) as s FROM inventory", db_conn)['s'].iloc[0] or 0
    ord_v = pd.read_sql_query("SELECT SUM(qty * price) as s FROM orders WHERE status != 'Готово'", db_conn)['s'].iloc[0] or 0
    st.metric("Капітал на складі", f"{inv_v:,.2f} грн")
    st.metric("В роботі", f"{ord_v:,.2f} грн")

db_conn.close()
