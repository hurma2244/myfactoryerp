import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text, URL
import requests
import os
from datetime import datetime, timedelta

# --- 1. НАЛАШТУВАННЯ СТОРІНКИ ---
st.set_page_config(page_title="Factory ERP Cloud Pro", layout="wide")

# --- 2. КОНФІГУРАЦІЯ (ПРЯМЕ ПІДКЛЮЧЕННЯ 5432) ---
TG_TOKEN = "8743391673:AAGPXg-5-87Y881bO5XWhftEPPugKNK4y88"
TG_CHAT_ID = "-1003848428987"

# Використовуємо спеціальний інструмент для збірки посилання без помилок
db_url = URL.create(
    drivername="postgresql+psycopg2",
    username="postgres",
    password="qWeRtY1234Qrohjt",
    host="db.sumpnxmxpdzwchanewnj.supabase.co", # ТІЛЬКИ ЦЕЙ АДРЕС, БЕЗ // ТА БЕЗ supabase.com НА ПОЧАТКУ
    port=5432,
    database="postgres",
    query={"sslmode": "require"},
)

# Створення двигуна
engine = create_engine(db_url, pool_pre_ping=True)

# --- 3. ФУНКЦІЯ TELEGRAM ---
def send_to_telegram(file_bytes, file_name, caption):
    url = f"https://telegram.org{TG_TOKEN}/sendDocument"
    files = {'document': (file_name, file_bytes)}
    data = {'chat_id': TG_CHAT_ID, 'caption': caption}
    try:
        requests.post(url, files=files, data=data, timeout=15)
    except:
        pass

# --- 4. ІНІЦІАЛІЗАЦІЯ БД ---
def init_db():
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS inventory (id SERIAL PRIMARY KEY, name TEXT, qty REAL, price REAL);
                CREATE TABLE IF NOT EXISTS orders (id SERIAL PRIMARY KEY, customer TEXT, detail TEXT, qty INTEGER, price REAL, status TEXT, has_files BOOLEAN DEFAULT FALSE);
                CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT, last_seen TIMESTAMP);
                CREATE TABLE IF NOT EXISTS logs (id SERIAL PRIMARY KEY, timestamp TIMESTAMP, username TEXT, action TEXT);
                
                INSERT INTO users (username, password, role, last_seen) 
                VALUES ('admin', 'admin123', 'Адмін', CURRENT_TIMESTAMP) 
                ON CONFLICT (username) DO UPDATE SET password = EXCLUDED.password;
            """))
            conn.commit()
    except Exception as e:
        st.error(f"Помилка бази: {e}")

init_db()

# --- 5. АВТОРИЗАЦІЯ ---
if "authenticated" not in st.session_state:
    st.title("🏭 ERP Cloud (24/7)")
    st.info("Вхід: **admin** / **admin123**")
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
                st.rerun()
            else:
                st.error("❌ Невірний логін або пароль")
    st.stop()

# Оновлення активності
with engine.connect() as conn:
    conn.execute(text("UPDATE users SET last_seen = NOW() WHERE username = :u"), {"u": st.session_state["username"]})
    conn.commit()

user_role = st.session_state["role"]
username = st.session_state["username"]

# --- 6. SIDEBAR ---
st.sidebar.title(f"👤 {username}")
st.sidebar.info(f"Роль: {user_role}")

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
if user_role == "Адмін": menu += ["📝 Нове замовлення", "⚙️ Персонал"]
choice = st.sidebar.selectbox("Меню", menu)

# --- 7. РОЗДІЛИ ---

if choice == "📦 Склад":
    st.header("📦 Склад")
    df_inv = pd.read_sql(text("SELECT * FROM inventory ORDER BY name"), engine)
    st.dataframe(df_inv, use_container_width=True)
    
    if user_role == "Адмін":
        st.subheader("📝 Корегування залишків")
        if not df_inv.empty:
            c1, c2, c3 = st.columns(3)
            mat = c1.selectbox("Матеріал", df_inv['name'].tolist())
            cur_v = float(df_inv[df_inv['name']==mat]['qty'].iloc[0])
            new_q = c2.number_input("Кількість", value=cur_v)
            if c3.button("Оновити"):
                with engine.connect() as conn:
                    conn.execute(text("UPDATE inventory SET qty=:q WHERE name=:n"), {"q": new_q, "n": mat})
                    conn.commit()
                st.rerun()
        
        col1, col2 = st.columns(2)
        with col1.expander("➕ Додати"):
            with st.form("add_mat"):
                n = st.text_input("Назва")
                q = st.number_input("К-ть", min_value=0.0)
                p = st.number_input("Ціна закупівлі", min_value=0.0)
                if st.form_submit_button("Зберегти"):
                    with engine.connect() as conn:
                        conn.execute(text("INSERT INTO inventory (name, qty, price) VALUES (:n, :q, :p)"), {"n": n, "q": q, "p": p})
                        conn.commit()
                    st.rerun()
        with col2.expander("🗑️ Видалити"):
            if not df_inv.empty:
                d_m = st.selectbox("Що видалити?", df_inv['name'].tolist(), key="del_m")
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
            st.write(f"**Кількість:** {row['qty']} шт.")
            if row['has_files']:
                st.success("📂 Файли тех. документації в Telegram-архіві.")
            
            if user_role == "Адмін":
                st.write(f"**Ціна продажу:** {row['price']} грн")
                if st.button("🗑️ Видалити замовлення", key=f"del_{row['id']}"):
                    with engine.connect() as conn:
                        conn.execute(text("DELETE FROM orders WHERE id=:id"), {"id": row['id']})
                        conn.commit()
                    st.rerun()
            
            new_s = st.selectbox("Статус", ["Нове", "Обробка", "Готово"], 
                                 index=["Нове", "Обробка", "Готово"].index(row['status']), key=f"st_{row['id']}")
            if st.button("Зберегти статус", key=f"bt_{row['id']}"):
                with engine.connect() as conn:
                    conn.execute(text("UPDATE orders SET status=:s WHERE id=:id"), {"s": new_s, "id": row['id']})
                    conn.commit()
                st.rerun()

elif choice == "📝 Нове замовлення":
    st.header("📝 Реєстрація замовлення")
    with st.form("n_ord", clear_on_submit=True):
        c, d = st.text_input("Клієнт"), st.text_input("Виріб")
        qo, po = st.number_input("К-ть", min_value=1), st.number_input("Ціна")
        files = st.file_uploader("Файли", accept_multiple_files=True)
        if st.form_submit_button("Створити"):
            has_f = False
            if files:
                has_f = True
                for f in files:
                    send_to_telegram(f.getvalue(), f.name, f"🆕 Замовлення для {c}: {d}")
            with engine.connect() as conn:
                conn.execute(text("INSERT INTO orders (customer, detail, qty, price, status, has_files) VALUES (:c, :d, :q, :p, 'Нове', :hf)"),
                             {"c": c, "d": d, "q": qo, "p": po, "hf": has_f})
                conn.commit()
            st.success("✅ Створено! Файли надіслано в Telegram.")

