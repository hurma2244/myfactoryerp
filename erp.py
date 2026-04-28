import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import os
import shutil
from datetime import datetime, timedelta

# --- 1. НАЛАШТУВАННЯ СТОРІНКИ ---
st.set_page_config(page_title="Factory ERP Pro (Cloud)", layout="wide")

# --- 2. ПІДКЛЮЧЕННЯ ДО SUPABASE ---
# Рядок підключення. ЗАМІНІТЬ [ВАШ_ПАРОЛЬ_ТУТ] на реальний пароль!
DB_URI = "postgresql://postgres:ВАШ_ПАРОЛЬ_ТУТ@db.sumpnxmxpdzwchanewnj.supabase.co:5432/postgres"

engine = create_engine(DB_URI)
UPLOAD_DIR = 'order_files'
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# --- 3. ІНІЦІАЛІЗАЦІЯ ХМАРНОЇ БД ---
def init_db():
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS inventory (id SERIAL PRIMARY KEY, name TEXT, qty REAL, price REAL);
            CREATE TABLE IF NOT EXISTS orders (id SERIAL PRIMARY KEY, customer TEXT, detail TEXT, qty INTEGER, price REAL, status TEXT, file_path TEXT);
            CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT, last_seen TIMESTAMP);
            CREATE TABLE IF NOT EXISTS logs (id SERIAL PRIMARY KEY, timestamp TIMESTAMP, username TEXT, action TEXT);
            
            -- Гарантований адмін
            INSERT INTO users (username, password, role, last_seen) 
            VALUES ('admin', 'admin123', 'Адмін', CURRENT_TIMESTAMP) 
            ON CONFLICT (username) DO UPDATE SET password = EXCLUDED.password;
        """))
        conn.commit()

try:
    init_db()
except Exception as e:
    st.error(f"Помилка підключення до Supabase: {e}")

def add_log(username, action):
    try:
        with engine.connect() as conn:
            conn.execute(text("INSERT INTO logs (timestamp, username, action) VALUES (:t, :u, :a)"),
                         {"t": datetime.now(), "u": str(username), "a": action})
            conn.commit()
    except: pass

# --- 4. АВТОРИЗАЦІЯ ---
if "authenticated" not in st.session_state:
    st.title("🏭 ERP Система (Хмарне зберігання 24/7)")
    st.info("Вхід: admin / admin123")
    u_in = st.text_input("Логін").strip()
    p_in = st.text_input("Пароль", type="password").strip()
    if st.button("Увійти"):
        with engine.connect() as conn:
            res = conn.execute(text("SELECT username, role FROM users WHERE username=:u AND password=:p"),
                               {"u": u_in, "p": p_in}).fetchone()
            if res:
                st.session_state["authenticated"] = True
                st.session_state["username"] = res[0]
                st.session_state["role"] = res[1]
                add_log(res[0], "Увійшов у систему")
                st.rerun()
            else: st.error("❌ Невірний логін або пароль")
    st.stop()

# Оновлення активності
with engine.connect() as conn:
    conn.execute(text("UPDATE users SET last_seen = :t WHERE username = :u"), 
                 {"t": datetime.now(), "u": st.session_state["username"]})
    conn.commit()

# --- 5. ІНТЕРФЕЙС ---
user_role = st.session_state["role"]
username = st.session_state["username"]

st.sidebar.title(f"👤 {username}")
st.sidebar.info(f"Роль: {user_role}")

# Онлайн
st.sidebar.subheader("🟢 Онлайн")
five_mins_ago = datetime.now() - timedelta(minutes=5)
with engine.connect() as conn:
    online_df = pd.read_sql(text("SELECT username FROM users WHERE last_seen > :t"), conn, params={"t": five_mins_ago})
for u in online_df['username']:
    st.sidebar.write(f"● {u}")

if st.sidebar.button("Вийти"):
    st.session_state.clear()
    st.rerun()

menu = ["📊 Аналітика", "🛠 Виробництво", "📦 Склад"]
if user_role == "Адмін": menu += ["📝 Нове замовлення", "⚙️ Персонал", "📜 Журнал дій"]
choice = st.sidebar.selectbox("Меню", menu)

# --- 6. РОЗДІЛИ ---

if choice == "📦 Склад":
    st.header("📦 Склад")
    q = "SELECT name, qty, price FROM inventory" if user_role == "Адмін" else "SELECT name, qty FROM inventory"
    df_inv = pd.read_sql(text(q), engine)
    st.dataframe(df_inv, use_container_width=True)
    
    if user_role == "Адмін":
        st.subheader("📝 Корегування залишків")
        if not df_inv.empty:
            c1, c2, c3 = st.columns(3)
            mat = c1.selectbox("Матеріал", df_inv['name'].tolist())
            cur_val = float(df_inv[df_inv['name']==mat]['qty'].iloc[0])
            new_q = c2.number_input("Нова к-ть", value=cur_val)
            if c3.button("Оновити"):
                with engine.connect() as conn:
                    conn.execute(text("UPDATE inventory SET qty=:q WHERE name=:n"), {"q": new_q, "n": mat})
                    conn.commit()
                st.rerun()
        
        st.divider()
        col1, col2 = st.columns(2)
        with col1.expander("➕ Додати позицію"):
            with st.form("add_mat"):
                n, q, p = st.text_input("Назва"), st.number_input("К-ть"), st.number_input("Ціна")
                if st.form_submit_button("Зберегти"):
                    with engine.connect() as conn:
                        conn.execute(text("INSERT INTO inventory (name, qty, price) VALUES (:n, :q, :p)"), {"n": n, "q": q, "p": p})
                        conn.commit()
                    st.rerun()
        with col2.expander("🗑️ Видалити зі складу"):
            if not df_inv.empty:
                d_m = st.selectbox("Що видалити?", df_inv['name'].tolist(), key="del_inv")
                if st.button("Видалити назавжди"):
                    with engine.connect() as conn:
                        conn.execute(text("DELETE FROM inventory WHERE name=:n"), {"n": d_m})
                        conn.commit()
                    st.rerun()

elif choice == "🛠 Виробництво":
    st.header("🛠 Журнал виробництва")
    df_orders = pd.read_sql(text("SELECT * FROM orders ORDER BY id DESC"), engine)
    for _, row in df_orders.iterrows():
        with st.expander(f"📦 №{row['id']} | {row['customer']} | {row['detail']} ({row['status']})"):
            c1, c2 = st.columns(2)
            with c1:
                st.write(f"**Кількість:** {row['qty']} шт.")
                if row['file_path'] and os.path.exists(row['file_path']):
                    st.write("**Файли:**")
                    for f_name in os.listdir(row['file_path']):
                        f_p = os.path.join(row['file_path'], f_name)
                        with open(f_p, "rb") as fb:
                            st.download_button(f"📥 {f_name}", fb, file_name=f_name, key=f"dl_{row['id']}_{f_name}")
                if user_role == "Адмін":
                    st.write(f"**Ціна:** {row['price']} грн")
                    if st.button("🗑️ Видалити замовлення", key=f"del_o_{row['id']}"):
                        with engine.connect() as conn:
                            conn.execute(text("DELETE FROM orders WHERE id=:id"), {"id": row['id']})
                            conn.commit()
                        st.rerun()
            with c2:
                statuses = ["Нове", "Обробка", "Готово"]
                idx = statuses.index(row['status']) if row['status'] in statuses else 0
                new_s = st.selectbox("Статус", statuses, index=idx, key=f"st_{row['id']}")
                if st.button("Зберегти статус", key=f"bt_{row['id']}"):
                    with engine.connect() as conn:
                        conn.execute(text("UPDATE orders SET status=:s WHERE id=:id"), {"s": new_s, "id": row['id']})
                        conn.commit()
                    st.rerun()

elif choice == "📝 Нове замовлення" and user_role == "Адмін":
    st.header("📝 Реєстрація замовлення")
    with st.form("n_ord", clear_on_submit=True):
        c, d = st.text_input("Клієнт"), st.text_input("Виріб")
        qo, po = st.number_input("К-ть", min_value=1), st.number_input("Ціна")
        files = st.file_uploader("Файли", accept_multiple_files=True)
        if st.form_submit_button("Створити"):
            path = None
            if files:
                path = os.path.join(UPLOAD_DIR, f"order_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                os.makedirs(path)
                for f in files:
                    with open(os.path.join(path, f.name), "wb") as fs: fs.write(f.getbuffer())
            with engine.connect() as conn:
                conn.execute(text("INSERT INTO orders (customer, detail, qty, price, status, file_path) VALUES (:c, :d, :q, :p, 'Нове', :f)"),
                             {"c": c, "d": d, "q": qo, "p": po, "f": path})
                conn.commit()
            st.success("Додано!")

elif choice == "⚙️ Персонал" and user_role == "Адмін":
    st.header("👥 Персонал")
    df_u = pd.read_sql(text("SELECT username, role FROM users"), engine)
    st.table(df_u)
    
    col_u1, col_u2 = st.columns(2)
    with col_u1.expander("➕ Додати працівника"):
        with st.form("u_add"):
            u, p, r = st.text_input("Логін"), st.text_input("Пароль"), st.selectbox("Роль", ["Робочий", "Конструктор", "Адмін"])
            if st.form_submit_button("Створити"):
                with engine.connect() as conn:
                    conn.execute(text("INSERT INTO users (username, password, role, last_seen) VALUES (:u, :p, :r, :t)"), 
                                 {"u": u, "p": p, "r": r, "t": datetime.now()})
                    conn.commit()
                st.rerun()
    with col_u2.expander("🗑️ Видалити акаунт"):
        target = st.selectbox("Оберіть користувача", df_u['username'].tolist(), key="del_user")
        if target != 'admin':
            if st.button("Видалити назавжди"):
                with engine.connect() as conn:
                    conn.execute(text("DELETE FROM users WHERE username=:u"), {"u": target})
                    conn.commit()
                st.rerun()

elif choice == "📊 Аналітика" and user_role == "Адмін":
    st.header("📊 Фінанси")
    with engine.connect() as conn:
        t_inv = conn.execute(text("SELECT SUM(qty * price) FROM inventory")).scalar() or 0
        t_ord = conn.execute(text("SELECT SUM(qty * price) FROM orders WHERE status != 'Готово'")).scalar() or 0
    st.metric("Вартість складу", f"{t_inv:,.2f} грн")
    st.metric("В роботі", f"{t_ord:,.2f} грн")

elif choice == "📜 Журнал дій" and user_role == "Адмін":
    st.header("📜 Журнал")
    df_logs = pd.read_sql(text("SELECT timestamp, username, action FROM logs ORDER BY id DESC LIMIT 100"), engine)
    st.dataframe(df_logs, use_container_width=True)
