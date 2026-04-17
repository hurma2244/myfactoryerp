import streamlit as st
import sqlite3
import pandas as pd
import os

# --- НАСТРОЙКИ ---
DB_NAME = 'factory.db'
FILES_DIR = 'files'
PASSWORD = "admin" 

if not os.path.exists(FILES_DIR):
    os.makedirs(FILES_DIR)

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY, name TEXT, qty REAL, price REAL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, customer TEXT, detail TEXT, qty INTEGER, price REAL, status TEXT, photo TEXT)')
    conn.commit()
    conn.close()

init_db()

def check_password():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    if not st.session_state["authenticated"]:
        st.title("🔐 Вход в ERP Завода")
        pwd = st.text_input("Пароль:", type="password")
        if st.button("Войти"):
            if pwd == PASSWORD:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("❌ Неверный пароль")
        return False
    return True

if check_password():
    st.set_page_config(page_title="Factory ERP Pro", layout="wide")
    st.sidebar.title("🏭 Управление")
    menu = ["📊 Аналитика", "🛠 Производство", "📦 Склад", "📝 Новый заказ"]
    choice = st.sidebar.selectbox("Меню", menu)
    conn = sqlite3.connect(DB_NAME)

    if choice == "📊 Аналитика":
        st.header("📈 Состояние предприятия")
        df_inv = pd.read_sql_query("SELECT SUM(qty * price) as val FROM inventory", conn)
        df_ord = pd.read_sql_query("SELECT SUM(qty * price) as val FROM orders WHERE status != 'Готово'", conn)
        c1, c2 = st.columns(2)
        c1.metric("Склад (закупка)", f"{df_inv['val'].iloc[0] or 0:,.2f} грн")
        c2.metric("Заказы в работе", f"{df_ord['val'].iloc[0] or 0:,.2f} грн")

    elif choice == "🛠 Производство":
        st.header("📋 Журнал производства")
        search = st.text_input("🔍 Поиск (клиент или деталь):")
        query = "SELECT * FROM orders"
        if search: query += f" WHERE customer LIKE '%{search}%' OR detail LIKE '%{search}%'"
        df_orders = pd.read_sql_query(query, conn)

        for index, row in df_orders.iterrows():
            with st.expander(f"📦 Заказ №{row['id']} | {row['customer']} | {row['detail']} ({row['status']})"):
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.write(f"**Кол-во:** {row['qty']} шт. | **Сумма:** {row['qty'] * row['price']:.2f} грн")
                    new_status = st.selectbox("Статус", ["Новое", "Обработка", "Готово"], key=f"s_{row['id']}", index=["Новое", "Обработка", "Готово"].index(row['status']))
                    if st.button("Обновить статус", key=f"b_{row['id']}"):
                        conn.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, row['id']))
                        conn.commit()
                        st.rerun()

                with col2:
                    st.write("**Файлы и чертежи:**")
                    if row['photo']:
                        file_list = row['photo'].split(",") # Разбиваем строку путей на список
                        for file_path in file_list:
                            if os.path.exists(file_path):
                                file_name = os.path.basename(file_path)
                                ext = os.path.splitext(file_name)[1].lower()
                                
                                if ext in ['.jpg', '.jpeg', '.png']:
                                    st.image(file_path, use_container_width=True)
                                
                                with open(file_path, "rb") as f:
                                    st.download_button(label=f"💾 Скачать {file_name}", data=f, file_name=file_name, key=file_path+str(row['id']))
                    else:
                        st.info("Нет файлов")

    elif choice == "📦 Склад":
        st.header("📦 Склад материалов")
        df_inventory = pd.read_sql_query("SELECT * FROM inventory", conn)
        st.dataframe(df_inventory, use_container_width=True)
        
        c1, c2 = st.columns(2)
        with c1.expander("➕ Добавить"):
            with st.form("add"):
                n = st.text_input("Название")
                q = st.number_input("Кол-во", min_value=0.0)
                p = st.number_input("Цена", min_value=0.0)
                if st.form_submit_button("ОК"):
                    conn.execute("INSERT INTO inventory (name, qty, price) VALUES (?,?,?)", (n,q,p))
                    conn.commit(); st.rerun()
        
        with c2.expander("🗑️ Удалить"):
            if not df_inventory.empty:
                target = st.selectbox("Материал", df_inventory['name'].tolist())
                if st.button("Удалить навсегда"):
                    conn.execute("DELETE FROM inventory WHERE name=?", (target,))
                    conn.commit(); st.rerun()

    elif choice == "📝 Новый заказ":
        st.header("🆕 Оформление")
        with st.form("new_order", clear_on_submit=True):
            cust = st.text_input("Заказчик")
            det = st.text_input("Деталь")
            q_ord = st.number_input("Кол-во", min_value=1)
            p_ord = st.number_input("Цена за шт", min_value=0.0)
            # ВКЛЮЧАЕМ МУЛЬТИЗАГРУЗКУ
            uploaded_files = st.file_uploader("Чертежи, архивы, модели SolidWorks", 
                                             type=['jpg','png','pdf','zip','rar','sldprt','sldasm','step','stp'], 
                                             accept_multiple_files=True)
            
            if st.form_submit_button("В работу"):
                saved_paths = []
                for uploaded_file in uploaded_files:
                    path = os.path.join(FILES_DIR, f"{cust}_{uploaded_file.name}")
                    with open(path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    saved_paths.append(path)
                
                # Сохраняем все пути через запятую
                all_paths = ",".join(saved_paths)
                conn.execute("INSERT INTO orders (customer, detail, qty, price, status, photo) VALUES (?,?,?,?,'Новое',?)", 
                             (cust, det, q_ord, p_ord, all_paths))
                conn.commit()
                st.success("Заказ и файлы приняты!")

    conn.close()
