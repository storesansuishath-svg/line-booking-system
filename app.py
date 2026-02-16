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
LINE_ACCESS_TOKEN = "ILJVHrD24hZCe/stNR6wKxglGerAEtefHwB0HlDzq2vx5zc+hx0JoS2fDQe6BFzsOCwMD47HldTFuCBve9JRa1uAlAuq24sK2Iv/C5T/+p8Vkh1ppr3MKOb0ghP9MGO1kVj4UmgSzdyrI8P0vKHprgdB04t89/1O/w1cDnyilFU="
LINE_SECRET = "92765784656c2d17a334add0233d9e2f"
SUPABASE_URL = "https://qejqynbxdflwebzzwfzu.supabase.co"
SUPABASE_KEY = "sb_publishable_hvNQEPvuEAlXfVeCzpy7Ug_kzvihQqq"

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_SECRET)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 2. รายชื่อ Admin ---
ADMIN_IDS = ["Ub5588daf37957fe7625abce16bd8bb8e","U39cfc5182354b7fe5174f181983e4d1a"]

# --- 3. ฟังก์ชันสร้างตารางสรุป (Flex Message) ---
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
                # เพิ่มบรรทัดปลายทางตรงนี้ครับ
                {"type": "text", "text": f"📍 ปลายทาง: {row.get('destination', '-')}", "size": "xs", "color": "#666666", "wrap": True},
                {"type": "text", "text": f"📝 {row.get('purpose', '-')}", "size": "xs", "color": "#666666", "wrap": True}
            ]
        })
        contents.append({"type": "separator", "margin": "sm"})
    
    return FlexSendMessage(
        alt_text=f"ตาราง {title}", 
        contents={"type": "bubble", "body": {"type": "box", "layout": "vertical", "contents": contents}}
    )
# --- 4. ฟังก์ชันสร้างปุ่มอนุมัติ (Flex Message) ---
def create_approval_flex(booking_id, data):
    return FlexSendMessage(
        alt_text="มีคำขอจองใหม่",
        contents={
            "type": "bubble",
            "body": {
                "type": "box", "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "🔔 คำขอจองใหม่", "weight": "bold", "color": "#E65100"},
                    {"type": "text", "text": f"ID: {booking_id}", "size": "xs", "color": "#aaaaaa"},
                    {"type": "separator", "margin": "md"},
                    {"type": "text", "text": data.get('resource', '-'), "weight": "bold", "size": "lg", "margin": "md"},
                    {"type": "text", "text": f"👤 {data.get('name', '-')} ({data.get('dept', '-')})", "size": "sm"},
                    {"type": "text", "text": f"📅 {data.get('date', '-')} - {data.get('end_date', '-')}", "size": "sm", "color": "#1E88E5"},
                    # เพิ่มปลายทาง
                    {"type": "text", "text": f"📍 ปลายทาง: {data.get('destination', '-')}", "size": "sm", "color": "#666666"},
                    {"type": "text", "text": f"📝 {data.get('purpose', '-')}", "size": "sm", "wrap": True}
                ]
            },
            "footer": { ... } # ส่วนปุ่มกดคงเดิม
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
        car_list = ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG ขับเอง"]
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

    # --- ส่วนที่เพิ่มใหม่: เช็ค ID กลุ่ม ---
    elif text == "เช็ค ID กลุ่ม":
        if event.source.type == 'group':
            group_id = event.source.group_id
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"ID กลุ่มของคุณคือ:\n{group_id}"))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🚫 ต้องพิมพ์ใน 'กลุ่ม' เท่านั้นครับ"))

    elif text == "รออนุมัติ":
        if event.source.user_id in ADMIN_IDS:
            res = supabase.table("bookings").select("*").eq("status", "Pending").execute()
            if not res.data:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ ไม่มีรายการรออนุมัติครับ", quick_reply=quick_menu))
            else:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"มี {len(res.data)} รายการรออนุมัติครับ", quick_reply=quick_menu))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🚫 สำหรับ Admin เท่านั้นครับ", quick_reply=quick_menu))

# --- 7. จัดการกดปุ่ม (Postback) ---
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

        # ส่งตารางล่าสุดหลังอนุมัติ (ใช้ broadcast ไปก่อนจนกว่าจะได้ ID กลุ่ม)
        if action == "approve":
            now_iso = datetime.now().isoformat()
            res = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", now_iso).order("start_time").execute()
            line_bot_api.broadcast([
                TextSendMessage(text="📢 นี่คือตารางงานล่าสุด"),
                create_schedule_flex("📅 ตารางการใช้งานปัจจุบัน", res.data, "#2E7D32")
            ])

# --- 8. รับ Notify จาก Streamlit ---
@app.post("/notify")
async def notify_booking(request: Request):
    data = await request.json()
    mode = data.get("mode")
    if mode == "all_schedule":
        now = datetime.now().isoformat()
        res = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", now).order("start_time").execute()
        line_bot_api.broadcast([
            TextSendMessage(text="📢 นี่คือตารางงานล่าสุด"),
            create_schedule_flex("📅 ตารางการใช้งานปัจจุบัน", res.data, "#2E7D32")
        ])
    else:
        line_bot_api.broadcast(create_approval_flex(data.get("id"), data))
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
            line_bot_api.broadcast(TextSendMessage(text=msg))
            supabase.table("bookings").update({"reminder_sent": True}).eq("id", item['id']).execute()
    return {"status": "checked"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
