from fastapi import FastAPI, Request, HTTPException
from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, FlexSendMessage,
    QuickReply, QuickReplyButton, MessageAction, PostbackEvent, PostbackAction
)
from supabase import create_client
from datetime import datetime
from urllib.parse import parse_qsl
import os
import uvicorn

app = FastAPI()

# --- 1. ตั้งค่า LINE & SUPABASE ---
LINE_ACCESS_TOKEN = "ILJVHrD24hZCe/stNR6wKxglGerAEtefHwB0HlDzq2vx5zc+hx0JoS2fDQe6BFzsOCwMD47HldTFuCBve9JRa1uAlAuq24sK2Iv/C5T/+p8Vkh1ppr3MKOb0ghP9MGO1kVj4UmgSzdyrI8P0vKHprgdB04t89/1O/w1cDnyilFU="
LINE_SECRET = "92765784656c2d17a334add0233d9e2f"
SUPABASE_URL = "https://qejqynbxdflwebzzwfzu.supabase.co"
SUPABASE_KEY = "sb_publishable_hvNQEPvuEAlXfVeCzpy7Ug_kzvihQqq"

# ID กลุ่มที่ระบุมา
TARGET_GROUP_ID = "Cad74a32468ca40051bd7071a6064660d" 

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_SECRET)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# รายชื่อ Admin
ADMIN_IDS = ["Ub5588daf37957fe7625abce16bd8bb8e","U39cfc5182354b7fe5174f181983e4d1a"]

# --- 2. ฟังก์ชันช่วยส่งข้อความ 2 ทาง (Broadcast + Group Push) ---
def send_to_all_and_group(messages):
    """ส่งข้อความหาเพื่อนทุกคนและลงกลุ่มที่ระบุพร้อมกัน"""
    try:
        # ส่งหาเพื่อนทุกคน (Broadcast)
        line_bot_api.broadcast(messages)
        # ส่งลงกลุ่ม (Push)
        line_bot_api.push_message(TARGET_GROUP_ID, messages)
    except Exception as e:
        print(f"Error sending messages: {e}")

# --- 3. ฟังก์ชันสร้างตารางสวยๆ (Flex Message) ---
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
                {"type": "text", "text": f"📍 {row.get('destination', '-')}", "size": "xs", "color": "#666666"},
                {"type": "text", "text": f"📝 {row.get('purpose', '-')}", "size": "xs", "color": "#666666", "wrap": True, "margin": "xs"}
            ]
        })
        contents.append({"type": "separator", "margin": "sm"})

    return FlexSendMessage(
        alt_text=f"ตาราง {title}", 
        contents={"type": "bubble", "body": {"type": "box", "layout": "vertical", "contents": contents}}
    )

# --- 4. ฟังก์ชันสร้างปุ่มอนุมัติ (Flex Message) ---
def create_approval_flex(booking_id, data):
    flex_content = {
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
                {"type": "text", "text": f"📝 {data.get('purpose', '-')}", "size": "sm", "wrap": True, "color": "#555555"}
            ]
        },
        "footer": {
            "type": "box", "layout": "horizontal", "spacing": "sm",
            "contents": [
                {"type": "button", "style": "primary", "color": "#2E7D32", "action": PostbackAction(label="✅ อนุมัติ", data=f"action=approve&id={booking_id}&user={data.get('name')}")},
                {"type": "button", "style": "primary", "color": "#C62828", "action": PostbackAction(label="❌ ปฏิเสธ", data=f"action=reject&id={booking_id}&user={data.get('name')}")}
            ]
        }
    }
    return FlexSendMessage(alt_text="มีคำขอจองใหม่", contents=flex_content)

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
    
    if text == "เช็ค ID กลุ่ม":
        if event.source.type == 'group':
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"ID กลุ่มของคุณคือ:\n{event.source.group_id}"))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🚫 ต้องพิมพ์ใน 'กลุ่ม' เท่านั้นครับ"))
    
    elif text == "เช็ค ID":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"ID ของคุณ: {event.source.user_id}"))

# --- 7. จัดการกดปุ่ม (Postback) ---
@handler.add(PostbackEvent)
def handle_postback(event):
    if event.source.user_id not in ADMIN_IDS:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🚫 คุณไม่มีสิทธิ์ครับ"))
        return

    data = dict(parse_qsl(event.postback.data))
    action, booking_id, user_name = data.get('action'), data.get('id'), data.get('user')

    if action and booking_id:
        status = "Approved" if action == "approve" else "Rejected"
        supabase.table("bookings").update({"status": status}).eq("id", booking_id).execute()
        
        # ตอบกลับแอดมินคนกด
        msg_confirm = f"{'✅ อนุมัติ' if action == 'approve' else '❌ ปฏิเสธ'}คุณ {user_name} เรียบร้อย"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg_confirm))

        # หากเป็นการอนุมัติ ให้ส่งตารางล่าสุดหาทุกคนและลงกลุ่ม
        if action == "approve":
            now_iso = datetime.now().isoformat()
            res = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", now_iso).order("start_time").execute()
            
            latest_messages = [
                TextSendMessage(text="📢 นี่คือตารางงานล่าสุด"),
                create_schedule_flex("📅 ตารางการใช้งานปัจจุบัน", res.data, "#2E7D32")
            ]
            send_to_all_and_group(latest_messages)

# --- 8. รับ Notify จาก Streamlit ---
@app.post("/notify")
async def notify_booking(request: Request):
    data = await request.json()
    mode = data.get("mode")
    
    if mode == "all_schedule":
        now = datetime.now().isoformat()
        res = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", now).order("start_time").execute()
        
        messages = [
            TextSendMessage(text="📢 นี่คือตารางงานล่าสุด"),
            create_schedule_flex("📅 ตารางการใช้งานปัจจุบัน", res.data, "#2E7D32")
        ]
        send_to_all_and_group(messages)
    else:
        # งานใหม่รออนุมัติ ส่งปุ่มไปให้ทุกคนและลงกลุ่ม
        approval_flex = create_approval_flex(data.get("id"), data)
        send_to_all_and_group(approval_flex)
        
    return {"status": "success"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
