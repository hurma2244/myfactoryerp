import streamlit as st
import sqlite3
import pandas as pd
import os
from datetime import datetime

# --- НАЛАШТУВАННЯ СИСТЕМИ ---
DB_NAME = 'factory.db'
FILES_DIR = 'files'
if not os.path.exists(FILES_DIR):
    os.makedirs(FILES_DIR)

# --- ІНІЦІАЛІЗАЦІЯ БАЗИ ДАНИХ ---
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        # Склад
        cursor.execute('CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY, name TEXT, qty REAL, price REAL)')
        # Замовлення
        cursor.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, customer TEXT, detail TEXT, qty INTEGER, price REAL, status TEXT, photo TEXT)')
        # Користувачі
        cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                          (username TEXT PRIMARY KEY, password TEXT, role TEXT, last_seen TIMESTAMP)''')
        # Логи
        cursor.execute('''CREATE TABLE IF NOT EXISTS logs 
                          (id INTEGER PRIMARY KEY, timestamp TIMESTAMP, username TEXT, action TEXT)''')
        
        # Створення адміна (якщо немає)
        cursor.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES ('admin', 'admin123', 'Адмін')")
        
        # ВИПРАВЛЕННЯ РОЛЕЙ (Auto-fix мовних помилок)
        cursor.execute("UPDATE users SET role = 'Адмін' WHERE role IN ('Админ', 'admin', 'Admin')")
        cursor.execute("UPDATE users SET role = 'Робочий' WHERE role IN ('Рабочий', 'worker', 'Worker')")
        cursor.execute("UPDATE users SET role = 'Конструктор' WHERE role IN ('Designer', 'designer')")
        conn.commit()

init_db()

def add_log(username, action):
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("INSERT INTO logs (timestamp, username, action) VALUES (?, ?, ?)", 
                     (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), username, action))
        conn.commit()

# --- АВТОРИЗАЦІЯ ---
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
                    st.rerun()
                else:
                    st.error("❌ Невірний логін або пароль")
        return False
    
    # Оновлення активності
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("UPDATE users SET last_seen = ? WHERE username = ?", (datetime.now(), st.session_state["username"]))
        conn.commit()
    return True

if check_password():
    st.set_page_config(page_title="Factory ERP Pro", layout="wide")
    user_role = st.session_state["role"]
    username = st.session_state["username"]

    # --- SIDEBAR ---
    st.sidebar.title(f"👤 {username}")
    st.sidebar.info(f"Роль: {user_role}")
    
    if st.sidebar.button("Вийти з системи"):
        st.session_state.clear()
        st.rerun()

    # Список онлайн
    st.sidebar.markdown("---")
    st.sidebar.subheader("🟢 Зараз у системі")
    with sqlite3.connect(DB_NAME) as conn:
        online_users = pd.read_sql_query(
            "SELECT username, role FROM users WHERE last_seen > datetime('now', '-5 minutes', 'localtime')", conn)
        for _, row in online_users.iterrows():
            st.sidebar.write(f"● {row['username']} ({row['role']})")

    # Формування меню
    menu = ["📊 Аналітика", "🛠 Виробництво", "📦 Склад"]
    if user_role == "Адмін":
        menu += ["📝 Нове замовлення", "⚙️ Персонал", "📜 Журнал дій"]
    
    choice = st.sidebar.selectbox("Меню", menu)
    db_conn = sqlite3.connect(DB_NAME)

    # --- 1. АНАЛІТИКА ---
    if choice == "📊 Аналітика":
        st.header("📈 Стан підприємства")
        if user_role == "Адмін":
            df_inv = pd.read_sql_query("SELECT SUM(qty * price) as val FROM inventory", db_conn)
            df_ord = pd.read_sql_query("SELECT SUM(qty * price) as val FROM orders WHERE status != 'Готово'", db_conn)
            c1, c2 = st.columns(2)
            c1.metric("Вартість складу", f"{df_inv['val'].iloc[0] or 0:,.2f} грн")
            c2.metric("Замовлення в роботі", f"{df_ord['val'].iloc[0] or 0:,.2f} грн")
        else:
            st.info("Доступ до фінансової аналітики відкритий тільки для Адміністратора.")

    # --- 2. ВИРОБНИЦТВО ---
    elif choice == "🛠 Виробництво":
        st.header("📋 Журнал виробництва")
        df_orders = pd.read_sql_query("SELECT * FROM orders", db_conn)
        for _, row in df_orders.iterrows():
            with st.expander(f"📦 Замовлення №{row['id']} | {row['customer']} | {row['detail']} ({row['status']})"):
                c1, c2 = st.columns(2)
                with c1:
                    st.write(f"**Кількість:** {row['qty']} шт.")
                    if user_role == "Адмін": st.write(f"**Ціна продажу:** {row['price']} грн")
                with c2:
                    statuses = ["Нове", "Обробка", "Готово"]
                    cur_idx = statuses.index(row['status']) if row['status'] in statuses else 0
                    new_status = st.selectbox("Змінити статус", statuses, index=cur_idx, key=f"s_{row['id']}")
                    if st.button("Оновити статус", key=f"b_{row['id']}"):
                        db_conn.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, row['id']))
                        db_conn.commit()
                        add_log(username, f"Змінив статус замовлення №{row['id']} на '{new_status}'")
                        st.rerun()

    # --- 3. СКЛАД ---
    elif choice == "📦 Склад":
        st.header("📦 Склад матеріалів")
        q = "SELECT * FROM inventory" if user_role == "Адмін" else "SELECT name, qty FROM inventory"
        df_inv = pd.read_sql_query(q, db_conn)
        st.dataframe(df_inv, use_container_width=True)

        if user_role == "Адмін":
            col_sc1, col_sc2 = st.columns(2)
            with col_sc1.expander("➕ Додати новий матеріал"):
                with st.form("inv_add"):
                    n = st.text_input("Назва матеріалу")
                    qv = st.number_input("Кількість", min_value=0.0)
                    pv = st.number_input("Ціна закупівлі", min_value=0.0)
                    if st.form_submit_button("Зберегти"):
                        db_conn.execute("INSERT INTO inventory (name, qty, price) VALUES (?,?,?)", (n, qv, pv))
                        db_conn.commit()
                        add_log(username, f"Додав на склад: {n} ({qv} шт)")
                        st.rerun()

            with col_sc2.expander("🗑️ Видалити позицію повністю"):
                if not df_inv.empty:
                    target_del = st.selectbox("Матеріал для видалення", df_inv['name'].tolist())
                    if st.button("Видалити остаточно"):
                        db_conn.execute("DELETE FROM inventory WHERE name=?", (target_del,))
                        db_conn.commit()
                        add_log(username, f"Видалив зі складу: {target_del}")
                        st.rerun()

            st.divider()
            st.subheader("📝 Швидке корегування залишків")
            if not df_inv.empty:
                cadj1, cadj2, cadj3 = st.columns(3)
                mat_adj = cadj1.selectbox("Оберіть матеріал", df_inv['name'].tolist(), key="adj_s")
                cur_q = df_inv[df_inv['name'] == mat_adj]['qty'].iloc[0]
                new_q = cadj2.number_input(f"Встановіть залишок (зараз: {cur_q})", min_value=0.0)
                if cadj3.button("Оновити кількість"):
                    db_conn.execute("UPDATE inventory SET qty = ? WHERE name = ?", (new_q, mat_adj))
                    db_conn.commit()
                    add_log(username, f"Змінив залишок {mat_adj} з {cur_q} на {new_q}")
                    st.rerun()

    # --- 4. НОВЕ ЗАМОВЛЕННЯ ---
    elif choice == "📝 Нове замовлення":
        st.header("🆕 Реєстрація замовлення")
        with st.form("order_new"):
            c, d = st.text_input("Замовник"), st.text_input("Виріб/Деталь")
            qo, po = st.number_input("Кількість", min_value=1), st.number_input("Ціна продажу", min_value=0.0)
            if st.form_submit_button("Запустити у виробництво"):
                db_conn.execute("INSERT INTO orders (customer, detail, qty, price, status) VALUES (?,?,?,?,'Нове')", (c, d, qo, po))
                db_conn.commit()
                add_log(username, f"Створив замовлення для {c}: {d}")
                st.success("Успішно додано!")

    # --- 5. ПЕРСОНАЛ ---
    elif choice == "⚙️ Персонал":
        st.header("👥 Керування працівниками")
        with st.expander("➕ Зареєструвати нового співробітника"):
            with st.form("user_reg"):
                u, p, r = st.text_input("Логін"), st.text_input("Пароль", type="password"), st.selectbox("Роль", ["Адмін", "Конструктор", "Робочий"])
                if st.form_submit_button("Створити"):
                    try:
                        db_conn.execute("INSERT INTO users (username, password, role) VALUES (?,?,?)", (u, p, r))
                        db_conn.commit()
                        add_log(username, f"Зареєстрував працівника: {u} ({r})")
                        st.rerun()
                    except: st.error("Цей логін вже зайнятий")

        st.divider()
        st.subheader("📝 Редагування та видалення")
        all_u = pd.read_sql_query("SELECT username, role FROM users", db_conn)
        target_u = st.selectbox("Виберіть працівника", all_u['username'].tolist())
        
        # Безпечний пошук ролі
        cur_role = all_u[all_u['username'] == target_u]['role'].iloc[0]
        roles_list = ["Адмін", "Конструктор", "Робочий"]
        role_idx = roles_list.index(cur_role) if cur_role in roles_list else 2

        ced1, ced2 = st.columns(2)
        with ced1:
            enm = st.text_input("Новий логін", value=target_u)
            erl = st.selectbox("Нова роль", roles_list, index=role_idx)
        with ced2:
            eps = st.text_input("Новий пароль (залиште порожнім)", type="password")

        if st.button("💾 Зберегти зміни"):
            if eps:
                db_conn.execute("UPDATE users SET username=?, password=?, role=? WHERE username=?", (enm, eps, erl, target_u))
            else:
                db_conn.execute("UPDATE users SET username=?, role=? WHERE username=?", (enm, erl, target_u))
            db_conn.execute("UPDATE logs SET username=? WHERE username=?", (enm, target_u))
            db_conn.commit()
            add_log(username, f"Оновив дані користувача {target_u}")
            st.rerun()

        if st.button("🗑 Видалити доступ"):
            if target_u != username:
                db_conn.execute("DELETE FROM users WHERE username=?", (target_u,))
                db_conn.commit()
                add_log(username, f"Видалив акаунт: {target_u}")
                st.rerun()
            else: st.error("Ви не можете видалити самого себе!")

    # --- 6. ЖУРНАЛ ДІЙ ---
    elif choice == "📜 Журнал дій":
        st.header("📜 Історія активності")
        df_log = pd.read_sql_query("SELECT timestamp as 'Час', username as 'Працівник', action as 'Дія' FROM logs ORDER BY timestamp DESC LIMIT 200", db_conn)
        st.table(df_log)

    db_conn.close()



