import streamlit as st
import sqlite3
import pandas as pd
import os
from datetime import datetime

# --- НАСТРОЙКИ ---
DB_NAME = 'factory.db'
FILES_DIR = 'files'
if not os.path.exists(FILES_DIR):
    os.makedirs(FILES_DIR)

# --- БД: ИНИЦИАЛИЗАЦИЯ ---
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        # Склад и Заказы
        cursor.execute('CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY, name TEXT, qty REAL, price REAL)')
        cursor.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, customer TEXT, detail TEXT, qty INTEGER, price REAL, status TEXT, photo TEXT)')
        # Пользователи: логин, пароль, роль, последняя активность
        cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                          (username TEXT PRIMARY KEY, password TEXT, role TEXT, last_seen TIMESTAMP)''')
        
        # Предзаполненные пользователи (если их еще нет)
        users = [
            ('admin', 'admin123', 'Админ'),
            ('konstr', 'k123', 'Конструктор'),
            ('worker', 'w123', 'Рабочий')
        ]
        cursor.executemany("INSERT OR IGNORE INTO users (username, password, role) VALUES (?,?,?)", users)
        conn.commit()

init_db()

# --- ЛОГИКА АВТОРИЗАЦИИ ---
def check_password():
    if "authenticated" not in st.session_state:
        st.title("🔐 Вход в систему ERP")
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
    
    # Обновляем статус "Онлайн" (Heartbeat)
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("UPDATE users SET last_seen = ? WHERE username = ?", (datetime.now(), st.session_state["username"]))
        conn.commit()
    return True

if check_password():
    st.set_page_config(page_title="Factory ERP Pro", layout="wide")
    
    # --- БОКОВАЯ ПАНЕЛЬ ---
    st.sidebar.title(f"👤 {st.session_state['username']}")
    st.sidebar.info(f"Роль: {st.session_state['role']}")
    
    # Список онлайн (активность за последние 5 минут)
    st.sidebar.markdown("---")
    st.sidebar.subheader("🟢 Сейчас в системе")
    with sqlite3.connect(DB_NAME) as conn:
        online_users = pd.read_sql_query(
            "SELECT username, role FROM users WHERE last_seen > datetime('now', '-5 minutes', 'localtime')", conn)
        for _, row in online_users.iterrows():
            st.sidebar.write(f"● {row['username']} ({row['role']})")
    
    st.sidebar.markdown("---")
    
    # Разграничение меню
    user_role = st.session_state["role"]
    menu = ["📊 Аналитика", "🛠 Производство", "📦 Склад"]
    if user_role == "Админ":
        menu.append("📝 Новый заказ")
        
    choice = st.sidebar.selectbox("Меню", menu)
    
    if st.sidebar.button("Выйти"):
        st.session_state.clear()
        st.rerun()

    conn = sqlite3.connect(DB_NAME)

    # --- 1. АНАЛИТИКА ---
    if choice == "📊 Аналитика":
        st.header("📈 Состояние предприятия")
        df_inv = pd.read_sql_query("SELECT SUM(qty * price) as val FROM inventory", conn)
        df_ord = pd.read_sql_query("SELECT SUM(qty * price) as val FROM orders WHERE status != 'Готово'", conn)
        
        c1, c2 = st.columns(2)
        # Аналитику (деньги) видит только админ, остальные — только заголовки или заглушки
        if user_role == "Админ":
            c1.metric("Стоимость склада", f"{df_inv['val'].iloc[0] or 0:,.2f} грн")
            c2.metric("Активные заказы", f"{df_ord['val'].iloc[0] or 0:,.2f} грн")
        else:
            st.info("Доступ к финансовой аналитике ограничен.")

    # --- 2. ПРОИЗВОДСТВО ---
    elif choice == "🛠 Производство":
        st.header("📋 Журнал производства")
        df_orders = pd.read_sql_query("SELECT * FROM orders", conn)
        
        for index, row in df_orders.iterrows():
            with st.expander(f"📦 Заказ №{row['id']} | {row['customer']} | {row['detail']} ({row['status']})"):
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.write(f"**Кол-во:** {row['qty']} шт.")
                    if user_role == "Админ":
                        st.write(f"**Цена:** {row['price']} грн")
                
                with col2:
                    # Изменять статус могут все, но удалять — только Админ
                    new_status = st.selectbox("Статус", ["Новое", "Обработка", "Готово"], 
                                             index=["Новое", "Обработка", "Готово"].index(row['status']), 
                                             key=f"st_{row['id']}")
                    if st.button("Обновить", key=f"upd_{row['id']}"):
                        conn.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, row['id']))
                        conn.commit()
                        st.rerun()
                    
                    if user_role == "Админ":
                        if st.button("🗑 Удалить", key=f"del_{row['id']}"):
                            conn.execute("DELETE FROM orders WHERE id = ?", (row['id'],))
                            conn.commit()
                            st.rerun()

    # --- 3. СКЛАД ---
    elif choice == "📦 Склад":
        st.header("📦 Склад материалов")
        # Конструктор и рабочий видят только Название и Количество
        if user_role == "Админ":
            df_inv = pd.read_sql_query("SELECT * FROM inventory", conn)
        else:
            df_inv = pd.read_sql_query("SELECT name, qty FROM inventory", conn)
            
        st.dataframe(df_inv, use_container_width=True)

        # Админ-панель управления складом
        if user_role == "Админ":
            st.subheader("➕ Добавить/Изменить")
            with st.form("inv_form"):
                n = st.text_input("Материал")
                q = st.number_input("Кол-во", min_value=0.0)
                p = st.number_input("Цена закупки", min_value=0.0)
                if st.form_submit_button("Сохранить"):
                    conn.execute("INSERT INTO inventory (name, qty, price) VALUES (?,?,?)", (n, q, p))
                    conn.commit()
                    st.rerun()

    # --- 4. НОВЫЙ ЗАКАЗ (Только Админ) ---
    elif choice == "📝 Новый заказ":
        if user_role == "Админ":
            st.header("🆕 Оформление нового заказа")
            # ... (код формы из вашего первого сообщения) ...
            with st.form("new_order"):
                cust = st.text_input("Заказчик")
                det = st.text_input("Деталь")
                q_ord = st.number_input("Кол-во", min_value=1)
                p_ord = st.number_input("Цена продажи", min_value=0.0)
                if st.form_submit_button("Создать"):
                    conn.execute("INSERT INTO orders (customer, detail, qty, price, status) VALUES (?,?,?,?,'Новое')", 
                                 (cust, det, q_ord, p_ord))
                    conn.commit()
                    st.success("Создано")
        else:
            st.error("У вас нет прав для создания заказов.")

    conn.close()
