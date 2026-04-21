import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime

# --- 1. НАЛАШТУВАННЯ СТОРІНКИ ---
st.set_page_config(page_title="Factory ERP Cloud", layout="wide")

# --- 2. ПІДКЛЮЧЕННЯ ДО SUPABASE ---
# ЗАМІНІТЬ ЦЕЙ РЯДОК НА ВАШ URI (з паролем замість [YOUR-PASSWORD])
DB_URI = "postgresql://postgres:[PASSWORD]@db.xxxxxx.supabase.co:5432/postgres"
engine = create_engine(DB_URI)

# --- 3. ІНІЦІАЛІЗАЦІЯ ТАБЛИЦЬ (PostgreSQL) ---
def init_db():
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS inventory (id SERIAL PRIMARY KEY, name TEXT, qty REAL, price REAL);
            CREATE TABLE IF NOT EXISTS orders (id SERIAL PRIMARY KEY, customer TEXT, detail TEXT, qty INTEGER, price REAL, status TEXT);
            CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT, last_seen TIMESTAMP);
            CREATE TABLE IF NOT EXISTS logs (id SERIAL PRIMARY KEY, timestamp TIMESTAMP, username TEXT, action TEXT);
            
            INSERT INTO users (username, password, role) 
            VALUES ('admin', 'admin123', 'Адмін') 
            ON CONFLICT (username) DO NOTHING;
        """))
        conn.commit()

init_db()

def add_log(username, action):
    try:
        with engine.connect() as conn:
            conn.execute(text("INSERT INTO logs (timestamp, username, action) VALUES (:t, :u, :a)"),
                         {"t": datetime.now(), "u": str(username), "a": action})
            conn.commit()
    except: pass

# --- 4. АВТОРИЗАЦІЯ ---
if "authenticated" not in st.session_state:
    st.title("🏭 ERP Система (Cloud 24/7)")
    user = st.text_input("Логін")
    pwd = st.text_input("Пароль", type="password")
    if st.button("Увійти"):
        with engine.connect() as conn:
            res = conn.execute(text("SELECT username, role FROM users WHERE username=:u AND password=:p"),
                               {"u": user, "p": pwd}).fetchone()
            if res:
                st.session_state["authenticated"] = True
                st.session_state["username"] = res[0]
                st.session_state["role"] = res[1]
                add_log(res[0], "Увійшов у систему")
                st.rerun()
            else: st.error("❌ Невірний логін або пароль")
    st.stop()

# --- 5. РОБОЧИЙ ІНТЕРФЕЙС ---
user_role = st.session_state["role"]
username = st.session_state["username"]

st.sidebar.title(f"👤 {username}")
if st.sidebar.button("Вийти"):
    st.session_state.clear()
    st.rerun()

menu = ["📊 Аналітика", "🛠 Виробництво", "📦 Склад"]
if user_role == "Адмін": menu += ["📝 Нове замовлення", "⚙️ Персонал", "📜 Журнал дій"]
choice = st.sidebar.selectbox("Меню", menu)

# --- 📊 АНАЛІТИКА ---
if choice == "📊 Аналітика":
    st.header("📈 Стан підприємства")
    df_inv = pd.read_sql("SELECT SUM(qty * price) as val FROM inventory", engine)
    df_ord = pd.read_sql("SELECT SUM(qty * price) as val FROM orders WHERE status != 'Готово'", engine)
    c1, c2 = st.columns(2)
    v_inv = df_inv['val'].iloc[0] if df_inv['val'].iloc[0] else 0
    v_ord = df_ord['val'].iloc[0] if df_ord['val'].iloc[0] else 0
    c1.metric("Склад (грн)", f"{v_inv:,.2f}")
    c2.metric("В роботі (грн)", f"{v_ord:,.2f}")

# --- 🛠 ВИРОБНИЦТВО ---
elif choice == "🛠 Виробництво":
    st.header("📋 Журнал виробництва")
    df_orders = pd.read_sql("SELECT * FROM orders ORDER BY id DESC", engine)
    for _, row in df_orders.iterrows():
        with st.expander(f"📦 №{row['id']} | {row['customer']} | {row['detail']} ({row['status']})"):
            statuses = ["Нове", "Обробка", "Готово"]
            new_status = st.selectbox("Статус", statuses, index=statuses.index(row['status']) if row['status'] in statuses else 0, key=f"s{row['id']}")
            if st.button("Оновити", key=f"b{row['id']}"):
                with engine.connect() as conn:
                    conn.execute(text("UPDATE orders SET status=:s WHERE id=:id"), {"s": new_status, "id": row['id']})
                    conn.commit()
                add_log(username, f"Змінив статус замовлення №{row['id']} на {new_status}")
                st.rerun()

# --- 📦 СКЛАД (З РЕДАГУВАННЯМ ЗАЛИШКІВ) ---
elif choice == "📦 Склад":
    st.header("📦 Склад матеріалів")
    df_inv = pd.read_sql("SELECT * FROM inventory ORDER BY name ASC", engine)
    st.dataframe(df_inv, use_container_width=True)

    if user_role == "Адмін":
        st.subheader("📝 Швидке корегування залишків")
        if not df_inv.empty:
            cadj1, cadj2, cadj3 = st.columns(3)
            mat_adj = cadj1.selectbox("Оберіть матеріал", df_inv['name'].tolist())
            row_data = df_inv[df_inv['name'] == mat_adj]
            cur_q = float(row_data['qty'].iloc[0])
            
            new_q = cadj2.number_input(f"Встановіть залишок (зараз: {cur_q})", min_value=0.0, value=cur_q)
            if cadj3.button("✅ Оновити кількість"):
                with engine.connect() as conn:
                    conn.execute(text("UPDATE inventory SET qty = :q WHERE name = :n"), {"q": new_q, "n": mat_adj})
                    conn.commit()
                add_log(username, f"Змінив залишок {mat_adj} на {new_q}")
                st.success(f"Кількість {mat_adj} оновлена!")
                st.rerun()
        
        st.divider()
        c1, c2 = st.columns(2)
        with c1.expander("➕ Додати новий матеріал"):
            with st.form("add_inv_form"):
                n = st.text_input("Назва")
                q = st.number_input("Кількість", min_value=0.0)
                p = st.number_input("Ціна закупівлі", min_value=0.0)
                if st.form_submit_button("Зберегти"):
                    with engine.connect() as conn:
                        conn.execute(text("INSERT INTO inventory (name, qty, price) VALUES (:n, :q, :p)"), {"n": n, "q": q, "p": p})
                        conn.commit()
                    add_log(username, f"Додав матеріал {n}")
                    st.rerun()
        with c2.expander("🗑️ Видалити позицію"):
            target = st.selectbox("Матеріал", df_inv['name'].tolist() if not df_inv.empty else [])
            if st.button("Видалити остаточно"):
                with engine.connect() as conn:
                    conn.execute(text("DELETE FROM inventory WHERE name=:n"), {"n": target})
                    conn.commit()
                add_log(username, f"Видалив зі складу: {target}")
                st.rerun()

# --- 📝 НОВЕ ЗАМОВЛЕННЯ ---
elif choice == "📝 Нове замовлення":
    st.header("🆕 Реєстрація замовлення")
    with st.form("new_order"):
        c, d = st.text_input("Замовник"), st.text_input("Виріб")
        qo, po = st.number_input("Кількість", min_value=1), st.number_input("Ціна продажу", min_value=0.0)
        if st.form_submit_button("Запустити у виробництво"):
            with engine.connect() as conn:
                conn.execute(text("INSERT INTO orders (customer, detail, qty, price, status) VALUES (:c, :d, :q, :p, 'Нове')"),
                             {"c": c, "d": d, "q": qo, "p": po})
                conn.commit()
            add_log(username, f"Створив замовлення для {c}")
            st.success("Успішно додано!")

# --- ⚙️ ПЕРСОНАЛ ---
elif choice == "⚙️ Персонал":
    st.header("👥 Керування працівниками")
    all_u = pd.read_sql("SELECT username, role FROM users", engine)
    st.table(all_u)
    with st.expander("➕ Зареєструвати нового"):
        with st.form("u_add"):
            u, p, r = st.text_input("Логін"), st.text_input("Пароль"), st.selectbox("Роль", ["Робочий", "Конструктор", "Адмін"])
            if st.form_submit_button("Створити"):
                try:
                    with engine.connect() as conn:
                        conn.execute(text("INSERT INTO users (username, password, role) VALUES (:u, :p, :r)"), {"u": u, "p": p, "r": r})
                        conn.commit()
                    add_log(username, f"Створив працівника: {u}")
                    st.rerun()
                except: st.error("Логін вже зайнятий")

# --- 📜 ЖУРНАЛ ДІЙ ---
elif choice == "📜 Журнал дій":
    st.header("📜 Історія активності (Cloud)")
    df_l = pd.read_sql("SELECT timestamp, username, action FROM logs ORDER BY id DESC LIMIT 100", engine)
    st.dataframe(df_l, use_container_width=True)

