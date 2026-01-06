import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import time
import io
import hashlib
import json
import ast # Thư viện để xử lý text thông minh hơn

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
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER, 
            name TEXT NOT NULL,
            device_info TEXT,
            reg_date TEXT,
            duration INTEGER)''')
    conn.commit()
    conn.close()

# --- XỬ LÝ DỮ LIỆU ---
def get_current_user_id():
    if 'user_id' in st.session_state and st.session_state['user_id']:
        return st.session_state['user_id']
    return None

def get_all_customers():
    user_id = get_current_user_id()
    if user_id:
        conn = sqlite3.connect(DB_FILE)
        df = pd.read_sql_query("SELECT * FROM customers WHERE owner_id=?", conn, params=(user_id,))
        conn.close()
        return df
    else:
        if 'guest_data' not in st.session_state:
            st.session_state.guest_data = pd.DataFrame([
                {"id": 1, "name": "Khách Mẫu (Guest)", "device_info": "Dữ liệu mẫu", "reg_date": datetime.now().strftime("%d/%m/%Y"), "duration": 1}
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
        new_row = {"id": int(time.time()), "name": name, "device_info": device, "reg_date": date, "duration": duration}
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

# --- LOGIC TÍNH TOÁN & IMPORT ---
def parse_date(date_str):
    for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%y"]:
        try:
            return datetime.strptime(str(date_str).strip(), fmt)
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
    
    # [FIX] Đảm bảo kiểu dữ liệu an toàn trước khi xử lý
    df['duration'] = pd.to_numeric(df['duration'], errors='coerce').fillna(1).astype(int)
    
    # Tính ngày hết hạn (Object datetime)
    df['obj_expiry'] = df.apply(lambda x: calculate_expiry(x['reg_date'], x['duration']), axis=1)
    
    # [FIX QUAN TRỌNG] Kiểm tra pd.isnull(x) để tránh lỗi NaT (Not a Time)
    df['Ngày Hết Hạn'] = df['obj_expiry'].apply(
        lambda x: x.strftime("%d/%m/%Y") if (x is not None and not pd.isnull(x)) else "Lỗi/Sai Ngày"
    )
    
    def get_status(x):
        if x is None or pd.isnull(x): return "Kiểm tra lại"
        days = (x - today).days
        if days < 0: return f"ĐÃ HẾT HẠN ({abs(days)} ngày)"
        if days <= 3: return f"Sắp hết ({days} ngày)"
        return f"Còn {days} ngày"
    
    df['Trạng Thái'] = df['obj_expiry'].apply(get_status)
    df['Gói'] = df['duration'].apply(lambda x: f"{x} tháng")
    
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
    df_raw.columns = [str(c).lower().strip() for c in df_raw.columns]
    col_map = {'name': '', 'device': '', 'date': '', 'duration': ''}
    
    for col in df_raw.columns:
        if any(x in col for x in ['ten', 'name', 'khach', 'user']): col_map['name'] = col
        elif any(x in col for x in ['thiet', 'device', 'may', 'note', 'thông tin']): col_map['device'] = col
        elif any(x in col for x in ['ngay', 'date', 'time', 'dang ki', 'reg']): col_map['date'] = col
        elif any(x in col for x in ['thang', 'duration', 'goi', 'han']): col_map['duration'] = col
    
    df_clean = pd.DataFrame()
    df_clean['name'] = df_raw[col_map['name']] if col_map['name'] else "Khách Nhập File"
    df_clean['device_info'] = df_raw[col_map['device']] if col_map['device'] else "Không rõ"
    
    if col_map['date']: 
        df_clean['reg_date'] = df_raw[col_map['date']].fillna(datetime.now().strftime("%d/%m/%Y"))
    else: 
        df_clean['reg_date'] = datetime.now().strftime("%d/%m/%Y")
        
    if col_map['duration']: 
        df_clean['duration'] = pd.to_numeric(df_raw[col_map['duration']], errors='coerce').fillna(1).astype(int)
    else: 
        df_clean['duration'] = 1
        
    return df_clean

@st.dialog("📊 Báo Cáo Doanh Thu Theo Tháng")
def show_monthly_revenue(df, price):
    if df.empty:
        st.warning("Chưa có dữ liệu.")
        return
    
    df_rev = df.copy()
    # Chuyển đổi duration sang số
    df_rev['duration'] = pd.to_numeric(df_rev['duration'], errors='coerce').fillna(0)

    def get_month_year(date_str):
        dt = parse_date(date_str)
        if dt: return dt.strftime("%Y-%m")
        return "Không xác định"
    
    def get_display_month(date_str):
        dt = parse_date(date_str)
        if dt: return dt.strftime("%m/%Y")
        return "Không xác định"

    df_rev['YYYY_MM'] = df_rev['reg_date'].apply(get_month_year)
    df_rev['Revenue'] = df_rev['duration'] * price
    df_rev = df_rev[df_rev['YYYY_MM'] != "Không xác định"]
    
    monthly_stats = df_rev.groupby('YYYY_MM')['Revenue'].sum().reset_index()
    monthly_count = df_rev.groupby('YYYY_MM')['id'].count().reset_index()
    
    final_stats = pd.merge(monthly_stats, monthly_count, on='YYYY_MM')
    final_stats.columns = ['YYYY_MM', 'Doanh Thu', 'Số Khách']
    final_stats['Tháng'] = final_stats['YYYY_MM'].apply(lambda x: datetime.strptime(x, "%Y-%m").strftime("%m/%Y"))
    final_stats = final_stats.sort_values('YYYY_MM')

    total_rev_all = final_stats['Doanh Thu'].sum()
    st.metric("💎 TỔNG DOANH THU TOÀN THỜI GIAN", "{:,.0f} VNĐ".format(total_rev_all))
    st.divider()
    
    st.subheader("Biểu đồ doanh thu")
    st.bar_chart(final_stats, x="Tháng", y="Doanh Thu", color="#2ecc71")
    
    st.subheader("Chi tiết từng tháng")
    st.dataframe(final_stats[['Tháng', 'Số Khách', 'Doanh Thu']], hide_index=True)

# --- 4. GIAO DIỆN CHÍNH ---
init_db()

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
        st.warning("⚠️ Đang dùng chế độ KHÁCH. Dữ liệu sẽ mất khi tải lại trang.")
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
                        time.sleep(0.5); st.rerun()
                    else: st.error("Sai thông tin")
            with tab_signup:
                s_user = st.text_input("User mới", key="s_u")
                s_pass = st.text_input("Pass mới", type="password", key="s_p")
                if st.button("Tạo tài khoản"):
                    if create_user(s_user, s_pass): st.success("Tạo xong! Hãy đăng nhập.")
                    else: st.error("Tên đã tồn tại")
    st.markdown("---")
    st.link_button("Donate Ngay ❤️", "https://tsufu.gitbook.io/donate/", type="primary")

st.markdown("""<div class="custom-header"><h1>🖊️ HỆ THỐNG QUẢN LÝ GÓI ĐĂNG KÍ</h1></div>""", unsafe_allow_html=True)

tab1, tab2, tab3, tab4 = st.tabs(["📋 DANH SÁCH", "➕ THÊM KHÁCH", "✏️ QUẢN LÝ", "📂 NHẬP/XUẤT"])

# TAB 1: DANH SÁCH
with tab1:
    c1, c2, c3 = st.columns([1, 2, 1])
    with c1: price_input = st.number_input("Giá 1 tháng (VNĐ):", value=50000, step=10000)
    with c3:
        st.write("")
        if st.button("💎 Xem Báo Cáo Doanh Thu", type="primary", use_container_width=True):
            df_rev = get_all_customers()
            show_monthly_revenue(df_rev, price_input)
    st.divider()
    c_s, c_r = st.columns([4, 1])
    with c_s: search_q = st.text_input("🔍 Tìm kiếm:", placeholder="Nhập tên khách...")
    with c_r: 
        if st.button("Làm mới"): st.rerun()

    df = get_all_customers()
    if not df.empty:
        if search_q: df = df[df['name'].str.contains(search_q, case=False)]
        display_df, styled_df = process_data(df)
        if styled_df is not None:
            st.dataframe(styled_df, use_container_width=True, hide_index=True, height=500)
    else: st.info("Chưa có dữ liệu.")

# TAB 2: THÊM MỚI
with tab2:
    with st.form("add"):
        c1, c2 = st.columns(2)
        nn = c1.text_input("Tên khách"); nd = c2.text_input("Thông tin khách hàng")
        c3, c4 = st.columns(2)
        dp = c3.date_input("Ngày ĐK", datetime.now(), format="DD/MM/YYYY")
        dur = c4.number_input("Tháng", 1, min_value=1)
        if st.form_submit_button("Lưu", type="primary"):
            if nn:
                add_customer(nn, nd, dp.strftime("%d/%m/%Y"), int(dur))
                st.success(f"Đã thêm {nn}"); time.sleep(0.5); st.rerun()
            else: st.error("Thiếu tên")

# TAB 3: QUẢN LÝ
with tab3:
    df_edit = get_all_customers()
    if not df_edit.empty:
        opts = df_edit.apply(lambda x: f"{x['id']} - {x['name']}", axis=1)
        choice = st.selectbox("Chọn khách:", opts)
        cid = int(choice.split(" - ")[0])
        crec = df_edit[df_edit['id'] == cid].iloc[0]
        c1, c2 = st.columns(2)
        with c1:
            with st.form("edit"):
                en = st.text_input("Tên", crec['name'])
                ed = st.text_input("Thông tin", crec['device_info'])
                dt_val = parse_date(crec['reg_date']) or datetime.now()
                edp = st.date_input("Ngày", dt_val, format="DD/MM/YYYY")
                edu = st.number_input("Tháng", int(crec['duration']), min_value=1)
                if st.form_submit_button("Cập nhật"):
                    update_customer(cid, en, ed, edp.strftime("%d/%m/%Y"), edu)
                    st.success("Xong!"); time.sleep(0.5); st.rerun()
        with c2:
            st.error("Nguy hiểm"); 
            if st.button("Xóa khách này"): 
                delete_customer(cid); st.success("Đã xóa"); time.sleep(0.5); st.rerun()

# TAB 4: NHẬP / XUẤT (CÓ FORM)
with tab4:
    c_imp, c_exp = st.columns(2)
    with c_imp:
        st.subheader("📥 Nhập Dữ Liệu")
        t_file, t_text = st.tabs(["Tải File", "Dán Text (JSON/CSV)"])
        
        df_up = pd.DataFrame()
        with t_file:
            uf = st.file_uploader("Chọn file", type=['csv','txt','json'])
            if uf:
                try:
                    if uf.name.endswith('.json'): df_up = pd.read_json(uf)
                    else: df_up = pd.read_csv(uf, sep=None, engine='python')
                except: st.error("Lỗi file")

        # [FIX] Dùng Form để nút bấm hoạt động ngay lập tức
        with t_text:
            with st.form("paste_form"):
                txt = st.text_area("Dán dữ liệu JSON hoặc CSV vào đây", height=200)
                sub_paste = st.form_submit_button("Xử lý dữ liệu dán")
                if sub_paste and txt:
                    try:
                        # Logic 1: Parse JSON text
                        clean_txt = txt.strip()
                        if clean_txt.startswith("[") or clean_txt.startswith("{"):
                            try:
                                js = json.loads(clean_txt)
                                df_up = pd.DataFrame(js)
                            except: 
                                # Fallback nếu JSON lỗi cú pháp nhẹ (dùng ast)
                                try:
                                    js = ast.literal_eval(clean_txt)
                                    df_up = pd.DataFrame(js)
                                except: pass
                        
                        # Logic 2: Nếu không ra DF, thử parse CSV
                        if df_up.empty:
                            df_up = pd.read_csv(io.StringIO(clean_txt), sep=None, engine='python', header=None)
                            # Check nếu dòng 1 toàn string thì coi là header
                            if df_up.iloc[0].apply(lambda x: isinstance(x, str)).all():
                                df_up = pd.read_csv(io.StringIO(clean_txt), sep=None, engine='python')
                    except Exception as e:
                        st.error(f"Không hiểu định dạng: {e}")

        # Xử lý sau khi có Dataframe
        if not df_up.empty:
            st.write("Dữ liệu nhận diện:", df_up.head(3))
            if st.button("🚀 Xác nhận nhập vào hệ thống"):
                df_clean = smart_import(df_up)
                cnt = 0
                for _, r in df_clean.iterrows():
                    add_customer(r['name'], r['device_info'], r['reg_date'], r['duration'])
                    cnt += 1
                st.success(f"Đã nhập {cnt} dòng!"); time.sleep(1); st.rerun()

    with c_exp:
        st.subheader("📤 Xuất Dữ Liệu")
        dfe = get_all_customers()
        if not dfe.empty:
            st.download_button("Tải CSV", dfe.to_csv(index=False).encode('utf-8'), "data.csv", "text/csv")
            st.download_button("Tải JSON", dfe.to_json(orient="records", force_ascii=False).encode('utf-8'), "data.json", "application/json")
        else: st.warning("Trống")

st.markdown("""<div class="footer">Dev by Tsufu / Phú Trần Trung Lê | <a href="https://tsufu.gitbook.io/donate/" target="_blank">Donate Coffee ☕</a></div>""", unsafe_allow_html=True)