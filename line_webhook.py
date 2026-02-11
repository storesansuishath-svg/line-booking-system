from fastapi import FastAPI, Request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FlexSendMessage
import json
import os

app = FastAPI()

# --- 1. ตั้งค่า TOKEN ---
# (ตรวจสอบให้แน่ใจว่ารหัสเหล่านี้ตรงกับใน LINE Developers ของคุณ)
LINE_ACCESS_TOKEN = "ILJVHrD24hZCe/stNR6wKxglGerAEtefHwB0HlDzq2vx5zc+hx0JoS2fDQe6BFzsOCwMD47HldTFuCBve9JRa1uAlAuq24sK2Iv/C5T/+p8Vkh1ppr3MKOb0ghP9MGO1kVj4UmgSzdyrI8P0vKHprgdB04t89/1O/w1cDnyilFU="
LINE_SECRET = "92765784656c2d17a334add0233d9e2f"

# --- 2. รายชื่อ Admin ---
# ใส่ User ID (U...) ที่ได้จาก Logs ของแอดมินแต่ละคน
ADMIN_IDS = [
    "Ub5588daf37957fe7625abce16bd8bb8e",
    "Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx2",
    "Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx3",
    "Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx4",
    "Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx5"
]

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_SECRET)

# --- 3. ฟังก์ชันส่ง Flex Menu (เมนู 4 ช่อง) ---
def send_flex_menu(reply_token):
    try:
        with open("main_menu.json", "r", encoding="utf-8") as f:
            flex_content = json.load(f)
        line_bot_api.reply_message(
            reply_token,
            FlexSendMessage(alt_text="เมนูหลักระบบจอง", contents=flex_content)
        )
    except Exception as e:
        print(f"Error loading menu: {e}")
        line_bot_api.reply_message(reply_token, TextSendMessage(text="ขออภัย ไม่สามารถโหลดเมนูได้ในขณะนี้"))

# --- 4. เส้นทางรับข้อมูลจาก LINE (Webhook) ---
@app.post("/callback")
async def callback(request: Request):
    signature = request.headers.get('X-Line-Signature')
    body = await request.body()
    try:
        handler.handle(body.decode('utf-8'), signature)
    except Exception as e:
        print(f"Webhook Error: {e}")
    return 'OK'

# --- 5. จัดการข้อความที่ส่งมาจากผู้ใช้ ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    # พิมพ์ข้อมูล Event ลง Logs เพื่อหา User ID
    print(f"User Event: {event}")
    
    text = event.message.text.strip()
    user_id = event.source.user_id

    # คำสั่ง: หน้าหลัก / ทัก / สวัสดี
    if text in ["หน้าหลัก", "ทัก", "สวัสดี"]:
        send_flex_menu(event.reply_token)

    # คำสั่ง: จอง (ส่งลิงก์ไปหน้าเว็บ Streamlit)
    elif text == "จอง":
        url = "https://office-booking-system-hll8ub77ixfgmj2s4slbu4.streamlit.app/"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"📝 กดเพื่อทำการจองได้เลยครับ:\n{url}"))

    # คำสั่ง: ดู
    elif text == "ดู":
        reply = "🔍 เลือกรายการที่ต้องการดู:\n1. ตารางรถ\n2. ตารางห้องประชุม\n3. รายการอนุมัติ/ไม่อนุมัติ"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    # คำสั่ง: อนุมัติ/ไม่อนุมัติ (เช็คสิทธิ์แอดมิน)
    elif text == "อนุมัติ/ไม่อนุมัติ":
        if user_id in ADMIN_IDS:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🔑 เข้าสู่ระบบแอดมิน: กำลังดึงรายการที่รออนุมัติ..."))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ เฉพาะแอดมิน 5 ท่านที่ได้รับอนุญาตเท่านั้นครับ"))

# --- 6. เส้นทางรับแจ้งเตือนจากหน้าเว็บ Streamlit (/notify) ---
@app.post("/notify")
async def notify_booking(request: Request):
    try:
        data = await request.json()
        resource = data.get("resource", "ไม่ระบุ")
        name = data.get("name", "ไม่ระบุ")
        date = data.get("date", "ไม่ระบุ")

        # ข้อความที่จะส่งเข้า LINE
        msg = f"🔔 มีรายการจองใหม่!\n\n🔹 รายการ: {resource}\n👤 ผู้จอง: {name}\n📅 เวลาเริ่ม: {date}\n\n⚠️ กรุณาเข้าหน้าเว็บ Admin เพื่อตรวจสอบและอนุมัติครับ"

        # ส่งแบบ Broadcast หาทุกคนที่เคยทักบอท
        line_bot_api.broadcast(TextSendMessage(text=msg))
        return {"status": "success"}
    except Exception as e:
        print(f"Error in /notify: {e}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
