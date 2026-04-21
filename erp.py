import streamlit as st
import sqlite3
import pandas as pd
import os
from datetime import datetime

# --- 1. НАЛАШТУВАННЯ СТОРІНКИ ---
st.set_page_config(page_title="Factory ERP Pro", layout="wide")

# --- 2. КОНФІГУРАЦІЯ СИСТЕМИ ---
DB_NAME = 'factory.db'
FILES_DIR = 'files'
if not os.path.exists(FILES_DIR):
    os.makedirs(FILES_DIR)

# --- 3. ІНІЦІАЛІЗАЦІЯ БАЗИ ДАНИХ ---
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        # Склад
        cursor.execute('CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY, name TEXT, qty REAL, price REAL)')
        # Замовлення
        cursor.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, customer TEXT, detail TEXT, qty INTEGER, price REAL, status TEXT, photo TEXT)')
        # Користувачі
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT, last_seen TIMESTAMP)''')
        # Логи
        cursor.execute('''CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY, timestamp TIMESTAMP, username TEXT, action TEXT)''')
        
        # ПРИМУСОВЕ ОНОВЛЕННЯ АДМІНА (щоб пароль admin123 точно запрацював)
        cursor.execute("INSERT OR REPLACE INTO users (username, password, role) VALUES ('admin', 'admin123', 'Адмін')")
        
        # Виправлення ролей
        cursor.execute("UPDATE users SET role = 'Адмін' WHERE role IN ('Админ', 'admin', 'Admin')")
        cursor.execute("UPDATE users SET role = 'Робочий' WHERE role IN ('Рабочий', 'worker', 'Worker')")
        cursor.execute("UPDATE users SET role = 'Конструктор' WHERE role IN ('Designer', 'designer')")
        conn.commit()

init_db()

def add_log(username, action):
    try:
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute("INSERT INTO logs (timestamp, username, action) VALUES (?, ?, ?)", 
                         (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), username, action))
            conn.commit()
    except Exception as e:
        pass # Щоб не переривати роботу через помилку логів

# --- 4. АВТОРИЗАЦІЯ ---
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
                    add_log(res[0], "Увійшов у систему")
                    st.rerun()
                else:
                    st.error("❌ Невірний логін або пароль")
        return False
    
    # Оновлення активності
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("UPDATE users SET last_seen = ? WHERE username = ?", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), st.session_state["username"]))
        conn.commit()
    return True

# --- 5. ОСНОВНИЙ ЦИКЛ ПРОГРАМИ ---
if check_password():
    user_role = st.session_state["role"]
    username = st.session_state["username"]
    db_conn = sqlite3.connect(DB_NAME)

    # --- SIDEBAR ---
    st.sidebar.title(f"👤 {username}")
    st.sidebar.info(f"Роль: {user_role}")
    
    if st.sidebar.button("Вийти з системи"):
        add_log(username, "Вийшов із системи")
        st.session_state.clear()
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.subheader("🟢 Зараз у системі")
    online_users = pd.read_sql_query(
        "SELECT username, role FROM users WHERE last_seen > datetime('now', '-5 minutes')", db_conn)
    for _, row in online_users.iterrows():
        st.sidebar.write(f"● {row['username']} ({row['role']})")

    menu = ["📊 Аналітика", "🛠 Виробництво", "📦 Склад"]
    if user_role == "Адмін":
        menu += ["📝 Нове замовлення", "⚙️ Персонал", "📜 Журнал дій"]
    choice = st.sidebar.selectbox("Меню", menu)

    # --- ЛОГІКА РОЗДІЛІВ ---
    
    if choice == "📊 Аналітика":
        st.header("📈 Стан підприємства")
        if user_role == "Адмін":
            df_inv = pd.read_sql_query("SELECT SUM(qty * price) as val FROM inventory", db_conn)
            df_ord = pd.read_sql_query("SELECT SUM(qty * price) as val FROM orders WHERE status != 'Готово'", db_conn)
            c1, c2 = st.columns(2)
            val_inv = df_inv['val'].iloc[0] if not df_inv.empty and df_inv['val'].iloc[0] else 0
            val_ord = df_ord['val'].iloc[0] if not df_ord.empty and df_ord['val'].iloc[0] else 0
            c1.metric("Вартість складу", f"{val_inv:,.2f} грн")
            c2.metric("Замовлення в роботі", f"{val_ord:,.2f} грн")
        else:
            st.info("Доступ до фінансової аналітики відкритий тільки для Адміністратора.")

    elif choice == "🛠 Виробництво":
        st.header("📋 Журнал виробництва")
        df_orders = pd.read_sql_query("SELECT * FROM orders", db_conn)
        if df_orders.empty:
            st.write("Замовлень поки немає.")
        for _, row in df_orders.iterrows():
            with st.expander(f"📦 №{row['id']} | {row['customer']} | {row['detail']} ({row['status']})"):
                c1, c2 = st.columns(2)
                with c1:
                    st.write(f"**Кількість:** {row['qty']} шт.")
                    if user_role == "Адмін": st.write(f"**Ціна:** {row['price']} грн")
                with c2:
                    statuses = ["Нове", "Обробка", "Готово"]
                    cur_idx = statuses.index(row['status']) if row['status'] in statuses else 0
                    new_status = st.selectbox("Статус", statuses, index=cur_idx, key=f"s_{row['id']}")
                    if st.button("Оновити", key=f"b_{row['id']}"):
                        db_conn.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, row['id']))
                        db_conn.commit()
                        add_log(username, f"Змінив статус замовлення №{row['id']} на '{new_status}'")
                        st.rerun()

    elif choice == "📦 Склад":
        st.header("📦 Склад матеріалів")
        q = "SELECT * FROM inventory" if user_role == "Адмін" else "SELECT name, qty FROM inventory"
        df_inv = pd.read_sql_query(q, db_conn)
        st.dataframe(df_inv, use_container_width=True)

        if user_role == "Адмін":
            col_sc1, col_sc2 = st.columns(2)
            with col_sc1.expander("➕ Додати матеріал"):
                with st.form("inv_add"):
                    n = st.text_input("Назва")
                    qv = st.number_input("Кількість", min_value=0.0)
                    pv = st.number_input("Ціна закупівлі", min_value=0.0)
                    if st.form_submit_button("Зберегти"):
                        db_conn.execute("INSERT INTO inventory (name, qty, price) VALUES (?,?,?)", (n, qv, pv))
                        db_conn.commit()
                        add_log(username, f"Додав на склад: {n}")
                        st.rerun()
            
            with col_sc2.expander("🗑️ Видалити позицію"):
                if not df_inv.empty:
                    target_del = st.selectbox("Оберіть для видалення", df_inv['name'].tolist())
                    if st.button("Видалити"):
                        db_conn.execute("DELETE FROM inventory WHERE name=?", (target_del,))
                        db_conn.commit()
                        add_log(username, f"Видалив зі складу: {target_del}")
                        st.rerun()

    elif choice == "📝 Нове замовлення":
        st.header("🆕 Реєстрація замовлення")
        with st.form("order_new"):
            c = st.text_input("Замовник")
            d = st.text_input("Виріб")
            qo = st.number_input("Кількість", min_value=1)
            po = st.number_input("Ціна продажу", min_value=0.0)
            if st.form_submit_button("Запустити"):
                db_conn.execute("INSERT INTO orders (customer, detail, qty, price, status) VALUES (?,?,?,?,'Нове')", (c, d, qo, po))
                db_conn.commit()
                add_log(username, f"Створив замовлення для {c}")
                st.success("Додано!")

    elif choice == "⚙️ Персонал":
        st.header("👥 Керування працівниками")
        with st.expander("➕ Новий співробітник"):
            with st.form("user_reg"):
                u, p, r = st.text_input("Логін"), st.text_input("Пароль", type="password"), st.selectbox("Роль", ["Адмін", "Конструктор", "Робочий"])
                if st.form_submit_button("Створити"):
                    try:
                        db_conn.execute("INSERT INTO users (username, password, role) VALUES (?,?,?)", (u, p, r))
                        db_conn.commit()
                        add_log(username, f"Зареєстрував: {u}")
                        st.success("Створено!")
                    except: st.error("Логін зайнятий")

        st.divider()
        all_u = pd.read_sql_query("SELECT username, role FROM users", db_conn)
        if not all_u.empty:
            target_u = st.selectbox("Редагувати працівника", all_u['username'].tolist())
            cur_role = all_u[all_u['username'] == target_u]['role'].iloc[0]
            roles_list = ["Адмін", "Конструктор", "Робочий"]
            role_idx = roles_list.index(cur_role) if cur_role in roles_list else 0
            
            c1, c2 = st.columns(2)
            with c1:
                enm = st.text_input("Новий логін", value=target_u)
                erl = st.selectbox("Нова роль", roles_list, index=role_idx)
            with c2:
                eps = st.text_input("Новий пароль (залиште порожнім)", type="password")
            
            if st.button("💾 Зберегти зміни"):
                if eps:
                    db_conn.execute("UPDATE users SET username=?, password=?, role=? WHERE username=?", (enm, eps, erl, target_u))
                else:
                    db_conn.execute("UPDATE users SET username=?, role=? WHERE username=?", (enm, erl, target_u))
                db_conn.commit()
                st.rerun()

            if st.button("🗑 Видалити доступ"):
                if target_u != username:
                    db_conn.execute("DELETE FROM users WHERE username=?", (target_u,))
                    db_conn.commit()
                    st.rerun()
                else: st.error("Себе видаляти не можна!")

    elif choice == "📜 Журнал дій":
        st.header("📜 Історія")
        df_log = pd.read_sql_query("SELECT timestamp, username, action FROM logs ORDER BY id DESC LIMIT 200", db_conn)
        st.dataframe(df_log, use_container_width=True)

    db_conn.close()
