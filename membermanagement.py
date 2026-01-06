import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import time
import io
import hashlib
import json
import ast

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

# Các hàm thao tác DB (Add/Update/Delete)
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

def update_customer_db(id, name, device, date, duration):
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

def delete_customer_db(id):
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

# --- CALLBACK SỬA TRỰC TIẾP (TAB 1) ---
def save_editor_changes():
    changes = st.session_state.editor_changes
    if 'current_view_df' not in st.session_state: return
    df_view = st.session_state.current_view_df

    # Sửa
    for row_idx, edits in changes['edited_rows'].items():
        try:
            record_id = df_view.iloc[row_idx]['id']
            record = df_view.iloc[row_idx].to_dict()
            
            new_name = edits.get("Tên Khách Hàng", record['name'])
            new_device = edits.get("Thông tin khách hàng", record['device_info'])
            new_dur = edits.get("Gói (tháng)", record['duration'])
            
            new_date_val = edits.get("Ngày ĐK", record['reg_date_obj'])
            new_date_str = new_date_val.strftime("%d/%m/%Y") if isinstance(new_date_val, datetime) else str(new_date_val)

            update_customer_db(record_id, new_name, new_device, new_date_str, int(new_dur))
        except: pass

    # Xóa (Bằng nút Delete của bảng)
    for row_idx in changes['deleted_rows']:
        try:
            record_id = df_view.iloc[row_idx]['id']
            delete_customer_db(record_id)
        except: pass

    # Thêm Mới (Bằng dòng cuối cùng của bảng)
    for new_row in changes['added_rows']:
        try:
            n_name = new_row.get("Tên Khách Hàng", "Khách Mới")
            n_dev = new_row.get("Thông tin khách hàng", "")
            n_dur = new_row.get("Gói (tháng)", 1)
            n_date_str = datetime.now().strftime("%d/%m/%Y") 
            if "Ngày ĐK" in new_row:
                 try: n_date_str = datetime.strptime(str(new_row["Ngày ĐK"]), "%Y-%m-%d").strftime("%d/%m/%Y")
                 except: pass
            add_customer(n_name, n_dev, n_date_str, int(n_dur))
        except: pass

# --- UTILS & AUTH ---
def create_user(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, make_hashes(password)))
        conn.commit(); conn.close(); return True
    except: conn.close(); return False

def login_user(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, make_hashes(password)))
    data = c.fetchall(); conn.close(); return data

def parse_date(date_str):
    for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%y"]:
        try: return datetime.strptime(str(date_str).strip(), fmt)
        except: continue
    return None

def calculate_expiry(start_date, months):
    if not start_date: return None
    try:
        import calendar
        year = start_date.year
        month = start_date.month + int(months)
        while month > 12: month -= 12; year += 1
        day = min(start_date.day, calendar.monthrange(year, month)[1])
        return datetime(year, month, day)
    except: return None

def process_data_for_editor(df):
    if df.empty: return df
    df['reg_date_obj'] = df['reg_date'].apply(lambda x: parse_date(x))
    df['duration'] = pd.to_numeric(df['duration'], errors='coerce').fillna(1).astype(int)

    today = datetime.now()
    def get_status_expiry(row):
        exp = calculate_expiry(row['reg_date_obj'], row['duration'])
        if not exp: return "Lỗi", "⚪ Lỗi"
        days = (exp - today).days
        exp_str = exp.strftime("%d/%m/%Y")
        if days < 0: return exp_str, f"🔴 ĐÃ HẾT ({abs(days)}d)"
        if days <= 3: return exp_str, f"🟡 Sắp hết ({days}d)"
        return exp_str, f"🟢 Còn {days} ngày"

    df[['Hết Hạn', 'Trạng Thái']] = df.apply(lambda x: pd.Series(get_status_expiry(x)), axis=1)
    
    df_display = df.rename(columns={
        "name": "Tên Khách Hàng",
        "device_info": "Thông tin khách hàng",
        "reg_date_obj": "Ngày ĐK",
        "duration": "Gói (tháng)"
    })
    return df_display

def smart_import(df_raw):
    df_raw.columns = [str(c).lower().strip() for c in df_raw.columns]
    col_map = {'name': '', 'device': '', 'date': '', 'duration': ''}
    for col in df_raw.columns:
        if any(x in col for x in ['ten', 'name', 'khach']): col_map['name'] = col
        elif any(x in col for x in ['thiet', 'device', 'thông tin']): col_map['device'] = col
        elif any(x in col for x in ['ngay', 'date']): col_map['date'] = col
        elif any(x in col for x in ['thang', 'duration']): col_map['duration'] = col
    
    df_clean = pd.DataFrame()
    df_clean['name'] = df_raw[col_map['name']] if col_map['name'] else "Khách Nhập"
    df_clean['device_info'] = df_raw[col_map['device']] if col_map['device'] else ""
    if col_map['date']: 
        df_clean['reg_date'] = df_raw[col_map['date']].fillna(datetime.now().strftime("%d/%m/%Y"))
    else: df_clean['reg_date'] = datetime.now().strftime("%d/%m/%Y")
    df_clean['duration'] = pd.to_numeric(df_raw[col_map['duration']], errors='coerce').fillna(1).astype(int) if col_map['duration'] else 1
    return df_clean

@st.dialog("➕ Thêm Khách Hàng Nhanh")
def show_add_modal():
    with st.form("quick_add"):
        n = st.text_input("Tên khách hàng")
        d = st.text_input("Thông tin khách hàng")
        dt = st.date_input("Ngày Đăng Ký", datetime.now(), format="DD/MM/YYYY")
        dur = st.number_input("Thời hạn (tháng)", min_value=1, value=1)
        if st.form_submit_button("Lưu ngay", type="primary"):
            if n:
                add_customer(n, d, dt.strftime("%d/%m/%Y"), int(dur))
                st.success("Đã thêm thành công!"); time.sleep(0.5); st.rerun()
            else: st.error("Vui lòng nhập tên")

@st.dialog("📊 Báo Cáo Doanh Thu")
def show_monthly_revenue(df, price):
    if df.empty: st.warning("Chưa có dữ liệu."); return
    df = df.copy()
    df['duration'] = pd.to_numeric(df['duration'], errors='coerce').fillna(0)
    def get_ym(d): 
        dt = parse_date(d)
        return dt.strftime("%Y-%m") if dt else "N/A"
    
    df['YYYY_MM'] = df['reg_date'].apply(get_ym)
    df = df[df['YYYY_MM'] != "N/A"]
    df['Rev'] = df['duration'] * price
    
    stats = df.groupby('YYYY_MM')['Rev'].sum().reset_index()
    stats['Tháng'] = stats['YYYY_MM']
    st.metric("TỔNG DOANH THU", "{:,.0f} VNĐ".format(stats['Rev'].sum()))
    st.bar_chart(stats, x="Tháng", y="Rev", color="#2ecc71")
    st.dataframe(stats, hide_index=True)

# --- 4. GIAO DIỆN CHÍNH ---
init_db()

with st.sidebar:
    st.image("https://i.ibb.co/3ymHhQVd/logo.png", width=250)
    
    # --- PHỤC HỒI GIAO DIỆN AUTH TIẾNG VIỆT ---
    if 'username' not in st.session_state: st.session_state.username = None

    if st.session_state.username:
        st.success(f"Xin chào, {st.session_state.username}!")
        if st.button("Đăng xuất"):
            st.session_state.username = None; st.session_state.user_id = None; st.rerun()
    else:
        st.warning("⚠️ Bạn đang dùng **CHẾ ĐỘ KHÁCH (GUEST MODE)**.\n\nDữ liệu sẽ được lưu tạm thời trên trình duyệt và **SẼ MẤT** nếu bạn tải lại trang hoặc tắt tab.\n\nĐể lưu trữ vĩnh viễn, vui lòng đăng ký tài khoản.")
        with st.expander("🔐 Đăng nhập / Đăng ký"):
            t1, t2 = st.tabs(["Đăng nhập", "Đăng ký"])
            with t1:
                u = st.text_input("Tài khoản", key="lu"); p = st.text_input("Mật khẩu", type="password", key="lp")
                if st.button("Đăng nhập"):
                    res = login_user(u, p)
                    if res: 
                        st.session_state.user_id = res[0][0]; st.session_state.username = u; st.rerun()
                    else: st.error("Sai tài khoản hoặc mật khẩu")
            with t2:
                nu = st.text_input("Tài khoản mới", key="nu"); np = st.text_input("Mật khẩu mới", type="password", key="np")
                if st.button("Đăng ký"):
                    if create_user(nu, np): st.success("Tạo thành công! Hãy đăng nhập.")
                    else: st.error("Tên tài khoản đã tồn tại")
    st.divider()
    st.link_button("Donate Ủng Hộ ❤️", "https://tsufu.gitbook.io/donate/", type="primary")

st.markdown("""<div class="custom-header"><h1>🖊️ HỆ THỐNG QUẢN LÝ GÓI ĐĂNG KÍ</h1></div>""", unsafe_allow_html=True)

# PHỤC HỒI ĐẦY ĐỦ 3 TAB CHÍNH
tab1, tab2, tab3 = st.tabs(["📋 DANH SÁCH", "✏️ QUẢN LÝ CHI TIẾT", "📂 NHẬP/XUẤT"])

# --- TAB 1: DANH SÁCH & SỬA NHANH ---
with tab1:
    c1, c2, c3 = st.columns([1, 2, 1])
    with c1: price = st.number_input("Giá/tháng (VNĐ):", 50000, step=10000)
    with c3: 
        if st.button("💎 Xem Doanh Thu"): 
            show_monthly_revenue(get_all_customers(), price)
    
    st.divider()
    
    # Hàng nút chức năng
    col_btn, col_search = st.columns([1, 3])
    with col_btn:
        if st.button("➕ Thêm Khách Hàng", type="primary"):
            show_add_modal()
    with col_search:
        search = st.text_input("🔍 Tìm kiếm:", placeholder="Nhập tên hoặc thiết bị...")
    
    # Lấy dữ liệu
    df = get_all_customers()
    if search:
        df = df[df['name'].str.contains(search, case=False) | df['device_info'].str.contains(search, case=False)]
    
    # Xử lý hiển thị
    df_editor = process_data_for_editor(df)
    st.session_state.current_view_df = df_editor

    if not df_editor.empty:
        # HIỂN THỊ BẢNG SỬA TRỰC TIẾP
        edited_df = st.data_editor(
            df_editor,
            column_config={
                "id": None, 
                "name": None, "device_info": None, "reg_date": None, "duration": None, "reg_date_obj": None,
                "Tên Khách Hàng": st.column_config.TextColumn("Tên Khách Hàng", required=True),
                "Ngày ĐK": st.column_config.DateColumn("Ngày ĐK", format="DD/MM/YYYY"),
                "Gói (tháng)": st.column_config.NumberColumn("Gói", min_value=1, format="%d tháng"),
                "Hết Hạn": st.column_config.TextColumn("Hết Hạn", disabled=True), 
                "Trạng Thái": st.column_config.TextColumn("Trạng Thái", disabled=True), 
            },
            column_order=["Tên Khách Hàng", "Thông tin khách hàng", "Ngày ĐK", "Gói (tháng)", "Hết Hạn", "Trạng Thái"],
            use_container_width=True,
            num_rows="dynamic",
            key="editor_changes",
            on_change=save_editor_changes
        )
        st.caption("*Mẹo: Bạn có thể sửa trực tiếp trên bảng. Để xóa, chọn dòng và nhấn phím Delete, hoặc qua Tab Quản Lý.")
    else:
        st.info("Chưa có dữ liệu.")

# --- TAB 2: QUẢN LÝ / SỬA / XÓA (PHỤC HỒI THEO YÊU CẦU) ---
with tab2:
    st.subheader("🛠️ Chỉnh sửa hoặc Xóa Khách Hàng")
    df_edit = get_all_customers()
    if not df_edit.empty:
        # Chọn khách
        opts = df_edit.apply(lambda x: f"{x['id']} - {x['name']}", axis=1)
        choice = st.selectbox("👉 Chọn khách hàng cần thao tác:", opts)
        
        if choice:
            cid = int(choice.split(" - ")[0])
            crec = df_edit[df_edit['id'] == cid].iloc[0]
            
            col_l, col_r = st.columns(2)
            
            # Form Sửa
            with col_l:
                with st.form("edit_legacy"):
                    st.write("📝 **Sửa thông tin:**")
                    en = st.text_input("Tên", crec['name'])
                    ed = st.text_input("Thông tin", crec['device_info'])
                    dt_val = parse_date(crec['reg_date']) or datetime.now()
                    edp = st.date_input("Ngày ĐK", dt_val, format="DD/MM/YYYY")
                    edu = st.number_input("Tháng", value=int(crec['duration']), min_value=1)
                    if st.form_submit_button("Lưu Thay Đổi"):
                        update_customer_db(cid, en, ed, edp.strftime("%d/%m/%Y"), edu)
                        st.success("Đã cập nhật!"); time.sleep(0.5); st.rerun()
            
            # Nút Xóa
            with col_r:
                st.write("🗑️ **Xóa dữ liệu:**")
                st.warning("Hành động này không thể hoàn tác.")
                st.write(f"Bạn đang chọn xóa khách: **{crec['name']}**")
                if st.button("❌ XÁA KHÁCH HÀNG NÀY", type="primary"):
                    delete_customer_db(cid)
                    st.success("Đã xóa thành công!"); time.sleep(0.5); st.rerun()
    else:
        st.info("Chưa có dữ liệu để quản lý.")

# --- TAB 3: NHẬP/XUẤT (PHỤC HỒI TÍNH NĂNG NHẬP THÔNG MINH) ---
with tab3:
    imp, exp = st.columns(2)
    with imp:
        st.subheader("📥 Nhập dữ liệu (Import)")
        st.caption("Hỗ trợ: Copy/Paste văn bản JSON hoặc CSV. Tự động điền ngày nếu thiếu.")
        with st.form("paste"):
            txt = st.text_area("Dán dữ liệu vào đây (JSON hoặc CSV)", height=200)
            if st.form_submit_button("🚀 Xử lý & Nhập"):
                try:
                    clean = txt.strip()
                    # Logic nhận diện JSON
                    if clean.startswith("[") or clean.startswith("{"):
                        try: df_up = pd.DataFrame(json.loads(clean))
                        except: df_up = pd.DataFrame(ast.literal_eval(clean))
                    else:
                        # Logic nhận diện CSV
                        df_up = pd.read_csv(io.StringIO(clean), sep=None, engine='python', header=None)
                        if df_up.iloc[0].apply(lambda x: isinstance(x, str)).all():
                            df_up = pd.read_csv(io.StringIO(clean), sep=None, engine='python')
                    
                    if not df_up.empty:
                        df_c = smart_import(df_up)
                        cnt = 0
                        for _, r in df_c.iterrows():
                            add_customer(r['name'], r['device_info'], r['reg_date'], r['duration'])
                            cnt += 1
                        st.success(f"Đã nhập thành công {cnt} khách hàng!"); time.sleep(1); st.rerun()
                    else: st.error("Không tìm thấy dữ liệu.")
                except Exception as e: st.error(f"Lỗi định dạng: {e}")
    
    with exp:
        st.subheader("📤 Xuất dữ liệu (Export)")
        dfe = get_all_customers()
        if not dfe.empty:
            st.download_button("Tải xuống CSV (Excel)", dfe.to_csv(index=False).encode('utf-8'), "data.csv", "text/csv")
            st.download_button("Tải xuống JSON", dfe.to_json(orient="records", force_ascii=False).encode('utf-8'), "data.json", "application/json")
        else:
            st.warning("Chưa có dữ liệu để xuất.")

st.markdown("""<div class="footer">Dev by Tsufu / Phú Trần Trung Lê | <a href="https://tsufu.gitbook.io/donate/" target="_blank">Donate Coffee ☕</a></div>""", unsafe_allow_html=True)