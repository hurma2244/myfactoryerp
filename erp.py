import streamlit as st
import sqlite3
import pandas as pd
import os

# --- НАСТРОЙКИ СИСТЕМЫ ---
DB_NAME = 'factory.db'
FILES_DIR = 'files'
PASSWORD = "admin"  # Ваш пароль для входа

if not os.path.exists(FILES_DIR):
    os.makedirs(FILES_DIR)

# --- ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY, name TEXT, qty REAL, price REAL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, customer TEXT, detail TEXT, qty INTEGER, price REAL, status TEXT, photo TEXT)')
    conn.commit()
    conn.close()

init_db()

# --- ПРОВЕРКА ПАРОЛЯ ---
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    if not st.session_state["authenticated"]:
        st.title("🔐 Вход в ERP Завода")
        pwd = st.text_input("Введите пароль завода:", type="password")
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
    st.sidebar.title("🏭 Управление Заводом")
    
    menu = ["📊 Аналитика", "🛠 Производство", "📦 Склад", "📝 Новый заказ"]
    choice = st.sidebar.selectbox("Меню", menu)
    
    conn = sqlite3.connect(DB_NAME)

    # --- 1. РАЗДЕЛ: АНАЛИТИКА ---
    if choice == "📊 Аналитика":
        st.header("📈 Состояние предприятия")
        df_inv = pd.read_sql_query("SELECT SUM(qty * price) as val FROM inventory", conn)
        df_ord = pd.read_sql_query("SELECT SUM(qty * price) as val FROM orders WHERE status != 'Готово'", conn)
        
        c1, c2 = st.columns(2)
        c1.metric("Склад (стоимость материалов)", f"{df_inv['val'].iloc[0] or 0:,.2f} грн")
        c2.metric("Заказы в работе (сумма)", f"{df_ord['val'].iloc[0] or 0:,.2f} грн")

    # --- 2. РАЗДЕЛ: ПРОИЗВОДСТВО ---
    elif choice == "🛠 Производство":
        st.header("📋 Журнал производства")
        search = st.text_input("🔍 Поиск (клиент или деталь):")
        
        filter_status = st.multiselect("Фильтр по статусу:", ["Новое", "Обработка", "Готово"], default=["Новое", "Обработка", "Готово"])
        
        if filter_status:
            query = "SELECT * FROM orders WHERE status IN ({})".format(','.join(['?']*len(filter_status)))
            params = filter_status
            if search:
                query += " AND (customer LIKE ? OR detail LIKE ?)"
                params.extend([f'%{search}%', f'%{search}%'])
            
            df_orders = pd.read_sql_query(query, conn, params=params)

            for index, row in df_orders.iterrows():
                status_emoji = "🟢" if row['status'] == "Готово" else "🟠" if row['status'] == "Обработка" else "🔵"
                with st.expander(f"{status_emoji} Заказ №{row['id']} | {row['customer']} | {row['detail']}"):
                    col1, col2, col3 = st.columns([1, 1, 1])
                    
                    with col1:
                        st.write(f"**Кол-во:** {row['qty']} шт.")
                        st.write(f"**Сумма:** {row['qty'] * row['price']:.2f} грн")
                        new_status = st.selectbox("Статус", ["Новое", "Обработка", "Готово"], key=f"s_{row['id']}", index=["Новое", "Обработка", "Готово"].index(row['status']))
                        if st.button("Обновить статус", key=f"b_{row['id']}"):
                            conn.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, row['id']))
                            conn.commit()
                            st.rerun()

                    with col2:
                        st.write("**Файлы и чертежи:**")
                        if row['photo']:
                            file_list = row['photo'].split(",")
                            for file_path in file_list:
                                if os.path.exists(file_path):
                                    file_name = os.path.basename(file_path)
                                    ext = os.path.splitext(file_name)[1].lower()
                                    if ext in ['.jpg', '.jpeg', '.png']:
                                        st.image(file_path, use_container_width=True)
                                    with open(file_path, "rb") as f:
                                        st.download_button(label=f"💾 {file_name}", data=f, file_name=file_name, key=f"dl_{file_path}_{row['id']}")
                        else:
                            st.info("Файлов нет")

                    with col3:
                        st.write("**Удаление:**")
                        confirm_del = st.checkbox("Подтверждаю удаление", key=f"del_ch_{row['id']}")
                        if st.button("🗑️ Удалить заказ", key=f"del_btn_{row['id']}"):
                            if confirm_del:
                                if row['photo']:
                                    for f_path in row['photo'].split(","):
                                        if os.path.exists(f_path): os.remove(f_path)
                                conn.execute("DELETE FROM orders WHERE id = ?", (row['id'],))
                                conn.commit()
                                st.success("Удалено!")
                                st.rerun()
                            else:
                                st.warning("Поставьте галочку")
        else:
            st.warning("Выберите хотя бы один статус в фильтре.")

    # --- 3. РАЗДЕЛ: СКЛАД ---
    elif choice == "📦 Склад":
        st.header("📦 Склад материалов")
        df_inv = pd.read_sql_query("SELECT * FROM inventory", conn)
        st.dataframe(df_inv, use_container_width=True)
        
        c1, c2 = st.columns(2)
        with c1.expander("➕ Добавить материал"):
            with st.form("add_inv"):
                n = st.text_input("Название")
                q = st.number_input("Кол-во", min_value=0.0)
                p = st.number_input("Цена закупки", min_value=0.0)
                if st.form_submit_button("Сохранить"):
                    conn.execute("INSERT INTO inventory (name, qty, price) VALUES (?,?,?)", (n, q, p))
                    conn.commit(); st.rerun()
        
        with c2.expander("🗑️ Удалить со склада"):
            if not df_inv.empty:
                target = st.selectbox("Материал для удаления", df_inv['name'].tolist())
                if st.button("Удалить окончательно"):
                    conn.execute("DELETE FROM inventory WHERE name=?", (target,))
                    conn.commit(); st.rerun()

    # --- 4. РАЗДЕЛ: НОВЫЙ ЗАКАЗ ---
    elif choice == "📝 Новый заказ":
        st.header("🆕 Оформление замовлення")
        with st.form("new_order", clear_on_submit=True):
            cust = st.text_input("Заказчик")
            det = st.text_input("Деталь")
            q_ord = st.number_input("Кол-во", min_value=1)
            p_ord = st.number_input("Цена продажи (за шт)", min_value=0.0)
            files = st.file_uploader("Чертежи, фото, модели SolidWorks", accept_multiple_files=True,
                                     type=['jpg','png','pdf','zip','rar','sldprt','sldasm','step','stp'])
            
            if st.form_submit_button("В работу"):
                saved_paths = []
                for f in files:
                    p = os.path.join(FILES_DIR, f"{cust}_{f.name}")
                    with open(p, "wb") as file:
                        file.write(f.getbuffer())
                    saved_paths.append(p)
                
                paths_str = ",".join(saved_paths)
                conn.execute("INSERT INTO orders (customer, detail, qty, price, status, photo) VALUES (?,?,?,?,'Новое',?)", 
                             (cust, det, q_ord, p_ord, paths_str))
                conn.commit()
                st.success(f"Заказ для {cust} успешно создан!")

    conn.close()
