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
        
        # Дефолтный админ (создается один раз)
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
    
    # Обновление времени онлайн
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("UPDATE users SET last_seen = ? WHERE username = ?", (datetime.now(), st.session_state["username"]))
        conn.commit()
    return True

if check_password():
    st.set_page_config(page_title="Factory ERP Pro", layout="wide")
    user_role = st.session_state["role"]
    username = st.session_state["username"]

    # --- SIDEBAR (Боковая панель) ---
    st.sidebar.title(f"👤 {username}")
    st.sidebar.info(f"Роль: {user_role}")
    
    if st.sidebar.button("Выйти"):
        st.session_state.clear()
        st.rerun()

    # Список онлайн пользователей
    st.sidebar.markdown("---")
    st.sidebar.subheader("🟢 Сейчас в системе")
    with sqlite3.connect(DB_NAME) as conn:
        online_users = pd.read_sql_query(
            "SELECT username, role FROM users WHERE last_seen > datetime('now', '-5 minutes', 'localtime')", conn)
        for _, row in online_users.iterrows():
            st.sidebar.write(f"● {row['username']} ({row['role']})")

    # Формирование меню по ролям
    menu = ["📊 Аналитика", "🛠 Производство", "📦 Склад"]
    if user_role == "Админ":
        menu += ["📝 Новый заказ", "⚙️ Персонал", "📜 Логи"]
    
    choice = st.sidebar.selectbox("Меню", menu)
    db_conn = sqlite3.connect(DB_NAME)

    # --- 1. АНАЛИТИКА ---
    if choice == "📊 Аналитика":
        st.header("📈 Состояние предприятия")
        if user_role == "Админ":
            df_inv = pd.read_sql_query("SELECT SUM(qty * price) as val FROM inventory", db_conn)
            df_ord = pd.read_sql_query("SELECT SUM(qty * price) as val FROM orders WHERE status != 'Готово'", db_conn)
            c1, c2 = st.columns(2)
            c1.metric("Склад (грн)", f"{df_inv['val'].iloc[0] or 0:,.2f}")
            c2.metric("Заказы в работе (грн)", f"{df_ord['val'].iloc[0] or 0:,.2f}")
        else:
            st.info("Доступ к финансовым данным разрешен только Администратору.")

    # --- 2. ПРОИЗВОДСТВО ---
    elif choice == "🛠 Производство":
        st.header("📋 Журнал производства")
        df_orders = pd.read_sql_query("SELECT * FROM orders", db_conn)
        for _, row in df_orders.iterrows():
            with st.expander(f"Заказ №{row['id']} | {row['customer']} | {row['detail']} ({row['status']})"):
                c1, c2 = st.columns(2)
                with c1:
                    st.write(f"Кол-во: {row['qty']} шт.")
                    if user_role == "Админ": st.write(f"Цена: {row['price']} грн")
                with c2:
                    new_status = st.selectbox("Изменить статус", ["Новое", "Обработка", "Готово"], 
                                             index=["Новое", "Обработка", "Готово"].index(row['status']), key=f"s_{row['id']}")
                    if st.button("Обновить статус", key=f"b_{row['id']}"):
                        db_conn.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, row['id']))
                        db_conn.commit()
                        add_log(username, f"Изменил статус заказа №{row['id']} на '{new_status}'")
                        st.rerun()

    # --- 3. СКЛАД ---
    elif choice == "📦 Склад":
        st.header("📦 Склад материалов")
        q = "SELECT * FROM inventory" if user_role == "Админ" else "SELECT name, qty FROM inventory"
        st.dataframe(pd.read_sql_query(q, db_conn), use_container_width=True)
        if user_role == "Админ":
            with st.expander("➕ Добавить материал"):
                with st.form("inv_form"):
                    n = st.text_input("Название")
                    qty = st.number_input("Кол-во", min_value=0.0)
                    pr = st.number_input("Цена закупки", min_value=0.0)
                    if st.form_submit_button("Сохранить"):
                        db_conn.execute("INSERT INTO inventory (name, qty, price) VALUES (?,?,?)", (n, qty, pr))
                        db_conn.commit()
                        add_log(username, f"Добавил на склад: {n} ({qty} шт)")
                        st.rerun()

    # --- 4. НОВЫЙ ЗАКАЗ ---
    elif choice == "📝 Новый заказ":
        st.header("🆕 Оформление нового заказа")
        with st.form("order_form"):
            c_name = st.text_input("Заказчик")
            d_name = st.text_input("Название изделия")
            o_qty = st.number_input("Количество", min_value=1)
            o_price = st.number_input("Цена продажи (за шт)", min_value=0.0)
            if st.form_submit_button("Запустить в производство"):
                db_conn.execute("INSERT INTO orders (customer, detail, qty, price, status) VALUES (?,?,?,?,'Новое')", 
                                (c_name, d_name, o_qty, o_price))
                db_conn.commit()
                add_log(username, f"Создал заказ: {d_name} для {c_name}")
                st.success("Заказ добавлен!")

    # --- 5. УПРАВЛЕНИЕ ПЕРСОНАЛОМ ---
    elif choice == "⚙️ Персонал":
        st.header("👥 Управление доступом")
        
        # Создание нового
        with st.expander("➕ Зарегистрировать сотрудника"):
            with st.form("reg_user"):
                u_new = st.text_input("Логин")
                p_new = st.text_input("Пароль", type="password")
                r_new = st.selectbox("Роль", ["Админ", "Конструктор", "Рабочий"])
                if st.form_submit_button("Создать акаунт"):
                    try:
                        db_conn.execute("INSERT INTO users (username, password, role) VALUES (?,?,?)", (u_new, p_new, r_new))
                        db_conn.commit()
                        add_log(username, f"Создал пользователя {u_new}")
                        st.success("Пользователь создан!")
                        st.rerun()
                    except: st.error("Этот логин уже занят")

        # Редактирование
        st.divider()
        st.subheader("📝 Редактирование данных")
        all_u = pd.read_sql_query("SELECT username, role FROM users", db_conn)
        target = st.selectbox("Кого редактируем?", all_u['username'].tolist())
        
        col1, col2 = st.columns(2)
        with col1:
            edit_name = st.text_input("Новый логин", value=target)
            edit_role = st.selectbox("Новая роль", ["Админ", "Конструктор", "Рабочий"], 
                                     index=["Админ", "Конструктор", "Рабочий"].index(all_u[all_u['username']==target]['role'].iloc[0]))
        with col2:
            edit_pass = st.text_input("Новый пароль (оставьте пустым, чтобы не менять)")

        if st.button("💾 Сохранить изменения"):
            try:
                if edit_pass:
                    db_conn.execute("UPDATE users SET username=?, password=?, role=? WHERE username=?", (edit_name, edit_pass, edit_role, target))
                else:
                    db_conn.execute("UPDATE users SET username=?, role=? WHERE username=?", (edit_name, edit_role, target))
                
                db_conn.execute("UPDATE logs SET username=? WHERE username=?", (edit_name, target))
                db_conn.commit()
                add_log(username, f"Переименовал {target} в {edit_name}")
                st.success("Данные обновлены!")
                st.rerun()
            except Exception as e: st.error(f"Ошибка: {e}")

        if st.button("🗑 Удалить сотрудника"):
            if target != username:
                db_conn.execute("DELETE FROM users WHERE username=?", (target,))
                db_conn.commit()
                add_log(username, f"Удалил пользователя {target}")
                st.rerun()
            else: st.error("Себя удалять нельзя!")

    # --- 6. ЛОГИ ---
    elif choice == "📜 Логи":
        st.header("📜 Журнал действий")
        df_l = pd.read_sql_query("SELECT timestamp, username, action FROM logs ORDER BY timestamp DESC LIMIT 100", db_conn)
        st.dataframe(df_l, use_container_width=True)

    db_conn.close()
