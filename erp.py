import streamlit as st
import sqlite3
import pandas as pd
import os
import requests
from datetime import datetime, timedelta

# --- 1. КОНФИГУРАЦИЯ ---
st.set_page_config(page_title="Factory ERP Pro (Safe Mode)", layout="wide")

DB_NAME = 'factory.db'
# Ваш проверенный токен
TG_TOKEN = "8743391673:AAGPXg-5-87Y881bO5XWhftEPPugKNK4y88"
# Ваш правильный ID канала
TG_CHAT_ID = "-1003964597358"

# --- 2. ФУНКЦИИ TELEGRAM (ИСПРАВЛЕННЫЙ АДРЕС) ---
def send_db_backup():
    """Отправляет актуальную базу в Telegram (сборка адреса по частям)"""
    base_url = "https://telegram.org"
    method = "/sendDocument"
    # Собираем адрес так, чтобы он не превращался в нерабочую ссылку
    full_url = f"{base_url}{TG_TOKEN}{method}"
    
    try:
        if os.path.exists(DB_NAME):
            with open(DB_NAME, 'rb') as f:
                r = requests.post(
                    full_url, 
                    data={'chat_id': TG_CHAT_ID, 'caption': f"📦 Backup: {datetime.now().strftime('%d.%m %H:%M')}"}, 
                    files={'document': f},
                    timeout=15
                )
            if r.status_code == 200:
                return True, "Успешно"
            else:
                return False, f"Ошибка {r.status_code}: {r.text}"
        return False, "Файл базы не найден"
    except Exception as e:
        return False, str(e)

def send_file_to_tg(file_bytes, file_name, caption):
    """Отправляет чертежи в Telegram"""
    base_url = "https://telegram.org"
    method = "/sendDocument"
    full_url = f"{base_url}{TG_TOKEN}{method}"
    try:
        requests.post(full_url, data={'chat_id': TG_CHAT_ID, 'caption': caption}, files={'document': (file_name, file_bytes)})
    except: pass

# --- 3. ИНИЦИАЛИЗАЦИЯ БД ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY, name TEXT, qty REAL, price REAL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, customer TEXT, detail TEXT, qty INTEGER, price REAL, status TEXT, has_files BOOLEAN)')
    cursor.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT, last_seen TIMESTAMP)')
    
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone() == 0:
        cursor.execute("INSERT INTO users VALUES ('admin', 'admin123', 'Адмін', ?)", (datetime.now(),))
    conn.commit()
    conn.close()

init_db()

# --- 4. АВТОРИЗАЦИЯ ---
if "auth" not in st.session_state:
    st.title("🏭 ERP Factory (Safe Mode)")
    
    with st.expander("🔄 ВОССТАНОВЛЕНИЕ ДАННЫХ (если база обнулилась)"):
        st.info("Скачайте последний файл factory.db из вашего Telegram-канала и загрузите сюда")
        up_db = st.file_uploader("Выберите файл .db", type="db")
        if up_db and st.button("Восстановить"):
            with open(DB_NAME, "wb") as f: f.write(up_db.getbuffer())
            st.success("База восстановлена! Перезагрузите страницу.")
            st.stop()

    u = st.text_input("Логин").strip()
    p = st.text_input("Пароль", type="password").strip()
    if st.button("Войти"):
        conn = sqlite3.connect(DB_NAME)
        res = conn.execute("SELECT username, role FROM users WHERE username=? AND password=?", (u, p)).fetchone()
        if res:
            st.session_state["auth"], st.session_state["user"], st.session_state["role"] = True, res[0], res[1]
            st.rerun()
        else: st.error("❌ Неверный логин или пароль")
    st.stop()

# Обновление активности
with sqlite3.connect(DB_NAME) as conn:
    conn.execute("UPDATE users SET last_seen = ? WHERE username = ?", (datetime.now(), st.session_state["user"]))
    conn.commit()

# --- 5. ОСНОВНОЙ ИНТЕРФЕЙС ---
user_role = st.session_state["role"]
username = st.session_state["user"]
db_conn = sqlite3.connect(DB_NAME)

st.sidebar.title(f"👤 {username}")
st.sidebar.info(f"Роль: {user_role}")

# Тест Telegram в сайдбаре
st.sidebar.markdown("---")
if st.sidebar.button("📤 Проверить Telegram"):
    success, msg = send_db_backup()
    if success: st.sidebar.success("✅ Работает! Файл в Telegram.")
    else: st.sidebar.error(f"❌ {msg}")

if st.sidebar.button("Выход"):
    st.session_state.clear()
    st.rerun()

menu = ["📊 Аналитика", "🛠 Производство", "📦 Склад"]
if user_role == "Адмін": menu += ["📝 Новый заказ", "⚙️ Персонал"]
choice = st.sidebar.selectbox("Меню", menu)

# --- СКЛАД ---
if choice == "📦 Склад":
    st.header("📦 Склад материалов")
    df_inv = pd.read_sql_query("SELECT * FROM inventory ORDER BY name", db_conn)
    st.dataframe(df_inv, use_container_width=True)

    if user_role == "Адмін":
        st.subheader("📝 Корректировка остатков")
        if not df_inv.empty:
            c1, c2, c3 = st.columns(3)
            mat = c1.selectbox("Материал", df_inv['name'].tolist())
            cur_qty = float(df_inv[df_inv['name'] == mat]['qty'].iloc[0])
            new_qty = c2.number_input("Новое количество", value=cur_qty)
            if c3.button("✅ Обновить"):
                db_conn.execute("UPDATE inventory SET qty=? WHERE name=?", (new_qty, mat))
                db_conn.commit()
                send_db_backup()
                st.rerun()
        
        col1, col2 = st.columns(2)
        with col1.expander("➕ Добавить позицию"):
            with st.form("add_mat"):
                n, q, p = st.text_input("Название"), st.number_input("К-во"), st.number_input("Цена")
                if st.form_submit_button("Сохранить"):
                    db_conn.execute("INSERT INTO inventory (name, qty, price) VALUES (?,?,?)", (n, q, p))
                    db_conn.commit()
                    send_db_backup()
                    st.rerun()
        with col2.expander("🗑️ Удалить позицию"):
            if not df_inv.empty:
                to_del = st.selectbox("Что удалить?", df_inv['name'].tolist())
                if st.button("Удалить навсегда"):
                    db_conn.execute("DELETE FROM inventory WHERE name=?", (to_del,))
                    db_conn.commit()
                    send_db_backup()
                    st.rerun()

# --- ПРОИЗВОДСТВО ---
elif choice == "🛠 Производство":
    st.header("📋 Журнал производства")
    df_o = pd.read_sql_query("SELECT * FROM orders ORDER BY id DESC", db_conn)
    for _, row in df_o.iterrows():
        with st.expander(f"📦 №{row['id']} | {row['customer']} | {row['detail']} ({row['status']})"):
            c1, c2 = st.columns(2)
            with c1:
                st.write(f"Количество: {row['qty']} шт.")
                if row['has_files']: st.info("📂 Чертежи отправлены в Telegram")
                if user_role == "Адмін": 
                    st.write(f"Цена: {row['price']} грн")
                    if st.button("Удалить заказ", key=f"del{row['id']}"):
                        db_conn.execute("DELETE FROM orders WHERE id=?", (row['id'],))
                        db_conn.commit()
                        send_db_backup()
                        st.rerun()
            with c2:
                new_s = st.selectbox("Статус", ["Нове", "Обробка", "Готово"], index=["Нове", "Обробка", "Готово"].index(row['status']), key=f"s{row['id']}")
                if st.button("Обновить статус", key=f"b{row['id']}"):
                    db_conn.execute("UPDATE orders SET status=? WHERE id=?", (new_s, row['id']))
                    db_conn.commit()
                    send_db_backup()
                    st.rerun()

# --- ПЕРСОНАЛ ---
elif choice == "⚙️ Персонал" and user_role == "Адмін":
    st.header("👥 Персонал")
    users = pd.read_sql_query("SELECT username, role FROM users", db_conn)
    st.table(users)
    with st.expander("➕ Добавить работника"):
        u, p, r = st.text_input("Логин"), st.text_input("Пароль"), st.selectbox("Роль", ["Робочий", "Конструктор", "Адмін"])
        if st.button("Создать"):
            db_conn.execute("INSERT INTO users VALUES (?,?,?,?)", (u, p, r, datetime.now()))
            db_conn.commit()
            send_db_backup()
            st.rerun()

# --- АНАЛИТИКА ---
elif choice == "📊 Аналитика" and user_role == "Адмін":
    st.header("📈 Финансы")
    inv_v = pd.read_sql_query("SELECT SUM(qty * price) as s FROM inventory", db_conn)['s'].iloc[0] or 0
    ord_v = pd.read_sql_query("SELECT SUM(qty * price) as s FROM orders WHERE status != 'Готово'", db_conn)['s'].iloc[0] or 0
    st.metric("Капитал на складе", f"{inv_v:,.2f} грн")
    st.metric("В работе", f"{ord_v:,.2f} грн")

db_conn.close()
