import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta
import requests
import time
import io

# ==========================================
# 1. การเชื่อมต่อ DATABASE & CONFIG
# ==========================================
SUPABASE_URL = "https://qejqynbxdflwebzzwfzu.supabase.co" 
SUPABASE_KEY = "sb_publishable_hvNQEPvuEAlXfVeCzpy7Ug_kzvihQqq"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

CURRENT_BOT_ID = "@871fsfnr"  
LINE_ADD_FRIEND_URL = f"https://line.me/R/ti/p/{CURRENT_BOT_ID}"

st.set_page_config(page_title="ระบบจองรถและห้องประชุม - Sansuisha", layout="wide")

st.markdown("""
    <style>
    @keyframes blinker { 50% { opacity: 0; } }
    .blink { animation: blinker 1s linear infinite; color: #FF0000; font-weight: bold; font-size: 18px; }
    .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] {
        background-color: #E3F2FD !important; color: #0D47A1 !important; border: 1px solid #BBDEFB !important;
    }
    .main-title { font-size: 35px; font-weight: bold; color: #1E88E5; text-align: center; margin-bottom: 20px;}
    
    [data-testid="stLinkButton"] a {
        background-color: #8BC34A !important; color: white !important;
        border-radius: 8px !important; font-weight: bold !important;
        border: none !important; text-align: center !important;
    }
    [data-testid="stLinkButton"] a:hover { background-color: #4CAF50 !important; }
    [data-testid="stLinkButton"] a:active { background-color: #2E7D32 !important; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. ฟังก์ชันหลัก (CORE FUNCTIONS) & ตั้งค่าระบบ
# ==========================================
def load_settings():
    res = supabase.table("app_settings").select("*").execute()
    if not res.data:
        default_data = {
            "id": 1,
            "line_token": "**",
            "line_secret": "**",
            "group_id": "Cad74a32468ca40051bd7071a6064660d",
            "car_list": "Civic (ตุ้ม),Civic (บอล),Camry (เนก),MG,MG (เนก)",
            "room_list": "ห้องชั้น 1 (ห้องใหญ่),ห้องชั้น 2,ห้อง VIP,ห้องชั้นลอย,ห้อง Production",
            "dept_list": "AC,HR,Sales,QA,PE,Fac,Loading,Unload,Coating,Repair,Delivery,Assembly,QC - MS,Metal sheet,Factory 1,Factory 2,Admin (JP)"
        }
        supabase.table("app_settings").insert(default_data).execute()
        return default_data
    return res.data[0]

sys_settings = load_settings()
SYS_CARS = [x.strip() for x in sys_settings['car_list'].split(',') if x.strip()]
SYS_ROOMS = [x.strip() for x in sys_settings['room_list'].split(',') if x.strip()]
SYS_DEPTS = [x.strip() for x in sys_settings['dept_list'].split(',') if x.strip()]

def format_time_string(t_raw):
    clean = str(t_raw).replace(":", "").strip()
    if len(clean) == 4: return f"{clean[:2]}:{clean[2:]}"
    return clean

def check_booking_conflict(resource, start_time_iso, end_time_iso):
    res = supabase.table("bookings").select("*").eq("resource", resource).in_("status", ["Approved", "Pending"]).execute()
    new_s = datetime.fromisoformat(start_time_iso).replace(tzinfo=None)
    new_e = datetime.fromisoformat(end_time_iso).replace(tzinfo=None)
    for item in res.data:
        ex_s = pd.to_datetime(item['start_time']).replace(tzinfo=None)
        ex_e = pd.to_datetime(item['end_time']).replace(tzinfo=None)
        if new_s < ex_e and new_e > ex_s:
            return True, item['requester'], item['status']
    return False, None, None
    
def send_line_notification(booking_id, resource, name, dept, t_start, t_end, purpose, destination, status_text="Pending"):
    render_url = "https://line-booking-system.onrender.com/notify"
    try:
        s_dt = pd.to_datetime(t_start)
        s_str = s_dt.strftime("%d/%m/%Y %H:%M")
        e_str = t_end if isinstance(t_end, str) else pd.to_datetime(t_end).strftime("%H:%M")
        payload = {
            "id": booking_id, "target_id": sys_settings['group_id'], "resource": resource, 
            "name": name, "dept": dept, "date": s_str, "end_date": e_str, 
            "purpose": purpose, "destination": destination, "status": status_text
        }
        requests.post(render_url, json=payload, timeout=30)
    except: pass

def auto_delete_old_bookings():
    threshold = (datetime.now() - timedelta(days=45)).isoformat()
    try: supabase.table("bookings").delete().lt("end_time", threshold).execute()
    except: pass

# ==========================================
# 3. ระบบ LOGIN & AUTHENTICATION
# ==========================================
if "admin_logged_in" not in st.session_state:
    st.session_state["admin_logged_in"] = False
if "admin_user" not in st.session_state:
    st.session_state["admin_user"] = ""

def check_admin_login():
    if st.session_state["admin_logged_in"]:
        return True
    
    st.subheader("🔐 เข้าสู่ระบบผู้ดูแลระบบ (Admin)")
    try:
        admins_data = supabase.table("app_admins").select("*").execute().data
    except Exception as e:
        st.error(f"ไม่สามารถดึงข้อมูล Admin ได้ กรุณาตรวจสอบตาราง app_admins: {e}")
        return False

    # กรณีไม่มี Admin ในระบบเลย (ทำครั้งแรก)
    if not admins_data:
        st.info("👋 ยินดีต้อนรับ! ระบบตรวจพบว่ายังไม่มี Admin กรุณาสร้างบัญชี Admin คนแรกเพื่อเริ่มใช้งาน")
        with st.form("first_admin_form"):
            new_u = st.text_input("ตั้ง Username")
            new_p = st.text_input("ตั้ง Password", type="password")
            if st.form_submit_button("บันทึก Admin คนแรก", type="primary"):
                if new_u and new_p:
                    supabase.table("app_admins").insert({"username": new_u, "password": new_p}).execute()
                    st.success("✅ สร้าง Admin สำเร็จ! กรุณาเข้าสู่ระบบ")
                    time.sleep(1.5)
                    st.rerun()
                else:
                    st.error("⚠️ กรุณากรอก Username และ Password ให้ครบ")
        return False
    
    # กรณีมี Admin แล้ว -> แสดงหน้า Login ปกติ
    else:
        with st.form("login_form"):
            login_u = st.text_input("Username")
            login_p = st.text_input("Password", type="password")
            if st.form_submit_button("เข้าสู่ระบบ", type="primary"):
                match = [a for a in admins_data if a['username'] == login_u and a['password'] == login_p]
                if match:
                    st.session_state["admin_logged_in"] = True
                    st.session_state["admin_user"] = match[0]['username']
                    st.success("✅ เข้าสู่ระบบสำเร็จ!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("❌ Username หรือ Password ไม่ถูกต้อง")
        return False

# ==========================================
# 4. SIDEBAR & NAVIGATION
# ==========================================
auto_delete_old_bookings()
pending_items = supabase.table("bookings").select("id").eq("status", "Pending").execute().data
pending_count = len(pending_items)

st.sidebar.image("https://lh3.googleusercontent.com/d/1zCjSjSbCO-mbsaGoDI6g0G-bfmyVfqFV", use_container_width=True)
st.sidebar.link_button(label="➕ เพิ่มเพื่อน LINE (ดูคิว/สถานะ)", url=LINE_ADD_FRIEND_URL, use_container_width=True, type="primary")
st.sidebar.markdown(f"<p style='text-align: center; color: gray; font-size: 12px;'>Line ID: {CURRENT_BOT_ID}</p>", unsafe_allow_html=True)

if pending_count > 0:
    st.sidebar.markdown(f'<p class="blink">📢 มีรายการรออนุมัติ: {pending_count}</p>', unsafe_allow_html=True)

st.sidebar.markdown("---")

# แสดงสถานะ Login ใน Sidebar
if st.session_state["admin_logged_in"]:
    st.sidebar.success(f"👤 เข้าสู่ระบบแล้ว:\n**{st.session_state['admin_user']}**")
    if st.sidebar.button("🚪 ออกจากระบบ (Logout)", use_container_width=True):
        st.session_state["admin_logged_in"] = False
        st.session_state["admin_user"] = ""
        st.rerun()
    st.sidebar.markdown("---")

menu = ["📝 จองใหม่", "📅 ตารางงาน (Real-time)", "⭐ ประเมินการใช้งาน", "🔑 Admin (อนุมัติ)", "📊 รายงานประจำเดือน", "⚙️ ตั้งค่าระบบ (Admin)"]
choice = st.sidebar.selectbox("เมนูจัดการระบบ", menu)

# ==========================================
# 5. หน้าจองใหม่ (BOOKING)
# ==========================================
if choice == "📝 จองใหม่":
    st.markdown('<div class="main-title">ระบบจองรถยนต์และห้องประชุม Online</div>', unsafe_allow_html=True)
    st.markdown('##### 📋 ข้อมูลรถและคนขับ (อ้างอิงจากฐานข้อมูล)')
    
    now_dt = datetime.utcnow() + timedelta(hours=7)
    t_today_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    t_today_end = now_dt.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()
    
    today_bookings = supabase.table("bookings").select("resource, start_time, end_time").eq("status", "Approved").gte("start_time", t_today_start).lte("start_time", t_today_end).execute()
        
    car_status = {car: {"text": "🟢 ปัจจุบันว่าง", "time": "", "class": "status-free"} for car in SYS_CARS}
    room_status = {room: {"text": "🟢 ปัจจุบันว่าง", "time": "", "class": "status-free"} for room in SYS_ROOMS}

    if today_bookings.data:
        for b in today_bookings.data:
            res_name = b['resource']
            st_dt = pd.to_datetime(b['start_time']).tz_localize(None)
            en_dt = pd.to_datetime(b['end_time']).tz_localize(None)
            
            if st_dt <= now_dt <= en_dt:
                if res_name in car_status:
                    car_status[res_name]["text"] = "🔴 ไม่ว่าง"
                    car_status[res_name]["time"] = f"{st_dt.strftime('%H:%M')} - {en_dt.strftime('%H:%M')}"
                    car_status[res_name]["class"] = "status-busy"
                elif res_name in room_status:
                    room_status[res_name]["text"] = "🔴 ไม่ว่าง"
                    room_status[res_name]["time"] = f"{st_dt.strftime('%H:%M')} - {en_dt.strftime('%H:%M')}"
                    room_status[res_name]["class"] = "status-busy"

    st.markdown("""<style>.status-badge { text-align: center; font-size: 12px; padding: 4px 10px; border-radius: 20px; font-weight: bold; min-width: 85px; margin-top:5px;} .status-free { background-color: #E8F5E9; color: #2E7D32; border: 1px solid #A5D6A7; } .status-busy { background-color: #FFEBEE; color: #C62828; border: 1px solid #EF9A9A; } .status-time { font-size: 11px; font-weight: normal; }</style>""", unsafe_allow_html=True)
    
    col_c1, col_c2, col_c3, col_c4, col_c5 = st.columns(5)
    cols = [col_c1, col_c2, col_c3, col_c4, col_c5]
    for i, car in enumerate(SYS_CARS):
        with cols[i % 5].container(border=True):
            st.markdown(f"**🚗 {car}**")
            st.markdown(f"<div class='status-badge {car_status[car]['class']}'><div>{car_status[car]['text']}</div><div class='status-time'>{car_status[car]['time']}</div></div>", unsafe_allow_html=True)
    
    st.markdown("---")
    
    today_approved_res = supabase.table("bookings").select("id").eq("status", "Approved").gte("start_time", t_today_start).lte("start_time", t_today_end).execute()
    today_approved_count = len(today_approved_res.data) if today_approved_res.data else 0
    d1, d2, d3 = st.columns(3)
    d1.metric("รายการจองวันนี้", f"{today_approved_count} รายการ")
    d2.metric("รอพี่อนุมัติ", f"{pending_count} รายการ")
    d3.metric("สถานะฐานข้อมูล", "Connected")
    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        cat = st.radio("ประเภททรัพยากร", ["รถยนต์", "ห้องประชุม"], horizontal=True)
        res_list = SYS_CARS if cat == "รถยนต์" else SYS_ROOMS
        res = st.selectbox("เลือกรายการ", res_list)
        dest = st.text_input("สถานที่ปลายทาง") if cat == "รถยนต์" else "Office"
        name = st.text_input("ชื่อผู้จอง")
        phone = st.text_input("เบอร์โทรศัพท์")
        dept = st.selectbox("แผนก", SYS_DEPTS)

    with col2:
        d_start = st.date_input("วันที่เริ่ม", datetime.now().date(), min_value=datetime.now().date())
        t_s_raw = st.text_input("เวลาเริ่ม (เช่น 0800)", value="", placeholder="กรอกเวลา เช่น 0800", max_chars=4)
        st.markdown("---")
        d_end = st.date_input("วันที่สิ้นสุด", d_start, min_value=d_start)
        t_e_raw = st.text_input("เวลาสิ้นสุด (เช่น 1700)", value="", placeholder="กรอกเวลา เช่น 1700", max_chars=4)
        reason = st.text_area("วัตถุประสงค์การใช้งาน")
        
        try:
            ts_f, te_f = format_time_string(t_s_raw.strip()), format_time_string(t_e_raw.strip())
            ts = datetime.combine(d_start, datetime.strptime(ts_f, "%H:%M").time())
            te = datetime.combine(d_end, datetime.strptime(te_f, "%H:%M").time())
        except: ts, te = None, None

    if st.button("ยืนยันการส่งคำขอจอง", use_container_width=True):
        if not name or not dept or ts is None:
            st.warning("⚠️ กรุณากรอกข้อมูลให้ครบถ้วน")
        elif ts < datetime.now(): 
            st.error("❌ ไม่สามารถจองย้อนหลังได้ กรุณาเลือกเวลาปัจจุบันหรือล่วงหน้า")
        elif ts >= te:
            st.error("❌ เวลาเริ่มต้องมาก่อนเวลาสิ้นสุด")
        else:
            is_conf, user_conf, status_conf = check_booking_conflict(res, ts.isoformat(), te.isoformat())
            if is_conf:
                msg = "ถูกจองแล้ว" if status_conf == "Approved" else "มีคนกำลังรออนุมัติ"
                st.error(f"❌ คิวชนกัน! {res} {msg} โดยคุณ {user_conf} ในเวลานี้")
            else:
                data = {"resource": res, "requester": name, "phone": phone, "dept": dept, "start_time": ts.isoformat(), "end_time": te.isoformat(), "purpose": reason, "destination": dest, "status": "Pending"}
                resp = supabase.table("bookings").insert(data).execute()
                if resp.data:
                    send_line_notification(resp.data[0]['id'], res, name, dept, ts, te, reason, dest)
                    st.success("✅ ส่งคำขอเรียบร้อย! โปรดรอ Admin อนุมัติ")
                    st.markdown('<div class="blink" style="text-align:center; padding:15px; background-color:#FFF9C4; border-radius:10px; border: 2px solid #FBC02D;">⭐ อย่าลืมเข้ามาให้คะแนนพนักงานขับรถหลังใช้งานเสร็จนะครับ ⭐</div>', unsafe_allow_html=True)
                    st.balloons()
                    time.sleep(3)
                    st.rerun()

# ==========================================
# 6. หน้าตารางงาน 
# ==========================================
elif choice == "📅 ตารางงาน (Real-time)":
    st.subheader("📅 ตารางการใช้งานปัจจุบันและล่วงหน้า")
    
    f_c1, f_c2 = st.columns([2, 1])
    search_q = f_c1.text_input("🔍 ค้นหาชื่อผู้จอง / สถานที่")
    view_cat = f_c2.selectbox("กรองตามประเภท", ["ทั้งหมด", "รถยนต์", "ห้องประชุม"])
    
    t_today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    db_res = supabase.table("bookings").select("*").eq("status", "Approved").gte("start_time", t_today_start).order("start_time").execute()
    df = pd.DataFrame(db_res.data)
    
    if df.empty:
        st.info("ขณะนี้ไม่มีรายการจอง")
    else:
        if view_cat == "รถยนต์": df = df[df['resource'].isin(SYS_CARS)]
        elif view_cat == "ห้องประชุม": df = df[df['resource'].isin(SYS_ROOMS)]
        if search_q: df = df[df['requester'].str.contains(search_q, case=False, na=False) | df['destination'].str.contains(search_q, case=False, na=False)]
        
        if not df.empty:
            df_show = df.copy().reset_index(drop=True)
            df_show.index += 1
            df_show.insert(0, 'ลำดับ/No.', df_show.index)
            
            df_show['start_fmt'] = pd.to_datetime(df_show['start_time'], errors='coerce').dt.strftime('%d/%m/%Y %H:%M')
            df_show['end_fmt'] = pd.to_datetime(df_show['end_time'], errors='coerce').dt.strftime('%d/%m/%Y %H:%M')
            
            df_disp = df_show[['ลำดับ/No.', 'resource', 'start_fmt', 'end_fmt', 'requester', 'purpose', 'destination']]
            df_disp.columns = ['ลำดับ / No.', 'รายการ / Resource', 'เวลาเริ่ม / Start Time', 'เวลาสิ้นสุด / End Time', 'ผู้จอง / Name', 'วัตถุประสงค์ / Purpose', 'ปลายทาง / Destination']
            st.dataframe(df_disp, use_container_width=True)

            st.markdown("---")
            with st.expander("🛠️ จัดการข้อมูล (แก้ไข/ลบ โดย Admin)"):
                # เปลี่ยนจากกรอกรหัส s1234 เป็นให้เช็ค Login Session
                if not st.session_state["admin_logged_in"]:
                    st.warning("⚠️ เฉพาะผู้ดูแลระบบเท่านั้น กรุณาเข้าสู่ระบบผ่านเมนู '🔑 Admin' ทางซ้ายมือก่อนใช้งานส่วนนี้")
                else:
                    sel_no = st.selectbox("เลือก No. ลำดับที่ต้องการจัดการ", df_show['ลำดับ/No.'].tolist())
                    row = df_show[df_show['ลำดับ/No.'] == sel_no].iloc[0]
                    
                    with st.form("edit_full_form"):
                        e_col1, e_col2 = st.columns(2)
                        all_res = SYS_CARS + SYS_ROOMS
                        try: res_idx = all_res.index(row['resource'])
                        except: res_idx = 0 
                        
                        n_res = e_col1.selectbox("รายการ / Resource", all_res, index=res_idx)
                        n_req = e_col1.text_input("ผู้จอง / Name", str(row['requester']))
                        n_dest = e_col1.text_input("ปลายทาง / Destination", str(row.get('destination', '-')))
                        
                        dt_s = pd.to_datetime(row['start_time'])
                        dt_e = pd.to_datetime(row['end_time'])
                        n_d_s = e_col2.date_input("วันที่เริ่ม", dt_s.date())
                        n_t_s = e_col2.text_input("เวลาเริ่ม (4 หลัก)", dt_s.strftime("%H%M"))
                        n_d_e = e_col2.date_input("วันที่สิ้นสุด", dt_e.date())
                        n_t_e = e_col2.text_input("เวลาสิ้นสุด (4 หลัก)", dt_e.strftime("%H%M"))
                        
                        n_purp = st.text_area("วัตถุประสงค์ / Purpose", str(row.get('purpose', '-')))
                        
                        b1, b2 = st.columns(2)
                        if b1.form_submit_button("💾 บันทึกการแก้ไข", use_container_width=True):
                            try:
                                fs, fe = format_time_string(n_t_s), format_time_string(n_t_e)
                                f_start = datetime.combine(n_d_s, datetime.strptime(fs, "%H:%M").time()).isoformat()
                                f_end = datetime.combine(n_d_e, datetime.strptime(fe, "%H:%M").time()).isoformat()
                                supabase.table("bookings").update({
                                    "resource": n_res, "requester": n_req, "destination": n_dest, 
                                    "purpose": n_purp, "start_time": f_start, "end_time": f_end
                                }).eq("id", row['id']).execute()
                                st.success("อัปเดตเรียบร้อย!"); st.rerun()
                            except: st.error("❌ รูปแบบเวลาผิด")
                        
                        if b2.form_submit_button("🗑️ ลบรายการนี้", use_container_width=True):
                            supabase.table("bookings").delete().eq("id", row['id']).execute(); st.rerun()

# ==========================================
# 7. เมนู ⭐ ประเมินการใช้งาน
# ==========================================
elif choice == "⭐ ประเมินการใช้งาน":
    st.subheader("⭐ ประเมินการปฏิบัติงานพนักงานขับรถ")
    now_iso = (datetime.utcnow() + timedelta(hours=7)).isoformat()
    try:
        res = supabase.table("bookings").select("*").eq("status", "Approved").in_("resource", SYS_CARS).lt("end_time", now_iso).execute()
        data = res.data
        unrated = [d for d in data if not d.get("is_rated")]
        
        if not unrated:
            st.success("🎉 ไม่มีรายการที่ต้องประเมินในขณะนี้ครับ ทุกรายการได้รับการให้คะแนนครบถ้วนแล้ว")
        else:
            st.info("💡 กรุณาเลือกรายการจองรถยนต์ที่เพิ่งใช้งานเสร็จสิ้นเพื่อทำการประเมินพนักงานขับรถ")
            options_dict = {}
            for d in sorted(unrated, key=lambda x: x['end_time'], reverse=True):
                end_dt_str = pd.to_datetime(d['end_time']).strftime('%d/%m/%Y %H:%M')
                label = f"วันที่: {end_dt_str} | รถ: {d['resource']} | ผู้จอง: {d['requester']}"
                options_dict[label] = d
                
            selected_label = st.selectbox("เลือกรถที่ต้องการประเมิน", list(options_dict.keys()))
            selected_booking = options_dict[selected_label]
            
            st.markdown("---")
            st.markdown(f"กำลังประเมินพนักงานขับรถสำหรับรายการ **{selected_booking['resource']}**")
            
            with st.form("rating_form"):
                st.write("**หัวข้อประเมิน (1 = ต้องปรับปรุง, 5 = ดีมาก)**")
                q1 = st.radio("พนักงานขับรถมีสภาพร่างกายพร้อมปฏิบัติงาน", [1, 2, 3, 4, 5], index=4, horizontal=True)
                q2 = st.radio("สภาพรถพร้อมใช้งานมีความสะอาดและปลอดภัย", [1, 2, 3, 4, 5], index=4, horizontal=True)
                q3 = st.radio("ขับรถด้วยความระมัดระวังและปลอดภัย", [1, 2, 3, 4, 5], index=4, horizontal=True)
                q4 = st.radio("กิริยาวาจาและพฤติกรรมมีความเหมาะสม", [1, 2, 3, 4, 5], index=4, horizontal=True)
                suggestion = st.text_area("ข้อเสนอแนะอื่นๆ")
                
                st.warning("⚠️ โปรดตรวจสอบข้อมูลให้ครบถ้วนก่อนส่ง (ไม่สามารถแก้ไขข้อมูลได้ภายหลังการให้คะแนน)")
                confirm = st.checkbox("แน่ใจ / ยืนยันข้อมูล")
                
                if st.form_submit_button("ส่งผลการประเมิน", type="primary"):
                    if not confirm:
                        st.error("❌ กรุณากดยืนยัน (ติ๊กถูกที่ช่อง แน่ใจ / ยืนยันข้อมูล) ก่อนส่งผลประเมินครับ")
                    else:
                        supabase.table("bookings").update({
                            "is_rated": True, "q1": q1, "q2": q2, "q3": q3, "q4": q4, "suggestion": suggestion
                        }).eq("id", selected_booking['id']).execute()
                        st.success("✅ บันทึกผลการประเมินเรียบร้อยแล้ว ขอบคุณที่ใช้บริการครับ!")
                        time.sleep(2)
                        st.rerun()
    except Exception as e:
        st.error(f"ไม่สามารถเชื่อมต่อฐานข้อมูลประเมินได้: {e}")

# ==========================================
# 8. หน้า ADMIN (APPROVAL) (Protected)
# ==========================================
elif choice == "🔑 Admin (อนุมัติ)":
    if check_admin_login():
        st.subheader("🔑 ระบบจัดการคำขอ (อนุมัติการจอง)")
        items = supabase.table("bookings").select("*").eq("status", "Pending").order("id").execute().data
        if not items: st.info("ไม่มีรายการรออนุมัติ")
        else:
            for item in items:
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
                    curr_start = pd.to_datetime(item['start_time'])
                    with c1:
                        st.write(f"🚗 **{item['resource']}** | 👤 {item['requester']}")
                        st.write(f"📍 {item.get('destination','-')} | 🎯 {item.get('purpose','-')}")
                        a_d = st.date_input("ยืนยันวันที่", curr_start.date(), key=f"d_{item['id']}")
                        a_t = st.text_input("ยืนยันเวลาเริ่ม (4 หลัก)", curr_start.strftime("%H%M"), key=f"t_{item['id']}")
                    
                    if c2.button("อนุมัติ ✅", key=f"ap_{item['id']}", use_container_width=True):
                        try:
                            f_time = format_time_string(a_t)
                            final_start = datetime.combine(a_d, datetime.strptime(f_time, "%H:%M").time()).isoformat()
                            supabase.table("bookings").update({"status": "Approved", "start_time": final_start}).eq("id", item['id']).execute()
                            send_line_notification(item['id'], item['resource'], item['requester'], item['dept'], final_start, item['end_time'], item['purpose'], item.get('destination','-'), "Approved")
                            st.rerun()
                        except Exception as e: st.error(f"❌ รูปแบบเวลาผิด: {e}")
                    
                    if c2.button("ลบ 🗑️", key=f"dl_{item['id']}", use_container_width=True):
                        supabase.table("bookings").delete().eq("id", item['id']).execute(); st.rerun()

# ==========================================
# 9. หน้ารายงาน (REPORT) (Protected)
# ==========================================
elif choice == "📊 รายงานประจำเดือน":
    if check_admin_login():
        st.subheader("📊 รายงานสรุปการใช้ทรัพยากรและการประเมิน")
        data = supabase.table("bookings").select("*").eq("status", "Approved").execute().data
        if data:
            df_rep = pd.DataFrame(data)
            df_rep['start_time'] = pd.to_datetime(df_rep['start_time'])
            df_rep['Month-Year'] = df_rep['start_time'].dt.strftime('%m/%Y')
            
            c1, c2 = st.columns(2)
            sel_m = c1.selectbox("เลือกเดือน", sorted(df_rep['Month-Year'].unique(), reverse=True))
            rep_type = st.selectbox("ประเภทรายงาน", ["ทั้งหมด", "รถยนต์", "ห้องประชุม"])
            
            f_df = df_rep[df_rep['Month-Year'] == sel_m].copy()
            if rep_type == "รถยนต์": f_df = f_df[f_df['resource'].isin(SYS_CARS)]
            elif rep_type == "ห้องประชุม": f_df = f_df[f_df['resource'].isin(SYS_ROOMS)]
            
            f_df['เวลาเริ่ม'] = f_df['start_time'].dt.strftime('%d/%m/%Y %H:%M')
            out_df = f_df[['resource', 'requester', 'dept', 'เวลาเริ่ม', 'destination', 'purpose']].copy()
            
            if 'is_rated' in f_df.columns:
                out_df['ประเมิน'] = f_df['is_rated'].apply(lambda x: 'ใช่' if x == True else 'ยัง')
                out_df['ร่างกาย'] = f_df.get('q1', '-')
                out_df['ความสะอาด'] = f_df.get('q2', '-')
                out_df['ขับปลอดภัย'] = f_df.get('q3', '-')
                out_df['มารยาท'] = f_df.get('q4', '-')
                out_df['ข้อเสนอแนะ'] = f_df.get('suggestion', '-')
                
                if rep_type in ["ทั้งหมด", "รถยนต์"]:
                    st.markdown("---")
                    st.markdown("#### ⭐ สรุปเปอร์เซ็นต์ความพึงพอใจพนักงานขับรถเฉลี่ย ประจำเดือน")
                    rated_cars = f_df[(f_df['resource'].isin(SYS_CARS)) & (f_df['is_rated'] == True)]
                    
                    if not rated_cars.empty:
                        avg1, avg2, avg3, avg4 = (rated_cars['q1'].mean()/5)*100, (rated_cars['q2'].mean()/5)*100, (rated_cars['q3'].mean()/5)*100, (rated_cars['q4'].mean()/5)*100
                        total_avg = (avg1 + avg2 + avg3 + avg4) / 4
                        st.success(f"📈 ภาพรวมเฉลี่ยความพึงพอใจ: **{total_avg:.2f}%**")
                        sc1, sc2, sc3, sc4 = st.columns(4)
                        sc1.metric("1. สภาพร่างกาย", f"{avg1:.2f}%")
                        sc2.metric("2. สภาพรถ/ความสะอาด", f"{avg2:.2f}%")
                        sc3.metric("3. การขับรถปลอดภัย", f"{avg3:.2f}%")
                        sc4.metric("4. มารยาท", f"{avg4:.2f}%")
                    else: st.info("ยังไม่มีข้อมูลการประเมินในเดือนที่เลือก")
            
            st.markdown("---")
            st.dataframe(out_df, use_container_width=True)
            
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='xlsxwriter') as w: out_df.to_excel(w, index=False)
            st.download_button("📥 ดาวน์โหลดรายงาน (Excel)", buf.getvalue(), f"Report_{rep_type}_{sel_m.replace('/', '-')}.xlsx")

# ==========================================
# 10. เมนู ⚙️ ตั้งค่าระบบ (Protected)
# ==========================================
elif choice == "⚙️ ตั้งค่าระบบ (Admin)":
    if check_admin_login():
        st.subheader("⚙️ จัดการข้อมูลระบบ (ไม่ต้องแก้ไขโค้ด)")
        
        tab1, tab2 = st.tabs(["🔧 ตั้งค่าระบบหลัก", "👥 จัดการผู้ดูแลระบบ (Admin)"])
        
        with tab1:
            st.info("💡 คำแนะนำ: สำหรับรายชื่อรถ ห้อง และแผนก ให้ใช้เครื่องหมายลูกน้ำ (,) คั่นระหว่างรายชื่อเสมอ")
            with st.form("settings_form"):
                new_cars = st.text_area("🚗 รายชื่อรถยนต์ (และชื่อคนขับ)", sys_settings.get('car_list', ''))
                new_rooms = st.text_area("🏢 รายชื่อห้องประชุม", sys_settings.get('room_list', ''))
                new_depts = st.text_area("🏢 รายชื่อแผนก", sys_settings.get('dept_list', ''))
                
                st.markdown("---")
                st.markdown("##### 🔐 การตั้งค่า LINE Bot (สำหรับนักพัฒนา)")
                new_token = st.text_input("LINE Access Token", sys_settings.get('line_token', ''))
                new_secret = st.text_input("LINE Secret", sys_settings.get('line_secret', ''))
                new_group = st.text_input("LINE Group ID (ห้องแชทที่ให้แจ้งเตือน)", sys_settings.get('group_id', ''))
                
                st.warning("⚠️ การแก้ไขข้อมูลนี้จะส่งผลต่อระบบทั้งหมดทันที กรุณาตรวจสอบให้ถูกต้องก่อนกดบันทึก")
                confirm = st.checkbox("☑️ ฉันตรวจสอบข้อมูลแล้ว และยืนยันการแก้ไขข้อมูล")
                
                if st.form_submit_button("💾 บันทึกการตั้งค่า", type="primary"):
                    if confirm:
                        supabase.table("app_settings").update({
                            "car_list": new_cars, "room_list": new_rooms, "dept_list": new_depts,
                            "line_token": new_token, "line_secret": new_secret, "group_id": new_group
                        }).eq("id", 1).execute()
                        st.success("✅ บันทึกข้อมูลตั้งค่าสำเร็จ!")
                        time.sleep(2)
                        st.rerun()
                    else:
                        st.error("❌ กรุณาติ๊กถูกที่ช่อง 'ยืนยันการแก้ไขข้อมูล' ก่อนกดบันทึกครับ")
        
        with tab2:
            st.markdown("##### 👥 รายชื่อ Admin ในระบบ")
            admins = supabase.table("app_admins").select("*").execute().data
            if admins:
                for a in admins:
                    col_u, col_d = st.columns([4, 1])
                    col_u.markdown(f"👤 **{a['username']}**")
                    if col_d.button("🗑️ ลบ", key=f"del_adm_{a['id']}", use_container_width=True):
                        if len(admins) == 1:
                            st.error("❌ ไม่สามารถลบ Admin คนสุดท้ายได้")
                        else:
                            supabase.table("app_admins").delete().eq("id", a['id']).execute()
                            st.rerun()
            st.markdown("---")
            st.markdown("##### ➕ เพิ่ม Admin ใหม่")
            with st.form("add_admin_form"):
                n_user = st.text_input("Username ใหม่")
                n_pass = st.text_input("Password ใหม่", type="password")
                if st.form_submit_button("บันทึก Admin ใหม่"):
                    if not n_user or not n_pass:
                        st.error("กรุณากรอกข้อมูลให้ครบถ้วน")
                    else:
                        is_dup = any(x['username'] == n_user for x in admins)
                        if is_dup:
                            st.error("❌ Username นี้มีอยู่แล้วในระบบ")
                        else:
                            supabase.table("app_admins").insert({"username": n_user, "password": n_pass}).execute()
                            st.success(f"✅ เพิ่ม Admin {n_user} สำเร็จ!")
                            time.sleep(1)
                            st.rerun()
