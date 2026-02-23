from fastapi import FastAPI, Request, HTTPException
from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, FlexSendMessage,
    QuickReply, QuickReplyButton, MessageAction, PostbackEvent, PostbackAction
)
from supabase import create_client
from datetime import datetime, timedelta
from urllib.parse import parse_qsl
import os

app = FastAPI()

# --- 1. ตั้งค่า LINE & SUPABASE ---
LINE_ACCESS_TOKEN = "hMc9myYeQVze7rzukNnOiGyMBtiFwDZaqRRzhci6iRAaCKAPorOkrjy3iV8HZ3ittnQcBknOd9Ou43Tx+9QHYVyQdPyUCpq4eWpr2B9XmKg2I6ABSl6QSWmL63MwEWbaikVKqpZjLZLm3/gEyXG3MAdB04t89/1O/w1cDnyilFU="
LINE_SECRET = "1a5c831d35b68b8b107eadaa179dee35"
# ID กลุ่มที่คุณต้องการให้แจ้งเตือน
GROUP_ID = "Cad74a32468ca40051bd7071a6064660d"

SUPABASE_URL = "https://qejqynbxdflwebzzwfzu.supabase.co"
# ⚠️ แนะนำเปลี่ยนเป็น service_role key (ขึ้นต้นด้วย ey...) เพื่อให้ Bot มีสิทธิ์แก้ไขข้อมูลในฐานข้อมูลได้ครับ
SUPABASE_KEY = "sb_publishable_hvNQEPvuEAlXfVeCzpy7Ug_kzvihQqq"

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_SECRET)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 2. รายชื่อ Admin ---
ADMIN_IDS = ["Ub5588daf37957fe7625abce16bd8bb8e","U39cfc5182354b7fe5174f181983e4d1a","U7b5850883e4b9b1ca2b172b164ceaf56","Ub9bbccb167730a5b2a0908ed6b20e8ec"]

# --- 3. ฟังก์ชันสร้างตารางสรุป ---
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
        contents.append({"type": "separator", "margin": "sm"})
    
    return FlexSendMessage(
        alt_text=f"ตาราง {title}", 
        contents={"type": "bubble", "body": {"type": "box", "layout": "vertical", "contents": contents}}
    )

# --- 4. ฟังก์ชันสร้างปุ่มอนุมัติ (แก้ไข SyntaxError แล้ว) ---
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
                "type": "box",
                "layout": "horizontal",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button", "style": "primary", "color": "#2E7D32", 
                        "action": {"type": "postback", "label": "อนุมัติ", "data": f"action=approve&id={booking_id}&user={user_name}"}
                    },
                    {
                        "type": "button", "style": "primary", "color": "#C62828", 
                        "action": {"type": "postback", "label": "ปฏิเสธ", "data": f"action=reject&id={booking_id}&user={user_name}"}
                    }
                ]
            }
        }
    )

# --- 5. Webhook Handler ---
@app.post("/callback")
async def callback(request: Request):
    signature = request.headers.get('X-Line-Signature')
    body = await request.body()
    try:
        handler.handle(body.decode('utf-8'), signature)
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    return 'OK'

# --- 6. จัดการข้อความ Text ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    
    quick_menu = QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="🚗 ตารางรถ", text="ดูตารางรถ")),
        QuickReplyButton(action=MessageAction(label="🏢 ตารางห้อง", text="ดูตารางห้อง")),
        QuickReplyButton(action=MessageAction(label="📝 จองใหม่", text="จอง")),
        QuickReplyButton(action=MessageAction(label="⏳ รออนุมัติ", text="รออนุมัติ"))
    ])

    if text in ["ดู", "เมนู", "สวัสดี", "ทัก", "หน้าหลัก"]:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="เลือกรายการที่ต้องการครับ 👇", quick_reply=quick_menu))

    elif text == "ดูตารางรถ":
        now = datetime.now().isoformat()
        car_list = ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG"]
        res = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", now).in_("resource", car_list).order("start_time").execute()
        line_bot_api.reply_message(event.reply_token, create_schedule_flex("ตารางรถ", res.data, "#1E88E5"))

    elif text == "ดูตารางห้อง":
        now = datetime.now().isoformat()
        room_list = ["ห้องชั้น 1 (ห้องใหญ่)", "ห้องชั้น 2", "ห้อง VIP", "ห้องชั้นลอย", "ห้อง Production"]
        res = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", now).in_("resource", room_list).order("start_time").execute()
        line_bot_api.reply_message(event.reply_token, create_schedule_flex("ตารางห้อง", res.data, "#43A047"))

    elif text == "จอง":
        url = "https://office-booking-system-hll8ub77ixfgmj2s4slbu4.streamlit.app/"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"กดลิงก์เพื่อจองครับ:\n{url}", quick_reply=quick_menu))

    elif text == "เช็ค ID":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"ID ของคุณ: {event.source.user_id}"))

    elif text == "รออนุมัติ":
        if event.source.user_id in ADMIN_IDS:
            res = supabase.table("bookings").select("*").eq("status", "Pending").execute()
            if not res.data:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ ไม่มีรายการรออนุมัติครับ", quick_reply=quick_menu))
            else:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"มี {len(res.data)} รายการรออนุมัติครับ", quick_reply=quick_menu))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🚫 สำหรับ Admin เท่านั้นครับ", quick_reply=quick_menu))

# --- 7. จัดการการกดปุ่ม (Postback) ---
@handler.add(PostbackEvent)
def handle_postback(event):
    if event.source.user_id not in ADMIN_IDS:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🚫 ไม่มีสิทธิ์ครับ"))
        return

    data = dict(parse_qsl(event.postback.data))
    action, booking_id, user_name = data.get('action'), data.get('id'), data.get('user')

    if action and booking_id:
        status = "Approved" if action == "approve" else "Rejected"
        supabase.table("bookings").update({"status": status}).eq("id", booking_id).execute()
        
        msg_text = f"✅ อนุมัติคุณ {user_name} เรียบร้อย" if action == "approve" else f"❌ ปฏิเสธคุณ {user_name} แล้ว"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg_text))

        if action == "approve":
            now_iso = datetime.now().isoformat()
            res = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", now_iso).order("start_time").execute()
            line_bot_api.push_message(GROUP_ID, [
                TextSendMessage(text="📢 รายการได้รับการอนุมัติ! ตารางงานล่าสุดมีดังนี้:"),
                create_schedule_flex("📅 ตารางการใช้งานปัจจุบัน", res.data, "#2E7D32")
            ])

# --- 8. รับ Notify จาก Streamlit (แก้ไขใหม่เพื่อให้รองรับการอนุมัติ) ---
@app.post("/notify")
async def notify_booking(request: Request):
    data = await request.json()
    status = data.get("status", "Pending")
    
    # ถ้าสถานะเป็น "Approved" (ส่งมาจากตอนพี่กดปุ่มอนุมัติในเว็บ)
    if status == "Approved":
        msg = f"✅ อนุมัติการจองแล้ว\n" \
              f"----------------------\n" \
              f"🚗 รายการ: {data.get('resource')}\n" \
              f"👤 ผู้จอง: {data.get('name')} ({data.get('dept')})\n" \
              f"📅 เวลา: {data.get('date')}\n" \
              f"📍 ปลายทาง: {data.get('destination', '-')}\n" \
              f"🎯 วัตถุประสงค์: {data.get('purpose', '-')}"
        
        # ✅ ส่งแจ้งเตือนแบบ Push เข้ากลุ่มทันที
        line_bot_api.push_message(GROUP_ID, TextSendMessage(text=msg))
    
    else:
        # 📝 ถ้าเป็นรายการจองใหม่ (สถานะ Pending) ให้ส่งแบบ "ปุ่มกดอนุมัติ" เหมือนเดิม
        line_bot_api.push_message(GROUP_ID, create_approval_flex(data.get("id"), data))
        
    return {"status": "success"}
# --- 9. แจ้งเตือนล่วงหน้า 15 นาที ---
@app.get("/check-reminders")
def check_reminders():
    now = datetime.now()
    t_min = (now + timedelta(minutes=14)).isoformat()
    t_max = (now + timedelta(minutes=16)).isoformat()
    res = supabase.table("bookings").select("*").eq("status", "Approved").eq("reminder_sent", False).gte("start_time", t_min).lte("start_time", t_max).execute()
    if res.data:
        for item in res.data:
            msg = f"⏰ แจ้งเตือนล่วงหน้า 15 นาที!\n\n🚗/🏢: {item['resource']}\n👤 ผู้จอง: {item['requester']}"
            line_bot_api.push_message(GROUP_ID, TextSendMessage(text=msg))
            supabase.table("bookings").update({"reminder_sent": True}).eq("id", item['id']).execute()
    return {"status": "checked"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)




