from fastapi import FastAPI, Request, HTTPException
from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, FlexSendMessage,
    QuickReply, QuickReplyButton, MessageAction, PostbackEvent
)
from supabase import create_client
from datetime import datetime, timedelta
from urllib.parse import parse_qsl
import os
import re

app = FastAPI()

# --- 1. ตั้งค่า SUPABASE ---
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://qejqynbxdflwebzzwfzu.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
if not SUPABASE_KEY:
    raise RuntimeError("Missing SUPABASE_KEY. Set it in Render Environment settings.")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 2. ดึงค่าตั้งค่าจากฐานข้อมูล ---
# Fallback ชั่วคราวกรณีฐานข้อมูลยังไม่ได้ตังค่า
LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN", "")
LINE_SECRET = os.getenv("LINE_SECRET", "")
GROUP_ID = os.getenv("GROUP_ID", "")

try:
    set_res = supabase.table("app_settings").select("*").eq("id", 1).execute()
    if set_res.data:
        # Render environment values take priority; database values remain a fallback.
        LINE_ACCESS_TOKEN = LINE_ACCESS_TOKEN or set_res.data[0]['line_token']
        LINE_SECRET = LINE_SECRET or set_res.data[0]['line_secret']
        GROUP_ID = GROUP_ID or set_res.data[0]['group_id']
except Exception as e:
    print(f"Database settings load error: {e}")

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_SECRET)

@app.get("/")
async def home():
    return {"status": "Online", "message": "Sansuisha Booking System is Ready"}

ADMIN_IDS = ["Ub5588daf37957fe7625abce16bd8bb8e","U39cfc5182354b7fe5174f181983e4d1a","U7b5850883e4b9b1ca2b172b164ceaf56","Ub9bbccb167730a5b2a0908ed6b20e8ec"]

# รถชื่อแตกต่างกันแต่เป็นรถคันเดียวกัน ต้องใช้คิวร่วมกัน
RESOURCE_CONFLICT_GROUPS = {
    "MG": ["MG", "MG (เนก)"],
    "MG (เนก)": ["MG", "MG (เนก)"],
}

def get_conflict_resources(resource):
    resource_name = str(resource).strip()
    return RESOURCE_CONFLICT_GROUPS.get(resource_name, [resource_name])

def parse_booking_datetime(value):
    value_text = str(value).strip()
    if value_text.endswith("Z"):
        value_text = f"{value_text[:-1]}+00:00"
    return datetime.fromisoformat(value_text).replace(tzinfo=None)

def check_booking_conflict(resource, start_time_iso, end_time_iso, exclude_booking_id=None):
    conflict_resources = get_conflict_resources(resource)
    result = supabase.table("bookings").select("*").in_("resource", conflict_resources).in_("status", ["Approved", "Pending"]).execute()
    new_start = parse_booking_datetime(start_time_iso)
    new_end = parse_booking_datetime(end_time_iso)

    for item in result.data or []:
        if exclude_booking_id is not None and str(item.get("id")) == str(exclude_booking_id):
            continue
        existing_start = parse_booking_datetime(item["start_time"])
        existing_end = parse_booking_datetime(item["end_time"])
        if new_start < existing_end and new_end > existing_start:
            return True, item.get("requester", "-"), item.get("status", "-")
    return False, None, None

def extract_google_maps_url(value):
    """Return a safe Google Maps URL from a destination field, if one exists."""
    for url in re.findall(r"https?://[^\s<>()]+", str(value or "")):
        url = url.rstrip(".,;:!?)]}")
        host = url.lower()
        if "maps.app.goo.gl" in host or "google.com/maps" in host or "maps.google.com" in host:
            return url
    return None

def create_schedule_flex(title, data_rows, color="#0D47A1"):
    if not data_rows:
        return TextSendMessage(text=f"✅ ไม่มีรายการจองสำหรับ {title} ในขณะนี้ครับ")
    contents = [
        {"type": "text", "text": title, "weight": "bold", "size": "xl", "color": color},
        {"type": "separator", "margin": "md"}
    ]
    for i, row in enumerate(data_rows):
        try:
            t_start = datetime.fromisoformat(row['start_time']).strftime('%H:%M')
            t_end = datetime.fromisoformat(row['end_time']).strftime('%H:%M')
            date_str = datetime.fromisoformat(row['start_time']).strftime('%d/%m')
        except: t_start, t_end, date_str = "-", "-", "-"
        
        contents.append({
            "type": "box", "layout": "vertical", "margin": "md",
            "contents": [
                {"type": "text", "text": f"{i+1}. {row['resource']}", "weight": "bold", "color": "#333333"},
                {"type": "text", "text": f"📅 {date_str} | ⏰ {t_start}-{t_end}", "size": "sm", "color": color},
                {"type": "text", "text": f"👤 {row['requester']} ({row.get('dept', '-')})", "size": "xs", "color": "#666666"},
                {"type": "text", "text": f"📍 ปลายทาง: {row.get('destination', '-')}", "size": "xs", "color": "#666666", "wrap": True},
                {"type": "text", "text": f"📝 {row.get('purpose', '-')}", "size": "xs", "color": "#666666", "wrap": True}
            ]
        })
        map_url = extract_google_maps_url(row.get('destination', ''))
        if map_url:
            contents.append({
                "type": "button", "style": "link", "height": "sm", "margin": "none",
                "action": {
                    "type": "uri", "label": "🗺️ เปิด Google Maps", "uri": map_url
                }
            })
        contents.append({"type": "separator", "margin": "sm"})
    return FlexSendMessage(alt_text=f"ตาราง {title}", contents={"type": "bubble", "body": {"type": "box", "layout": "vertical", "contents": contents}})

def create_approval_flex(booking_id, data):
    user_name = data.get('name', '-')
    return FlexSendMessage(
        alt_text="มีคำขอจองใหม่",
        contents={
            "type": "bubble",
            "body": {
                "type": "box", "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "🔔 คำขอจองใหม่", "weight": "bold", "color": "#E65100", "size": "lg"},
                    {"type": "text", "text": f"ID: {booking_id}", "size": "xs", "color": "#aaaaaa"},
                    {"type": "separator", "margin": "md"},
                    {"type": "text", "text": data.get('resource', '-'), "weight": "bold", "size": "xl", "margin": "md"},
                    {"type": "text", "text": f"👤 {user_name} ({data.get('dept', '-')})", "size": "sm"},
                    {"type": "text", "text": f"📅 {data.get('date', '-')} - {data.get('end_date', '-')}", "size": "sm", "color": "#1E88E5"},
                    {"type": "text", "text": f"📍 ปลายทาง: {data.get('destination', '-')}", "size": "sm", "color": "#666666"},
                    {"type": "text", "text": f"📝 วัตถุประสงค์: {data.get('purpose', '-')}", "size": "sm", "wrap": True}
                ]
            },
            "footer": {
                "type": "box", "layout": "horizontal", "spacing": "sm",
                "contents": [
                    {"type": "button", "style": "primary", "color": "#2E7D32", "action": {"type": "postback", "label": "อนุมัติ", "data": f"action=approve&id={booking_id}&user={user_name}"}},
                    {"type": "button", "style": "primary", "color": "#C62828", "action": {"type": "postback", "label": "ปฏิเสธ", "data": f"action=reject&id={booking_id}&user={user_name}"}}
                ]
            }
        }
    )

@app.post("/callback")
async def callback(request: Request):
    signature = request.headers.get('X-Line-Signature')
    body = await request.body()
    try: handler.handle(body.decode('utf-8'), signature)
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    quick_menu = QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="🚗 รถ (3วัน)", text="ดูตารางรถ")),
        QuickReplyButton(action=MessageAction(label="🏢 ห้อง (3วัน)", text="ดูตารางห้อง")),
        QuickReplyButton(action=MessageAction(label="🚗 รถ (ทั้งหมด)", text="ดูตารางรถทั้งหมด")),
        QuickReplyButton(action=MessageAction(label="🏢 ห้อง (ทั้งหมด)", text="ดูตารางห้องทั้งหมด")),
        QuickReplyButton(action=MessageAction(label="👔 ผู้บริหาร", text="ผู้บริหาร")),
        QuickReplyButton(action=MessageAction(label="📝 จองใหม่", text="จอง")),
        QuickReplyButton(action=MessageAction(label="⏳ รออนุมัติ", text="รออนุมัติ")),
        QuickReplyButton(action=MessageAction(label="⭐ ประเมิน", text="ประเมิน"))
    ])

    if text in ["ดู", "เมนู", "สวัสดี", "ทัก", "หน้าหลัก"]:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="เลือกรายการที่ต้องการครับ 👇", quick_reply=quick_menu))

    # ดึงค่ารถและห้องจากฐานข้อมูลแบบ Real-time เวลาผู้ใช้กดเรียกดู
    try:
        db_sets = supabase.table("app_settings").select("car_list, room_list").eq("id", 1).execute().data[0]
        SYS_CARS = [x.strip() for x in db_sets['car_list'].split(',')]
        SYS_ROOMS = [x.strip() for x in db_sets['room_list'].split(',')]
    except:
        SYS_CARS = ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG", "MG (เนก)"]
        SYS_ROOMS = ["ห้องชั้น 1 (ห้องใหญ่)", "ห้องชั้น 2", "ห้อง VIP", "ห้องชั้นลอย", "ห้อง Production"]

    now = datetime.now()
    now_iso = now.isoformat()
    three_days_later = (now + timedelta(days=3)).isoformat() 

    if text == "ดูตารางรถ":
        res = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", now_iso).lte("start_time", three_days_later).in_("resource", SYS_CARS).order("start_time").execute()
        line_bot_api.reply_message(event.reply_token, create_schedule_flex("ตารางรถ (3 วัน)", res.data, "#1E88E5"))
        
    elif text == "ดูตารางห้อง":
        res = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", now_iso).lte("start_time", three_days_later).in_("resource", SYS_ROOMS).order("start_time").execute()
        line_bot_api.reply_message(event.reply_token, create_schedule_flex("ตารางห้อง (3 วัน)", res.data, "#43A047"))

    elif text == "ดูตารางรถทั้งหมด":
        res = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", now_iso).in_("resource", SYS_CARS).order("start_time").execute()
        line_bot_api.reply_message(event.reply_token, create_schedule_flex("ตารางรถ (ทั้งหมด)", res.data, "#1E88E5"))
        
    elif text == "ผู้บริหาร":
        res = supabase.table("bookings").select("*").eq("status", "Approved").eq("is_executive_booking", True).gt("end_time", now_iso).in_("resource", SYS_CARS).order("start_time").execute()
        line_bot_api.reply_message(event.reply_token, create_schedule_flex("ตารางผู้บริหาร", res.data, "#7B1FA2"))

    elif text == "ดูตารางห้องทั้งหมด":
        res = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", now_iso).in_("resource", SYS_ROOMS).order("start_time").execute()
        line_bot_api.reply_message(event.reply_token, create_schedule_flex("ตารางห้อง (ทั้งหมด)", res.data, "#43A047"))

    elif text == "จอง":
        url = "https://office-booking-system-hll8ub77ixfgmj2s4slbu4.streamlit.app/"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"กดลิงก์เพื่อจองครับ:\n{url}", quick_reply=quick_menu))
        
    elif text == "ประเมิน":
        url = "https://office-booking-system-hll8ub77ixfgmj2s4slbu4.streamlit.app/"
        msg = f"⭐ การประเมินทำผ่านระบบเว็บครับ\nกดลิงก์ด้านล่าง แล้วเลือกเมนูซ้ายมือ '⭐ ประเมินการใช้งาน' ได้เลยครับ:\n{url}"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg, quick_reply=quick_menu))

    elif text == "เช็ค ID":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"ID ของคุณ: {event.source.user_id}"))

    elif text == "รออนุมัติ":
        if event.source.user_id in ADMIN_IDS:
            res = supabase.table("bookings").select("*").eq("status", "Pending").execute()
            if not res.data: line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ ไม่มีรายการรออนุมัติครับ", quick_reply=quick_menu))
            else: line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"มี {len(res.data)} รายการรออนุมัติครับ", quick_reply=quick_menu))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🚫 สำหรับ Admin เท่านั้นครับ", quick_reply=quick_menu))

@handler.add(PostbackEvent)
def handle_postback(event):
    if event.source.user_id not in ADMIN_IDS:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🚫 ไม่มีสิทธิ์ครับ"))
        return
    data = dict(parse_qsl(event.postback.data))
    action, booking_id, user_name = data.get('action'), data.get('id'), data.get('user')
    if action and booking_id:
        try:
            if action == "approve":
                booking_result = supabase.table("bookings").select("*").eq("id", booking_id).execute()
                if not booking_result.data:
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ ไม่พบรายการจองนี้ อาจถูกลบไปแล้ว"))
                    return

                booking = booking_result.data[0]
                requester = booking.get("requester", user_name or "-")
                if booking.get("status") == "Approved":
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"ℹ️ รายการของคุณ {requester} อนุมัติไปแล้ว"))
                    return
                if booking.get("status") != "Pending":
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"❌ รายการของคุณ {requester} ไม่ได้อยู่ในสถานะรออนุมัติ"))
                    return

                is_conflict, conflict_user, conflict_status = check_booking_conflict(
                    booking["resource"], booking["start_time"], booking["end_time"], exclude_booking_id=booking_id
                )
                if is_conflict:
                    conflict_label = "ถูกจองแล้ว" if conflict_status == "Approved" else "มีรายการอื่นรออนุมัติ"
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text=f"❌ อนุมัติไม่ได้ คิว {booking['resource']} ชนกัน: {conflict_label} โดยคุณ {conflict_user}")
                    )
                    return

                supabase.table("bookings").update({"status": "Approved"}).eq("id", booking_id).execute()
                msg_text = f"✅ อนุมัติคุณ {requester} เรียบร้อย"
            elif action == "reject":
                supabase.table("bookings").update({"status": "Rejected"}).eq("id", booking_id).execute()
                msg_text = f"❌ ปฏิเสธคุณ {user_name} แล้ว"
            else:
                msg_text = "❌ คำสั่งไม่ถูกต้อง"

            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg_text))
        except Exception as e:
            print(f"Approval error: {e}")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ ตรวจสอบหรือบันทึกการอนุมัติไม่สำเร็จ กรุณาลองใหม่"))

@app.post("/notify")
async def notify_booking(request: Request):
    data = await request.json()
    status = data.get("status", "Pending")
    
    # ดึงค่า Group ID ล่าสุดมาแจ้งเตือนเสมอ
    try: notify_group_id = supabase.table("app_settings").select("group_id").eq("id", 1).execute().data[0]['group_id']
    except: notify_group_id = GROUP_ID
    
    if status == "Approved":
        msg = f"✅ อนุมัติการจองแล้ว\n----------------------\n🚗/🏢 รายการ: {data.get('resource')}\n👤 ผู้จอง: {data.get('name')} ({data.get('dept')})\n📅 เวลา: {data.get('date')}\n📍 ปลายทาง: {data.get('destination', '-')}\n🎯 วัตถุประสงค์: {data.get('purpose', '-')}"
        line_bot_api.push_message(notify_group_id, TextSendMessage(text=msg))
    else:
        line_bot_api.push_message(notify_group_id, create_approval_flex(data.get("id"), data))
    return {"status": "success"}

@app.get("/check-reminders")
def check_reminders():
    try: notify_group_id = supabase.table("app_settings").select("group_id").eq("id", 1).execute().data[0]['group_id']
    except: notify_group_id = GROUP_ID

    now = datetime.now()
    t_min = (now + timedelta(minutes=14)).isoformat()
    t_max = (now + timedelta(minutes=16)).isoformat()
    res = supabase.table("bookings").select("*").eq("status", "Approved").eq("reminder_sent", False).gte("start_time", t_min).lte("start_time", t_max).execute()
    if res.data:
        for item in res.data:
            msg = f"⏰ แจ้งเตือนล่วงหน้า 15 นาที!\n\n🚗/🏢: {item['resource']}\n👤 ผู้จอง: {item['requester']}"
            line_bot_api.push_message(notify_group_id, TextSendMessage(text=msg))
            supabase.table("bookings").update({"reminder_sent": True}).eq("id", item['id']).execute()
    return {"status": "checked"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
