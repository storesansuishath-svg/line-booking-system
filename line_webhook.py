from fastapi import FastAPI, Request, BackgroundTasks
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FlexSendMessage, PostbackEvent
from supabase import create_client
import uvicorn
import json

app = FastAPI()

# --- 1. ตั้งค่าการเชื่อมต่อ (เอามาจากโค้ดเดิมของคุณ) ---
SUPABASE_URL = "https://qejqynbxdflwebzzwfzu.supabase.co"
SUPABASE_KEY = "sb_publishable_hvNQEPvuEAlXfVeCzpy7Ug_kzvihQqq"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 2. ตั้งค่า LINE (ต้องเอาจาก LINE Developers) ---
LINE_ACCESS_TOKEN = "ใส่ Access Token ยาวๆ ของคุณที่นี่"
LINE_SECRET = "ใส่ Channel Secret ของคุณที่นี่"

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_SECRET)

@app.post("/callback")
async def callback(request: Request):
    signature = request.headers.get('X-Line-Signature')
    body = await request.body()
    handler.handle(body.decode('utf-8'), signature)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    msg = event.message.text
    user_id = event.source.user_id

    # --- คีย์เวิร์ด: เช็ค หรือ ดู ---
    if msg in ["เช็ค", "ดู"]:
        reply_msg = "🔍 เลือกสิ่งที่ต้องการเช็คครับ:\n- ดูรถ\n- ดูห้องประชุม"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_msg))

    # --- คีย์เวิร์ด: ดูรถ ---
    elif msg == "ดูรถ":
        res = supabase.table("bookings").select("*").eq("status", "Approved").execute()
        car_list = ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG ขับเอง"]
        cars = [item for item in res.data if item['resource'] in car_list]
        
        if not cars:
            reply = "🚗 ตอนนี้ไม่มีรถถูกจองครับ (ว่างทุกคัน)"
        else:
            reply = "📋 รายการจองรถ:\n" + "\n".join([f"• {c['resource']} ({c['requester']})" for c in cars])
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

    # --- คีย์เวิร์ด: จอง ---
    elif msg == "จอง":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text="📝 กดจองที่หน้าเว็บนี้ได้เลยครับ:\nhttps://office-booking-system-hll8ub77ixfgmj2s4slbu4.streamlit.app/"
        ))

    # --- คีย์เวิร์ด: อนุมัติ (โชว์รายการที่ค้างอยู่) ---
    elif msg == "อนุมัติ":
        res = supabase.table("bookings").select("*").eq("status", "Pending").execute()
        if not res.data:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ ไม่มีรายการค้างอนุมัติครับ"))
        else:
            # ส่งรายการแรกที่ค้างอยู่มาให้กดปุ่ม (ตัวอย่าง)
            item = res.data[0]
            line_bot_api.reply_message(event.reply_token, TextSendMessage(
                text=f"📌 รออนุมัติ: {item['resource']}\nโดย: {item['requester']}\n(พิมพ์ 'ยืนยัน {item['id']}' เพื่ออนุมัติ)"
            ))

    # --- คีย์เวิร์ด: ยืนยัน [ID] ---
    elif msg.startswith("ยืนยัน "):
        booking_id = msg.split(" ")[1]
        supabase.table("bookings").update({"status": "Approved"}).eq("id", booking_id).execute()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"✅ อนุมัติหมายเลข {booking_id} เรียบร้อย!"))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)