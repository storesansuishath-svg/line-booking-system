from fastapi import FastAPI, Request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FlexSendMessage
import json
import os

app = FastAPI()

# --- 1. ตั้งค่า TOKEN (ใส่รหัสของคุณ) ---
LINE_ACCESS_TOKEN = "ใส่ Access Token ของคุณ"
LINE_SECRET = "ใส่ Channel Secret ของคุณ"

# --- 2. รายชื่อ Admin 5 คน (ให้ใส่ User ID ของแต่ละคน) ---
ADMIN_IDS = [
    "Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx1",
    "Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx2",
    "Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx3",
    "Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx4",
    "Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx5"
]

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_SECRET)

# ฟังก์ชันโหลดหน้าตาการ์ดเมนู
def send_flex_menu(reply_token):
    try:
        with open("main_menu.json", "r", encoding="utf-8") as f:
            flex_content = json.load(f)
        line_bot_api.reply_message(
            reply_token,
            FlexSendMessage(alt_text="เมนูหลักระบบจอง", contents=flex_content)
        )
    except Exception as e:
        line_bot_api.reply_message(reply_token, TextSendMessage(text="Error loading menu"))

@app.post("/callback")
async def callback(request: Request):
    signature = request.headers.get('X-Line-Signature')
    body = await request.body()
    handler.handle(body.decode('utf-8'), signature)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    user_id = event.source.user_id

    # คำสั่งหลัก: หน้าหลัก, ทัก, สวัสดี
    if text in ["หน้าหลัก", "ทัก", "สวัสดี"]:
        send_flex_menu(event.reply_token)

    # คำสั่ง: จอง
    elif text == "จอง":
        url = "https://office-booking-system-hll8ub77ixfgmj2s4slbu4.streamlit.app/"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"📝 กดเพื่อทำการจองได้เลยครับ:\n{url}"))

    # คำสั่ง: ดู
    elif text == "ดู":
        reply = "🔍 เลือกรายการที่ต้องการดู:\n1. ตารางรถ\n2. ตารางห้องประชุม\n3. รายการอนุมัติ/ไม่อนุมัติ"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    # คำสั่ง: อนุมัติ/ไม่อนุมัติ (เช็ค Admin 5 คน)
    elif text == "อนุมัติ/ไม่อนุมัติ":
        if user_id in ADMIN_IDS:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🔑 เข้าสู่ระบบแอดมิน: กำลังดึงรายการที่รออนุมัติ..."))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ เฉพาะแอดมิน 5 ท่านที่ได้รับอนุญาตเท่านั้นครับ"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
