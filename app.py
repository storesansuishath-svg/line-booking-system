import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta
import requests

# --- 1. การเชื่อมต่อ Supabase ---
SUPABASE_URL = "https://qejqynbxdflwebzzwfzu.supabase.co"
SUPABASE_KEY = "sb_publishable_hvNQEPvuEAlXfVeCzpy7Ug_kzvihQqq"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 2. ฟังก์ชันลบข้อมูลอัตโนมัติ ---
def auto_delete_old_bookings():
    threshold_time = (datetime.now() - timedelta(hours=24)).isoformat()
    try:
        supabase.table("bookings").delete().lt("end_time", threshold_time).execute()
    except:
        pass

# --- 3. ตั้งค่าหน้าจอ ---
st.set_page_config(page_title="ระบบจองรถ & ห้องประชุม", layout="wide")
LOGO_URL = "https://lh3.googleusercontent.com/d/1zCjSjSbCO-mbsaGoDI6g0G-bfmyVfqFV"
st.sidebar.image(LOGO_URL, use_container_width=True)
st.sidebar.markdown("---")

auto_delete_old_bookings()
st.title("ระบบจองรถยนต์และห้องประชุม Online")

menu = ["📝 จองใหม่", "📅 ตารางงาน (Real-time)", "🔑 Admin (อนุมัติ)"]
choice = st.sidebar.selectbox("เมนู", menu)

# --- หน้าจองใหม่ ---
if choice == "📝 จองใหม่":
    st.subheader("รายละเอียดการจอง")
    col1, col2 = st.columns(2)
    with col1:
        cat = st.radio("ประเภททรัพยากร", ["รถยนต์", "ห้องประชุม"])
        if cat == "รถยนต์":
            res = st.selectbox("เลือกคัน", ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG ขับเอง"])
            destination = st.text_input("สถานที่ปลายทาง", placeholder="เช่น บริษัท ABC")
        else:
            res = st.selectbox("เลือกห้อง", ["ห้องชั้น 1 (ห้องใหญ่)", "ห้องชั้น 2", "ห้อง VIP", "ห้องชั้นลอย", "ห้อง Production"])
            destination = "Office"
        name = st.text_input("ชื่อผู้จอง")
        phone = st.text_input("เบอร์โทรศัพท์")
        dept = st.text_input("แผนก")
    with col2:
        t_start = st.datetime_input("เวลาเริ่ม", datetime.now())
        t_end = st.datetime_input("เวลาสิ้นสุด", datetime.now())
        reason = st.text_area("วัตถุประสงค์การใช้งาน")

    if st.button("ยืนยันการส่งคำขอจอง"):
        if not name or not phone or not reason or not dept:
            st.warning("⚠️ กรุณากรอกข้อมูลให้ครบถ้วน")
        elif t_start >= t_end:
            st.error("❌ เวลาเริ่มต้นต้องก่อนเวลาสิ้นสุด")
        else:
            # ตรวจสอบการจองซ้ำ
            check_res = supabase.table("bookings").select("*").eq("resource", res).eq("status", "Approved").execute()
            df_check = pd.DataFrame(check_res.data)
            is_overlap = False
            if not df_check.empty:
                df_check['start_time'] = pd.to_datetime(df_check['start_time']).dt.tz_localize(None)
                df_check['end_time'] = pd.to_datetime(df_check['end_time']).dt.tz_localize(None)
                overlap = df_check[~((df_check['start_time'] >= t_end) | (df_check['end_time'] <= t_start))]
                if not overlap.empty: is_overlap = True

            if is_overlap:
                st.error(f"❌ ไม่ว่าง: {res} ถูกจองไปแล้วในช่วงเวลานี้")
            else:
                # 1. บันทึกข้อมูลลง Supabase
                data = {"resource": res, "requester": name, "phone": phone, "dept": dept, 
                        "start_time": t_start.isoformat(), "end_time": t_end.isoformat(), 
                        "purpose": reason, "destination": destination, "status": "Pending"}
                supabase.table("bookings").insert(data).execute()
                st.success("✅ ส่งคำขอเรียบร้อยแล้ว!")

                # 2. ส่งแจ้งเตือนไปที่ Render (/notify)
                try:
                    render_url = "https://line-booking-system.onrender.com/notify"
                    payload = {
                        "resource": res,
                        "name": name,
                        "date": t_start.strftime("%d/%m/%Y %H:%M")
                    }
                    resp = requests.post(render_url, json=payload, timeout=10)
                    
                    # บรรทัด Debug (ถ้าสำเร็จจะขึ้นเลข 200 บนหน้าเว็บแวบเดียว)
                    if resp.status_code == 200:
                        st.info("📨 ส่งแจ้งเตือนเข้า LINE แล้ว")
                    else:
                        st.warning(f"⚠️ บอทได้รับข้อมูลแต่ส่ง LINE ไม่สำเร็จ (Code: {resp.status_code})")
                except Exception as e:
                    st.error(f"❌ เชื่อมต่อกับบอทไม่ได้: {e}")

# --- หน้า Admin และ ตารางงาน (ส่วนที่เหลือคงเดิม) ---
elif choice == "🔑 Admin (อนุมัติ)":
    st.subheader("ระบบจัดการสำหรับ Admin")
    admin_pw = st.text_input("รหัสผ่าน Admin", type="password")
    if admin_pw == "1234":
        res_data = supabase.table("bookings").select("*").eq("status", "Pending").execute()
        df_pending = pd.DataFrame(res_data.data)
        if df_pending.empty:
            st.info("ไม่มีรายการรออนุมัติ")
        else:
            st.dataframe(df_pending[['id', 'resource', 'requester', 'dept', 'start_time', 'end_time']], use_container_width=True)
            target_id = st.number_input("ใส่ ID ที่ต้องการจัดการ", step=1, min_value=1)
            c1, c2 = st.columns(2)
            if c1.button("✅ อนุมัติ"):
                supabase.table("bookings").update({"status": "Approved"}).eq("id", target_id).execute()
                st.rerun()
            if c2.button("❌ ปฏิเสธ"):
                supabase.table("bookings").update({"status": "Rejected"}).eq("id", target_id).execute()
                st.rerun()

elif choice == "📅 ตารางงาน (Real-time)":
    st.subheader("📅 ตารางงานปัจจุบันและล่วงหน้า")
    now = datetime.now().isoformat()
    res_data = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", now).order("start_time").execute()
    df = pd.DataFrame(res_data.data)
    if df.empty:
        st.info("ขณะนี้ไม่มีรายการจอง")
    else:
        df['start_time'] = pd.to_datetime(df['start_time']).dt.strftime('%d/%m/%Y %H:%M')
        df['end_time'] = pd.to_datetime(df['end_time']).dt.strftime('%d/%m/%Y %H:%M')
        st.dataframe(df[['resource', 'start_time', 'end_time', 'requester', 'purpose', 'destination']], use_container_width=True)
