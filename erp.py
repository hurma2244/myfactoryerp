import streamlit as st
import sqlite3
import pandas as pd
import os

# --- НАЛАШТУВАННЯ ---
DB_NAME = 'factory.db'
FILES_DIR = 'files'
PASSWORD = "admin"  # Пароль для входу

if not os.path.exists(FILES_DIR):
    os.makedirs(FILES_DIR)

# --- БАЗА ДАНИХ ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Склад: ID, Назва, Кількість, Ціна закупівлі
    cursor.execute('CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY, name TEXT, qty REAL, price REAL)')
    # Замовлення: ID, Замовник, Деталь, Кількість, Ціна продажу, Статус, Фото
    cursor.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, customer TEXT, detail TEXT, qty INTEGER, price REAL, status TEXT, photo TEXT)')
    conn.commit()
    conn.close()

init_db()

# --- АВТОРИЗАЦІЯ ---
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    
    if not st.session_state["authenticated"]:
        st.title("🔐 Вхід у систему ERP")
        pwd = st.text_input("Введіть пароль заводу:", type="password")
        if st.button("Увійти"):
            if pwd == PASSWORD:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("❌ Невірний пароль")
        return False
    return True

if check_password():
    st.set_page_config(page_title="Factory ERP Pro", layout="wide")
    st.sidebar.title("🏭 Керування заводом")
    
    menu = ["📊 Аналітика", "🛠 Виробництво", "📦 Склад", "📝 Нове замовлення"]
    choice = st.sidebar.selectbox("Оберіть розділ", menu)
    
    conn = sqlite3.connect(DB_NAME)

    # --- РОЗДІЛ: АНАЛІТИКА ---
    if choice == "📊 Аналітика":
        st.header("📈 Стан підприємства")
        df_inv = pd.read_sql_query("SELECT SUM(qty * price) as val FROM inventory", conn)
        df_ord = pd.read_sql_query("SELECT SUM(qty * price) as val FROM orders WHERE status != 'Готово'", conn)
        
        col1, col2 = st.columns(2)
        col1.metric("Вартість матеріалів на складі", f"{df_inv['val'].iloc[0] or 0:,.2f} грн")
        col2.metric("Сума замовлень у роботі", f"{df_ord['val'].iloc[0] or 0:,.2f} грн")

    # --- РОЗДІЛ: ВИРОБНИЦТВО ---
    elif choice == "🛠 Виробництво":
        st.header("📋 Журнал замовлень")
        search = st.text_input("🔍 Пошук замовлення (деталь або клієнт):")
        query = "SELECT * FROM orders"
        if search:
            query += f" WHERE customer LIKE '%{search}%' OR detail LIKE '%{search}%'"
        
        df_orders = pd.read_sql_query(query, conn)
        
        for index, row in df_orders.iterrows():
            status_colors = {"Нове": "🔵", "Обробка": "🟠", "Готово": "🟢"}
            with st.expander(f"{status_colors.get(row['status'], '⚪')} Замовлення №{row['id']} | {row['customer']} | {row['detail']}"):
                c1, c2, c3 = st.columns(3)
                c1.write(f"**Кількість:** {row['qty']} шт.")
                c1.write(f"**Ціна замовлення:** {row['qty'] * row['price']:.2f} грн")
                
                new_status = c2.selectbox("Змінити статус", ["Нове", "Обробка", "Готово"], key=f"stat_{row['id']}", index=["Нове", "Обробка", "Готово"].index(row['status']))
                if c2.button("Оновити статус", key=f"btn_{row['id']}"):
                    conn.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, row['id']))
                    conn.commit()
                    st.rerun()
                
                if row['photo']:
                    c3.image(row['photo'], caption="Креслення/Фото", use_container_width=True)
                else:
                    c3.info("Фото відсутнє")

    # --- РОЗДІЛ: СКЛАД ---
    elif choice == "📦 Склад":
        st.header("📦 Облік матеріалів")
        df_inventory = pd.read_sql_query("SELECT * FROM inventory", conn)
        st.dataframe(df_inventory, use_container_width=True)
        
        col1, col2 = st.columns(2)
        
        # Додавання
        with col1.expander("➕ Додати новий матеріал"):
            with st.form("add_mat"):
                name = st.text_input("Назва матеріалу")
                q = st.number_input("Кількість", min_value=0.0)
                p = st.number_input("Ціна за одиницю (закупка)", min_value=0.0)
                if st.form_submit_button("Зберегти на склад"):
                    conn.execute("INSERT INTO inventory (name, qty, price) VALUES (?, ?, ?)", (name, q, p))
                    conn.commit()
                    st.success("Матеріал додано!")
                    st.rerun()

        # Видалення
        with col2.expander("🗑️ Видалити матеріал зі складу"):
            if not df_inventory.empty:
                list_of_materials = df_inventory['name'].tolist()
                mat_to_delete = st.selectbox("Оберіть матеріал для видалення:", list_of_materials)
                confirm = st.checkbox(f"Я підтверджую видалення '{mat_to_delete}'")
                if st.button("❌ Видалити остаточно"):
                    if confirm:
                        conn.execute("DELETE FROM inventory WHERE name = ?", (mat_to_delete,))
                        conn.commit()
                        st.success(f"'{mat_to_delete}' видалено!")
                        st.rerun()
                    else:
                        st.warning("Будь ласка, поставте галочку для підтвердження.")
            else:
                st.info("На складі порожньо.")

        # Коригування
        st.divider()
        st.subheader("📝 Швидке списання/коригування")
        if not df_inventory.empty:
            c1, c2, c3 = st.columns(3)
            selected_mat = c1.selectbox("Матеріал для коригування", df_inventory['name'].tolist(), key="adj_mat")
            new_qty = c2.number_input("Встановіть нову кількість", min_value=0.0, key="adj_qty")
            if c3.button("Оновити кількість"):
                conn.execute("UPDATE inventory SET qty = ? WHERE name = ?", (new_qty, selected_mat))
                conn.commit()
                st.success("Дані оновлено!")
                st.rerun()

    # --- РОЗДІЛ: НОВЕ ЗАМОВЛЕННЯ ---
    elif choice == "📝 Нове замовлення":
        st.header("🆕 Оформлення замовлення")
        with st.form("new_order"):
            c1, c2 = st.columns(2)
            cust = c1.text_input("Замовник")
            det = c1.text_input("Назва деталі")
            q_ord = c2.number_input("Кількість деталей", min_value=1)
            p_ord = c2.number_input("Ціна продажу за 1 шт", min_value=0.0)
            file = st.file_uploader("Завантажити фото/креслення", type=['jpg', 'png', 'pdf'])
            
            if st.form_submit_button("Запустити у виробництво"):
                path = ""
                if file:
                    path = os.path.join(FILES_DIR, file.name)
                    with open(path, "wb") as f:
                        f.write(file.getbuffer())
                
                conn.execute("INSERT INTO orders (customer, detail, qty, price, status, photo) VALUES (?, ?, ?, ?, 'Нове', ?)", 
                             (cust, det, q_ord, p_ord, path))
                conn.commit()
                st.success(f"Замовлення для {cust} прийнято!")

    conn.close()
