import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import time
import io

# --- 1. CẤU HÌNH TRANG WEB & CSS ---
st.set_page_config(page_title="Hệ Thống Quản Lý Tài Khoản", page_icon="🎮", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #f4f6f9; font-family: 'Segoe UI', sans-serif; }
    
    .custom-header {
        background-color: #2c3e50; padding: 15px 20px; border-radius: 5px;
        margin-bottom: 20px; color: white; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .custom-header h1 { margin: 0; font-size: 24px; font-weight: 700; color: white !important; }
    
    .footer {
        position: fixed; left: 0; bottom: 0; width: 100%;
        background-color: #f4f6f9; color: #7f8c8d; text-align: right;
        padding: 10px 30px; font-style: italic; font-size: 12px; border-top: 1px solid #ddd; z-index: 999;
    }
    
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# --- 2. XỬ LÝ DATABASE (BỎ CỘT is_paid) ---
DB_FILE = "dulieu_game.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Quay về bảng đơn giản ban đầu
    c.execute('''CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            device_info TEXT,
            reg_date TEXT,
            duration INTEGER)''')
    
    # Data mẫu
    c.execute("SELECT count(*) FROM customers")
    if c.fetchone()[0] == 0:
        sample_data = [
            ("Nguyễn Văn A", "PC Gaming 01", datetime.now().strftime("%d/%m/%Y"), 1),
            ("Trần Thị B", "PS5 Standard", "01/01/2026", 3),
            ("Lê Văn C", "Steam Deck OLED", "20/12/2025", 6)
        ]
        c.executemany("INSERT INTO customers (name, device_info, reg_date, duration) VALUES (?, ?, ?, ?)", sample_data)
        conn.commit()
    conn.close()

def get_all_customers():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM customers", conn)
    conn.close()
    return df

def add_customer(name, device, date, duration):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO customers (name, device_info, reg_date, duration) VALUES (?, ?, ?, ?)", 
              (name, device, date, duration))
    conn.commit()
    conn.close()

def update_customer(id, name, device, date, duration):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE customers SET name=?, device_info=?, reg_date=?, duration=? WHERE id=?", 
              (name, device, date, duration, id))
    conn.commit()
    conn.close()

def delete_customer(id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM customers WHERE id=?", (id,))
    conn.commit()
    conn.close()

# --- 3. LOGIC TÍNH TOÁN ---
def calculate_expiry(start_str, months):
    try:
        start_date = datetime.strptime(start_str, "%d/%m/%Y")
        import calendar
        year = start_date.year
        month = start_date.month + int(months)
        while month > 12:
            month -= 12
            year += 1
        days_in_new_month = calendar.monthrange(year, month)[1]
        day = min(start_date.day, days_in_new_month)
        return datetime(year, month, day)
    except:
        return None

def process_data(df):
    if df.empty: return df, None
    today = datetime.now()
    
    df['obj_expiry'] = df.apply(lambda x: calculate_expiry(x['reg_date'], x['duration']), axis=1)
    df['Ngày Hết Hạn'] = df['obj_expiry'].apply(lambda x: x.strftime("%d/%m/%Y") if x else "Lỗi")
    
    def get_status(x):
        if not x: return "Lỗi ngày"
        days = (x - today).days
        if days < 0: return f"ĐÃ HẾT HẠN ({abs(days)} ngày)"
        if days <= 3: return f"Sắp hết ({days} ngày)"
        return f"Còn {days} ngày"
    
    df['Trạng Thái'] = df['obj_expiry'].apply(get_status)
    df['Gói'] = df['duration'].apply(lambda x: f"{x} tháng")
    
    display_df = df[['id', 'name', 'device_info', 'reg_date', 'Gói', 'Ngày Hết Hạn', 'Trạng Thái']].copy()
    display_df.columns = ["STT", "Tên Khách Hàng", "Thông tin", "Ngày ĐK", "Gói", "Hết Hạn", "Trạng Thái"]
    
    def highlight_rows(row):
        status = row['Trạng Thái']
        if "ĐÃ HẾT HẠN" in status:
            return ['background-color: #fab1a0; color: #c0392b; font-weight: bold'] * len(row)
        elif "Sắp hết" in status:
            return ['background-color: #ffeaa7; color: #d35400; font-weight: bold'] * len(row)
        else:
            return ['background-color: white; color: black'] * len(row)

    styled_df = display_df.style.apply(highlight_rows, axis=1)
    return display_df, styled_df

# --- 4. HÀM HIỂN THỊ CỬA SỔ DOANH THU (ĐƠN GIẢN HÓA) ---
@st.dialog("💰 Báo Cáo Doanh Thu")
def show_revenue_report(df, price):
    if df.empty:
        st.warning("Chưa có dữ liệu.")
        return

    # Tính toán đơn giản: Tổng tháng x Giá
    total_months = df['duration'].sum()
    total_revenue = total_months * price
    
    st.info(f"Đang tính toán dựa trên mức giá: **{price:,.0f} VNĐ / tháng**")

    col1, col2 = st.columns(2)
    col1.metric("📦 Tổng số gói đã bán", f"{total_months} tháng")
    col2.metric("💎 TỔNG DOANH THU", "{:,.0f} VNĐ".format(total_revenue))
    
    st.divider()
    st.caption("Công thức: (Tổng số tháng của tất cả khách hàng) x (Giá 1 tháng)")

# --- 5. SIDEBAR ---
with st.sidebar:
    st.image("https://i.ibb.co/3ymHhQVd/logo.png", width=250)
    st.title("Admin Menu")
    st.info("Hệ thống quản lý v2.1")
    st.markdown("---")
    st.link_button("Donate Ngay ❤️", "https://tsufu.gitbook.io/donate/", type="primary")

# --- 6. GIAO DIỆN CHÍNH ---
init_db()

st.markdown("""<div class="custom-header"><h1>🖊️ HỆ THỐNG QUẢN LÝ GÓI ĐĂNG KÍ</h1></div>""", unsafe_allow_html=True)

tab1, tab2, tab3, tab4 = st.tabs(["📋 DANH SÁCH", "➕ THÊM KHÁCH", "✏️ QUẢN LÝ", "📂 IMPORT/EXPORT"])

# --- TAB 1: DANH SÁCH ---
with tab1:
    col_ctrl1, col_ctrl2, col_ctrl3 = st.columns([1, 2, 1])
    
    with col_ctrl1:
        # Nhập giá để tính toán nhanh
        price_input = st.number_input("Giá 1 tháng (VNĐ):", value=50000, step=10000)
    
    with col_ctrl2:
        st.write("") 
        
    with col_ctrl3:
        st.write("") 
        # Nút xem doanh thu gọn gàng
        if st.button("💎 Xem Tổng Doanh Thu", type="primary", use_container_width=True):
            df_rev = get_all_customers()
            show_revenue_report(df_rev, price_input)

    st.divider()

    col_search, col_ref = st.columns([4, 1])
    with col_search:
        search_q = st.text_input("🔍 Tìm kiếm:", placeholder="Nhập tên khách...")
    with col_ref:
        if st.button("Làm mới"): st.rerun()

    df = get_all_customers()
    if not df.empty:
        if search_q:
            df = df[df['name'].str.contains(search_q, case=False)]
        
        display_df, styled_df = process_data(df)
        
        if styled_df is not None:
            st.dataframe(styled_df, use_container_width=True, hide_index=True, height=500)
    else:
        st.info("Chưa có dữ liệu.")

# --- TAB 2: THÊM MỚI ---
with tab2:
    st.markdown("### Nhập thông tin khách hàng mới")
    with st.form("add_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        new_name = c1.text_input("Tên khách hàng")
        new_device = c2.text_input("Thông tin thiết bị / Note")
        
        c3, c4 = st.columns(2)
        date_pick = c3.date_input("Ngày Đăng Ký", value=datetime.now(), format="DD/MM/YYYY")
        new_duration = c4.number_input("Số tháng thuê", min_value=1, value=1)
        
        if st.form_submit_button("Lưu Khách Hàng", type="primary"):
            if new_name:
                date_str = date_pick.strftime("%d/%m/%Y")
                add_customer(new_name, new_device, date_str, int(new_duration))
                st.success(f"Đã thêm: {new_name}")
                time.sleep(1)
                st.rerun()
            else:
                st.error("Thiếu tên khách hàng!")

# --- TAB 3: SỬA / XÓA ---
with tab3:
    st.markdown("### Chỉnh sửa thông tin")
    df_edit = get_all_customers()
    if not df_edit.empty:
        opts = df_edit.apply(lambda x: f"{x['id']} - {x['name']}", axis=1)
        choice = st.selectbox("Chọn khách hàng:", opts)
        curr_id = int(choice.split(" - ")[0])
        curr_rec = df_edit[df_edit['id'] == curr_id].iloc[0]
        
        col_act1, col_act2 = st.columns(2)
        with col_act1:
            st.info("Sửa thông tin")
            with st.form("edit_form"):
                e_name = st.text_input("Tên", value=curr_rec['name'])
                e_device = st.text_input("Thiết bị", value=curr_rec['device_info'])
                try:
                    default_date = datetime.strptime(curr_rec['reg_date'], "%d/%m/%Y")
                except:
                    default_date = datetime.now()
                
                e_date_pick = st.date_input("Ngày ĐK", value=default_date, format="DD/MM/YYYY")
                e_dur = st.number_input("Tháng", value=int(curr_rec['duration']), min_value=1)
                
                if st.form_submit_button("Cập Nhật"):
                    e_date_str = e_date_pick.strftime("%d/%m/%Y")
                    update_customer(curr_id, e_name, e_device, e_date_str, e_dur)
                    st.success("Đã cập nhật!")
                    time.sleep(0.5)
                    st.rerun()
        
        with col_act2:
            st.error("Vùng nguy hiểm")
            st.write(f"Bạn muốn xóa khách: **{curr_rec['name']}**?")
            if st.button("Xác nhận XÓA Vĩnh Viễn"):
                delete_customer(curr_id)
                st.success("Đã xóa!")
                time.sleep(0.5)
                st.rerun()

# --- TAB 4: IMPORT/EXPORT ---
with tab4:
    st.header("📂 Quản lý File")
    
    col_imp, col_exp = st.columns(2)
    
    # NHẬP FILE
    with col_imp:
        st.subheader("📥 Nhập từ file (CSV/TXT)")
        st.info("File phải có định dạng Header: name, device, date, duration")
        uploaded_file = st.file_uploader("Chọn file", type=['csv', 'txt'])
        
        if uploaded_file is not None:
            try:
                if uploaded_file.name.endswith('.csv'):
                    df_upload = pd.read_csv(uploaded_file)
                else:
                    df_upload = pd.read_csv(uploaded_file, sep=",")
                
                st.write("Xem trước:", df_upload.head())
                
                if st.button("Xác nhận nhập dữ liệu"):
                    count = 0
                    for index, row in df_upload.iterrows():
                        if 'name' in row and 'device' in row:
                            name = row['name']
                            device = row['device']
                            date = row['date'] if 'date' in row else datetime.now().strftime("%d/%m/%Y")
                            duration = row['duration'] if 'duration' in row else 1
                            add_customer(name, device, str(date), int(duration))
                            count += 1
                    st.success(f"Đã nhập {count} dòng!")
                    time.sleep(1)
                    st.rerun()
            except Exception as e:
                st.error(f"Lỗi: {e}")

    # XUẤT FILE
    with col_exp:
        st.subheader("📤 Xuất dữ liệu ra file")
        df_export = get_all_customers()
        if not df_export.empty:
            csv = df_export.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Tải xuống CSV",
                data=csv,
                file_name='danh_sach_khach_hang.csv',
                mime='text/csv',
                type="primary"
            )
        else:
            st.warning("Không có dữ liệu.")

# FOOTER
st.markdown("""
    <div class="footer">
        Dev by Tsufu / Phú Trần Trung Lê | 
        <a href="https://tsufu.gitbook.io/donate/" target="_blank" style="color: #e74c3c; text-decoration: none; font-weight: bold;">Donate Coffee ☕</a>
    </div>
""", unsafe_allow_html=True)