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
    # Склад: ID, Название, Количество, Цена закупки
    cursor.execute('CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY, name TEXT, qty REAL, price REAL)')
    # Заказы: ID, Заказчик, Деталь, Количество, Цена продажи, Статус, Фото (пути к файлам)
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
        c1.metric("Стоимость материалов на складе", f"{df_inv['val'].iloc[0] or 0:,.2f} грн")
        c2.metric("Сумма активных заказов в работе", f"{df_ord['val'].iloc[0] or 0:,.2f} грн")

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
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.write(f"**Кол-во:** {row['qty']} шт.")
                        st.write(f"**Сумма:** {row['qty'] * row['price']:.2f} грн")
                        new_status = st.selectbox("Изменить статус", ["Новое", "Обработка", "Готово"], key=f"s_{row['id']}", index=["Новое", "Обработка", "Готово"].index(row['status']))
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
                                    ext = os.path.splitext(file_name).lower()
                                    if ext in ['.jpg', '.jpeg', '.png']:
                                        st.image(file_path, use_container_width=True)
                                    with open(file_path, "rb") as f:
                                        st.download_button(label=f"💾 {file_name}", data=f, file_name=file_name, key=f"dl_{file_path}_{row['id']}")
                        else:
                            st.info("Файлов нет")

                    with col3:
                        st.write("**Управление:**")
                        confirm_del = st.checkbox("Подтверждаю удаление", key=f"del_ch_{row['id']}")
                        if st.button("🗑️ Удалить заказ", key=f"del_btn_{row['id']}"):
                            if confirm_del:
                                if row['photo']:
                                    for f_path in row['photo'].split(","):
                                        if os.path.exists(f_path): os.remove(f_path)
                                conn.execute("DELETE FROM orders WHERE id = ?", (row['id'],))
                                conn.commit()
                                st.success("Заказ удален!")
                                st.rerun()
                            else:
                                st.warning("Нажмите галочку для удаления")
        else:
            st.warning("Выберите хотя бы один статус.")

    # --- 3. РАЗДЕЛ: СКЛАД ---
    elif choice == "📦 Склад":
        st.header("📦 Склад материалов")
        df_inv = pd.read_sql_query("SELECT * FROM inventory", conn)
        st.dataframe(df_inv, use_container_width=True)
        
        c1, c2 = st.columns(2)
        with c1.expander("➕ Добавить новый материал"):
            with st.form("add_inv"):
                n = st.text_input("Название материала")
                q = st.number_input("Количество", min_value=0.0)
                p = st.number_input("Цена закупки (за ед.)", min_value=0.0)
                if st.form_submit_button("Сохранить на склад"):
                    conn.execute("INSERT INTO inventory (name, qty, price) VALUES (?,?,?)", (n, q, p))
                    conn.commit(); st.rerun()
        
        with c2.expander("🗑️ Полное удаление позиции"):
            if not df_inv.empty:
                target = st.selectbox("Выберите материал", df_inv['name'].tolist())
                if st.button("Удалить позицию окончательно"):
                    conn.execute("DELETE FROM inventory WHERE name=?", (target,))
                    conn.commit(); st.rerun()

        # БЛОК КОРРЕКТИРОВКИ ЗАПАСОВ
        st.divider()
        st.subheader("📝 Быстрое списание / Корректировка остатков")
        if not df_inv.empty:
            col_adj1, col_adj2, col_adj3 = st.columns(3)
            selected_mat = col_adj1.selectbox("Выберите материал", df_inv['name'].tolist(), key="adj_sel")
            new_qty = col_adj2.number_input("Установите новый остаток", min_value=0.0, key="adj_val")
            if col_adj3.button("Обновить остаток"):
                conn.execute("UPDATE inventory SET qty = ? WHERE name = ?", (new_qty, selected_mat))
                conn.commit()
                st.success(f"Запас {selected_mat} успешно изменен!")
                st.rerun()

    # --- 4. РАЗДЕЛ: НОВЫЙ ЗАКАЗ ---
    elif choice == "📝 Новый заказ":
        st.header("🆕 Оформление нового заказа")
        with st.form("new_order", clear_on_submit=True):
            cust = st.text_input("Заказчик")
            det = st.text_input("Название детали / Изделия")
            q_ord = st.number_input("Количество (шт)", min_value=1)
            p_ord = st.number_input("Цена продажи (за 1 шт)", min_value=0.0)
            files = st.file_uploader("Загрузить файлы (Чертежи, SolidWorks, ZIP)", accept_multiple_files=True,
                                     type=['jpg','png','pdf','zip','rar','sldprt','sldasm','step','stp'])
            
            if st.form_submit_button("Запустить в производство"):
                saved_paths = []
                for f in files:
                    p = os.path.join(FILES_DIR, f"{cust}_{f.name}")
                    with open(p, "wb") as file:
                        file.write(file.getbuffer())
                    saved_paths.append(p)
                
                paths_str = ",".join(saved_paths)
                conn.execute("INSERT INTO orders (customer, detail, qty, price, status, photo) VALUES (?,?,?,?,'Новое',?)", 
                             (cust, det, q_ord, p_ord, paths_str))
                conn.commit()
                st.success(f"Заказ для '{cust}' успешно добавлен в систему!")

    conn.close()
