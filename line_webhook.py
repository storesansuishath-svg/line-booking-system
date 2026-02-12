from fastapi import FastAPI, Request, HTTPException
from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, FlexSendMessage,
    QuickReply, QuickReplyButton, MessageAction, PostbackEvent, PostbackAction
)
from supabase import create_client
from datetime import datetime
from urllib.parse import parse_qsl # ใช้แกะค่าที่ส่งมาจากปุ่ม
import json
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

# --- 2. รายชื่อ Admin (สำคัญมาก: ต้องมี User ID ของคนที่จะกดปุ่มได้) ---
ADMIN_IDS = [
    "Ub5588daf37957fe7625abce16bd8bb8e",
    # เพิ่ม ID ของ Admin คนอื่นที่นี่
]

# --- 3. สร้าง Flex Message สำหรับ "ขออนุมัติ" ---
def create_approval_flex(booking_id, data):
    # data คือ dict ข้อมูลการจองที่รับมาจาก Streamlit
    flex_content = {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "🔔 คำขอจองใหม่", "weight": "bold", "color": "#E65100"},
                {"type": "text", "text": f"ID: {booking_id}", "size": "xs", "color": "#aaaaaa"}
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": data.get('resource', '-'), "weight": "bold", "size": "xl"},
                {"type": "separator", "margin": "md"},
                {"type": "box", "layout": "vertical", "margin": "md", "contents": [
                    {"type": "text", "text": f"👤 ผู้ขอ: {data.get('name', '-')}", "size": "sm"},
                    {"type": "text", "text": f"🏢 แผนก: {data.get('dept', '-')}", "size": "sm"},
                    {"type": "text", "text": f"📅 เวลา: {data.get('date', '-')} - {data.get('end_date', '-')}", "size": "sm", "color": "#1E88E5"},
                    {"type": "text", "text": f"📝 เหตุผล: {data.get('purpose', '-')}", "size": "sm", "wrap": True, "color": "#555555"}
                ]}
            ]
        },
        "footer": {
            "type": "box",
            "layout": "horizontal",
            "spacing": "sm",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "color": "#2E7D32",
                    "action": PostbackAction(
                        label="✅ อนุมัติ",
                        data=f"action=approve&id={booking_id}&user={data.get('name')}",
                        display_text="อนุมัติครับ"
                    )
                },
                {
                    "type": "button",
                    "style": "primary",
                    "color": "#C62828",
                    "action": PostbackAction(
                        label="❌ ไม่อนุมัติ",
                        data=f"action=reject&id={booking_id}&user={data.get('name')}",
                        display_text="ไม่อนุมัติครับ"
                    )
                }
            ]
        }
    }
    return FlexSendMessage(alt_text="มีคำขอจองใหม่รออนุมัติ", contents=flex_content)

# --- 4. Webhook Handler ---
@app.post("/callback")
async def callback(request: Request):
    signature = request.headers.get('X-Line-Signature')
    body = await request.body()
    try:
        handler.handle(body.decode('utf-8'), signature)
    except Exception as e:
        print(f"Webhook Error: {e}")
    return 'OK'

# --- 5. จัดการข้อความ (Text) ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    
    # (โค้ดส่วน Quick Reply และตารางแสดงผลเดิม ใส่ไว้ตรงนี้ได้เลยครับ...)
    # เพื่อความกระชับ ผมละไว้ แต่คุณสามารถเอาโค้ดเดิมมาแปะต่อได้เลย
    
    if text == "เช็ค ID":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"User ID ของคุณคือ:\n{event.source.user_id}"))

# --- 6. จัดการการกดปุ่ม (Postback Event) ---
@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    
    # 1. เช็คสิทธิ์ Admin ก่อนเลย
    if user_id not in ADMIN_IDS:
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text="🚫 ขออภัยครับ คุณไม่มีสิทธิ์อนุมัติรายการนี้ (เฉพาะ Admin เท่านั้น)")
        )
        return

    # 2. แกะข้อมูลจากปุ่ม (data="action=approve&id=123...")
    data = dict(parse_qsl(event.postback.data))
    action = data.get('action')
    booking_id = data.get('id')
    requester_name = data.get('user')

    if not booking_id:
        return

    # 3. อัปเดตสถานะใน Supabase
    new_status = "Approved" if action == "approve" else "Rejected"
    
    try:
        supabase.table("bookings").update({"status": new_status}).eq("id", booking_id).execute()
        
        # 4. แจ้งผลกลับเข้ากลุ่ม
        if action == "approve":
            msg = f"✅ Admin อนุมัติการจองของ '{requester_name}' เรียบร้อยแล้วครับ"
        else:
            msg = f"❌ Admin ปฏิเสธการจองของ '{requester_name}' ครับ"
            
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))
        
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"⚠️ เกิดข้อผิดพลาดในการบันทึก: {e}"))


# --- 7. รับแจ้งเตือนจาก Streamlit (/notify) ---
@app.post("/notify")
async def notify_booking(request: Request):
    try:
        data = await request.json()
        booking_id = data.get("id")
        
        # สร้าง Flex Message ที่มีปุ่มกด
        flex_msg = create_approval_flex(booking_id, data)

        # ส่งเข้ากลุ่ม (Broadcast) หรือถ้าทราบ Group ID เจาะจงก็เปลี่ยนเป็น push_message ได้
        line_bot_api.broadcast(flex_msg)
        
        return {"status": "success"}
    except Exception as e:
        print(f"Notify Error: {e}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
