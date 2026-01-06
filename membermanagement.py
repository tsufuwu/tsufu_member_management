import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import time
import io
import hashlib
import json

# --- 1. CẤU HÌNH & CSS ---
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
    /* Tab container styles */
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; background-color: white; border-radius: 5px 5px 0 0; gap: 1px; padding-top: 10px; padding-bottom: 10px; }
    .stTabs [aria-selected="true"] { background-color: #e8f4f9; color: #2c3e50; font-weight: bold;}
</style>
""", unsafe_allow_html=True)

# --- 2. HỆ THỐNG DATABASE & AUTH ---
DB_FILE = "dulieu_game_v2.db"

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    if make_hashes(password) == hashed_text:
        return hashed_text
    return False

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Bảng user
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
                )''')

    # Bảng khách hàng (Có thêm owner_id)
    c.execute('''CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER, 
            name TEXT NOT NULL,
            device_info TEXT,
            reg_date TEXT,
            duration INTEGER)''')
    conn.commit()
    conn.close()

# --- XỬ LÝ DỮ LIỆU (TÁCH BIỆT USER VÀ GUEST) ---

def get_current_user_id():
    """Lấy ID user hiện tại, trả về None nếu là Guest"""
    if 'user_id' in st.session_state and st.session_state['user_id']:
        return st.session_state['user_id']
    return None # Guest mode

def get_all_customers():
    user_id = get_current_user_id()
    if user_id:
        # Lấy từ DB nếu đã đăng nhập
        conn = sqlite3.connect(DB_FILE)
        df = pd.read_sql_query("SELECT * FROM customers WHERE owner_id=?", conn, params=(user_id,))
        conn.close()
        return df
    else:
        # Guest mode: Lấy từ Session State (Bộ nhớ tạm)
        if 'guest_data' not in st.session_state:
            # Tạo dữ liệu mẫu cho Guest
            st.session_state.guest_data = pd.DataFrame([
                {"id": 1, "name": "Khách Mẫu (Guest)", "device_info": "Chưa đăng nhập", "reg_date": datetime.now().strftime("%d/%m/%Y"), "duration": 1}
            ])
        return st.session_state.guest_data

def add_customer(name, device, date, duration):
    user_id = get_current_user_id()
    if user_id:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO customers (owner_id, name, device_info, reg_date, duration) VALUES (?, ?, ?, ?, ?)", 
                  (user_id, name, device, date, duration))
        conn.commit()
        conn.close()
    else:
        # Guest: Thêm vào dataframe tạm
        new_row = {"id": len(st.session_state.guest_data) + 1, "name": name, "device_info": device, "reg_date": date, "duration": duration}
        st.session_state.guest_data = pd.concat([st.session_state.guest_data, pd.DataFrame([new_row])], ignore_index=True)

def update_customer(id, name, device, date, duration):
    user_id = get_current_user_id()
    if user_id:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE customers SET name=?, device_info=?, reg_date=?, duration=? WHERE id=? AND owner_id=?", 
                  (name, device, date, duration, id, user_id))
        conn.commit()
        conn.close()
    else:
        # Guest update
        df = st.session_state.guest_data
        idx = df.index[df['id'] == id].tolist()
        if idx:
            df.at[idx[0], 'name'] = name
            df.at[idx[0], 'device_info'] = device
            df.at[idx[0], 'reg_date'] = date
            df.at[idx[0], 'duration'] = duration
            st.session_state.guest_data = df

def delete_customer(id):
    user_id = get_current_user_id()
    if user_id:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("DELETE FROM customers WHERE id=? AND owner_id=?", (id, user_id))
        conn.commit()
        conn.close()
    else:
        # Guest delete
        df = st.session_state.guest_data
        st.session_state.guest_data = df[df['id'] != id].reset_index(drop=True)

# --- AUTH FUNCTIONS ---
def create_user(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, make_hashes(password)))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def login_user(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, make_hashes(password)))
    data = c.fetchall()
    conn.close()
    return data

# --- LOGIC TÍNH TOÁN & IMPORT THÔNG MINH ---
def parse_date(date_str):
    """Hàm phụ trợ parse ngày tháng từ nhiều định dạng"""
    for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%y"]:
        try:
            return datetime.strptime(str(date_str), fmt)
        except: continue
    return None

def calculate_expiry(start_str, months):
    start_date = parse_date(start_str)
    if not start_date: return None

    try:
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
    df['Ngày Hết Hạn'] = df['obj_expiry'].apply(lambda x: x.strftime("%d/%m/%Y") if x else "Lỗi/Sai Ngày")
    
    def get_status(x):
        if not x: return "Kiểm tra lại"
        days = (x - today).days
        if days < 0: return f"ĐÃ HẾT HẠN ({abs(days)} ngày)"
        if days <= 3: return f"Sắp hết ({days} ngày)"
        return f"Còn {days} ngày"
    
    df['Trạng Thái'] = df['obj_expiry'].apply(get_status)
    df['Gói'] = df['duration'].apply(lambda x: f"{x} tháng")
    
    # Rename columns for display
    display_df = df[['id', 'name', 'device_info', 'reg_date', 'Gói', 'Ngày Hết Hạn', 'Trạng Thái']].copy()
    display_df.columns = ["STT", "Tên Khách Hàng", "Thông tin khách hàng", "Ngày ĐK", "Gói", "Hết Hạn", "Trạng Thái"]
    
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

def smart_import(df_raw):
    """Hàm thông minh tự nhận diện cột và điền thiếu"""
    # 1. Chuẩn hóa tên cột (về chữ thường, bỏ dấu)
    df_raw.columns = [str(c).lower().strip() for c in df_raw.columns]
    
    # 2. Map cột thông minh
    col_map = {
        'name': '', 'device': '', 'date': '', 'duration': ''
    }
    
    for col in df_raw.columns:
        if any(x in col for x in ['ten', 'name', 'khach', 'user']): col_map['name'] = col
        elif any(x in col for x in ['thiet', 'device', 'may', 'note', 'ghi', 'thông tin']): col_map['device'] = col
        elif any(x in col for x in ['ngay', 'date', 'time', 'dang ki', 'reg']): col_map['date'] = col
        elif any(x in col for x in ['thang', 'duration', 'goi', 'han']): col_map['duration'] = col
    
    # 3. Tạo DataFrame chuẩn
    df_clean = pd.DataFrame()
    
    # Xử lý Tên
    if col_map['name']: df_clean['name'] = df_raw[col_map['name']]
    else: df_clean['name'] = "Khách Nhập File"
    
    # Xử lý Thiết bị
    if col_map['device']: df_clean['device_info'] = df_raw[col_map['device']]
    else: df_clean['device_info'] = "Không rõ thông tin"
    
    # Xử lý Ngày (Miễn cưỡng: Nếu thiếu hoặc lỗi -> Lấy ngày nay)
    if col_map['date']: 
        df_clean['reg_date'] = df_raw[col_map['date']].fillna(datetime.now().strftime("%d/%m/%Y"))
    else: 
        df_clean['reg_date'] = datetime.now().strftime("%d/%m/%Y")
        
    # Xử lý Gói (Miễn cưỡng: Nếu thiếu -> 1 tháng)
    if col_map['duration']: 
        df_clean['duration'] = pd.to_numeric(df_raw[col_map['duration']], errors='coerce').fillna(1).astype(int)
    else: 
        df_clean['duration'] = 1
        
    return df_clean

# --- HÀM BÁO CÁO DOANH THU THEO THÁNG ---
@st.dialog("📊 Báo Cáo Doanh Thu Theo Tháng")
def show_monthly_revenue(df, price):
    if df.empty:
        st.warning("Chưa có dữ liệu.")
        return

    # 1. Xử lý dữ liệu để nhóm theo tháng
    df_rev = df.copy()
    
    # Hàm lấy Tháng/Năm từ chuỗi ngày (Sortable YYYY-MM)
    def get_month_year(date_str):
        dt = parse_date(date_str)
        if dt:
            return dt.strftime("%Y-%m") # Trả về dạng 2025-12 để sort cho đúng
        return "Không xác định"
    
    # Hàm hiển thị Tháng/Năm đẹp (MM/YYYY)
    def get_display_month(date_str):
        dt = parse_date(date_str)
        if dt:
            return dt.strftime("%m/%Y")
        return "Không xác định"

    df_rev['YYYY_MM'] = df_rev['reg_date'].apply(get_month_year)
    df_rev['Display_Month'] = df_rev['reg_date'].apply(get_display_month)
    
    # Tính tiền từng đơn: Số tháng * Giá
    df_rev['Revenue'] = df_rev['duration'] * price

    # 2. Group by Tháng
    # Bỏ qua những ngày lỗi
    df_rev = df_rev[df_rev['YYYY_MM'] != "Không xác định"]
    
    monthly_stats = df_rev.groupby('YYYY_MM')['Revenue'].sum().reset_index()
    monthly_count = df_rev.groupby('YYYY_MM')['id'].count().reset_index()
    
    # Merge lại để có cả số tiền và số khách
    final_stats = pd.merge(monthly_stats, monthly_count, on='YYYY_MM')
    final_stats.columns = ['YYYY_MM', 'Doanh Thu', 'Số Khách']
    
    # Tạo cột hiển thị đẹp từ cột YYYY_MM
    final_stats['Tháng'] = final_stats['YYYY_MM'].apply(lambda x: datetime.strptime(x, "%Y-%m").strftime("%m/%Y"))
    final_stats = final_stats.sort_values('YYYY_MM') # Sắp xếp theo thời gian

    # 3. Hiển thị
    total_rev_all = final_stats['Doanh Thu'].sum()
    st.metric("💎 TỔNG DOANH THU TOÀN THỜI GIAN", "{:,.0f} VNĐ".format(total_rev_all))
    st.divider()
    
    # Biểu đồ
    st.subheader("Biểu đồ doanh thu")
    st.bar_chart(final_stats, x="Tháng", y="Doanh Thu", color="#2ecc71")
    
    # Bảng chi tiết
    st.subheader("Chi tiết từng tháng")
    st.dataframe(
        final_stats[['Tháng', 'Số Khách', 'Doanh Thu']],
        column_config={
            "Doanh Thu": st.column_config.NumberColumn(format="%d VNĐ"),
        },
        use_container_width=True,
        hide_index=True
    )

# --- 4. GIAO DIỆN CHÍNH ---
init_db()

# Sidebar Login/Logout
with st.sidebar:
    st.image("https://i.ibb.co/3ymHhQVd/logo.png", width=250)
    
    if 'username' not in st.session_state: st.session_state.username = None

    if st.session_state.username:
        st.success(f"Xin chào, {st.session_state.username}!")
        if st.button("Đăng xuất"):
            st.session_state.username = None
            st.session_state.user_id = None
            st.rerun()
    else:
        st.warning("⚠️ Đang dùng chế độ KHÁCH (Dữ liệu sẽ mất khi tải lại trang), hãy đăng kí/ đăng nhập tài khoản để lưu.")
        with st.expander("🔐 Đăng nhập / Đăng ký"):
            tab_login, tab_signup = st.tabs(["Đăng nhập", "Đăng ký"])
            with tab_login:
                l_user = st.text_input("Username", key="l_u")
                l_pass = st.text_input("Password", type="password", key="l_p")
                if st.button("Login"):
                    user_res = login_user(l_user, l_pass)
                    if user_res:
                        st.session_state.user_id = user_res[0][0]
                        st.session_state.username = l_user
                        st.success("Thành công!")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("Sai tài khoản/mật khẩu")
            with tab_signup:
                s_user = st.text_input("Username mới", key="s_u")
                s_pass = st.text_input("Password mới", type="password", key="s_p")
                if st.button("Tạo tài khoản"):
                    if create_user(s_user, s_pass):
                        st.success("Tạo thành công! Hãy đăng nhập.")
                    else:
                        st.error("Tên đăng nhập đã tồn tại.")

    st.markdown("---")
    st.link_button("Donate Ngay ❤️", "https://tsufu.gitbook.io/donate/", type="primary")

# Header
st.markdown("""<div class="custom-header"><h1>🖊️ HỆ THỐNG QUẢN LÝ GÓI ĐĂNG KÍ</h1></div>""", unsafe_allow_html=True)

# Main Tabs
tab1, tab2, tab3, tab4 = st.tabs(["📋 DANH SÁCH", "➕ THÊM KHÁCH", "✏️ QUẢN LÝ", "📂 NHẬP/XUẤT"])

# --- TAB 1: DANH SÁCH ---
with tab1:
    col_ctrl1, col_ctrl2, col_ctrl3 = st.columns([1, 2, 1])
    with col_ctrl1:
        price_input = st.number_input("Giá 1 tháng (VNĐ):", value=50000, step=10000)
    with col_ctrl3:
        st.write("") 
        if st.button("💎 Xem Báo Cáo Doanh Thu", type="primary", use_container_width=True):
            df_rev = get_all_customers()
            show_monthly_revenue(df_rev, price_input)

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
        st.info("Chưa có dữ liệu. Hãy thêm khách mới.")

# --- TAB 2: THÊM MỚI ---
with tab2:
    with st.form("add_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        new_name = c1.text_input("Tên khách hàng")
        new_device = c2.text_input("Thông tin khách hàng") 
        c3, c4 = st.columns(2)
        date_pick = c3.date_input("Ngày Đăng Ký", value=datetime.now(), format="DD/MM/YYYY")
        new_duration = c4.number_input("Số tháng thuê", min_value=1, value=1)
        
        if st.form_submit_button("Lưu Khách Hàng", type="primary"):
            if new_name:
                date_str = date_pick.strftime("%d/%m/%Y")
                add_customer(new_name, new_device, date_str, int(new_duration))
                st.success(f"Đã thêm: {new_name}")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("Thiếu tên khách hàng!")

# --- TAB 3: QUẢN LÝ ---
with tab3:
    df_edit = get_all_customers()
    if not df_edit.empty:
        opts = df_edit.apply(lambda x: f"{x['id']} - {x['name']}", axis=1)
        choice = st.selectbox("Chọn khách hàng:", opts)
        curr_id = int(choice.split(" - ")[0])
        curr_rec = df_edit[df_edit['id'] == curr_id].iloc[0]
        
        c1, c2 = st.columns(2)
        with c1:
            with st.form("edit_form"):
                e_name = st.text_input("Tên", value=curr_rec['name'])
                e_device = st.text_input("Thông tin khách hàng", value=curr_rec['device_info'])
                # Parse date safe
                try: 
                    e_date_val = parse_date(curr_rec['reg_date'])
                    if not e_date_val: e_date_val = datetime.now()
                except: e_date_val = datetime.now()
                
                e_date_pick = st.date_input("Ngày ĐK", value=e_date_val, format="DD/MM/YYYY")
                e_dur = st.number_input("Tháng", value=int(curr_rec['duration']), min_value=1)
                
                if st.form_submit_button("Cập Nhật"):
                    update_customer(curr_id, e_name, e_device, e_date_pick.strftime("%d/%m/%Y"), e_dur)
                    st.success("Đã lưu!")
                    time.sleep(0.5); st.rerun()
        with c2:
            st.error("Xóa dữ liệu")
            if st.button("Xóa Khách Này"):
                delete_customer(curr_id)
                st.success("Đã xóa!"); time.sleep(0.5); st.rerun()

# --- TAB 4: NHẬP/XUẤT ---
with tab4:
    col_imp, col_exp = st.columns(2)
    
    # NHẬP
    with col_imp:
        st.subheader("📥 Nhập Dữ Liệu")
        st.caption("Hỗ trợ: CSV, JSON, hoặc Paste văn bản JSON/CSV.")
        
        tab_file, tab_paste = st.tabs(["Tải File", "Nhập Tay (Copy/Paste)"])
        
        df_upload = pd.DataFrame()
        
        with tab_file:
            uploaded_file = st.file_uploader("Chọn file", type=['csv', 'txt', 'json'])
            if uploaded_file:
                try:
                    if uploaded_file.name.endswith('.csv') or uploaded_file.name.endswith('.txt'):
                        df_upload = pd.read_csv(uploaded_file, sep=None, engine='python')
                    elif uploaded_file.name.endswith('.json'):
                        df_upload = pd.read_json(uploaded_file)
                except Exception as e: st.error(f"Lỗi đọc file: {e}")

        with tab_paste:
            paste_txt = st.text_area("Dán dữ liệu JSON hoặc CSV vào đây", height=200, help="Dán danh sách JSON như ví dụ của bạn vào đây")
            if paste_txt:
                try:
                    # Logic 1: Thử đọc JSON trước (vì bạn yêu cầu hỗ trợ đoạn text JSON)
                    if paste_txt.strip().startswith("[") or paste_txt.strip().startswith("{"):
                        js_data = json.loads(paste_txt)
                        df_upload = pd.DataFrame(js_data)
                    else:
                    # Logic 2: Nếu không phải JSON, thử đọc CSV
                        df_upload = pd.read_csv(io.StringIO(paste_txt), sep=None, engine='python', header=None)
                        if df_upload.iloc[0].apply(lambda x: isinstance(x, str)).all():
                            df_upload = pd.read_csv(io.StringIO(paste_txt), sep=None, engine='python')
                except: pass

        if not df_upload.empty:
            st.write("Dữ liệu tìm thấy:", df_upload.head(3))
            if st.button("🚀 Xử lý & Nhập vào hệ thống"):
                # GỌI HÀM IMPORT THÔNG MINH
                df_clean = smart_import(df_upload)
                
                count = 0
                for _, row in df_clean.iterrows():
                    add_customer(row['name'], row['device_info'], row['reg_date'], row['duration'])
                    count += 1
                st.success(f"Đã nhập thành công {count} khách hàng!")
                time.sleep(1.5)
                st.rerun()
        elif paste_txt:
            st.error("Không thể nhận diện định dạng dữ liệu. Hãy đảm bảo đúng format JSON hoặc CSV.")

    # XUẤT
    with col_exp:
        st.subheader("📤 Xuất Dữ Liệu")
        df_export = get_all_customers()
        if not df_export.empty:
            # CSV
            csv = df_export.to_csv(index=False).encode('utf-8')
            st.download_button("Tải CSV (Excel)", csv, "data.csv", "text/csv")
            
            # JSON
            json_str = df_export.to_json(orient="records", force_ascii=False).encode('utf-8')
            st.download_button("Tải JSON", json_str, "data.json", "application/json")
        else:
            st.warning("Chưa có dữ liệu để xuất.")

# Footer
st.markdown("""<div class="footer">Dev by Tsufu / Phú Trần Trung Lê | <a href="https://tsufu.gitbook.io/donate/" target="_blank">Donate Coffee ☕</a></div>""", unsafe_allow_html=True)