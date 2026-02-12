from fastapi import FastAPI, Request
from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, FlexSendMessage,
    QuickReply, QuickReplyButton, MessageAction
)
from supabase import create_client
from datetime import datetime
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

# --- 2. รายชื่อ Admin ---
ADMIN_IDS = [
    "Ub5588daf37957fe7625abce16bd8bb8e",
    # เพิ่ม ID อื่นๆ ที่นี่
]

# --- 3. ฟังก์ชันสร้างตาราง Flex Message (ให้เหมือนหน้าเว็บ) ---
def create_schedule_flex(title, data_rows, color="#0D47A1"):
    """
    สร้าง Flex Message แบบตาราง
    data_rows คือ list ของ dict ที่มี keys: resource, start, end, name, purpose, dest
    """
    if not data_rows:
        return TextSendMessage(text=f"✅ ไม่มีรายการจองสำหรับ {title} ในขณะนี้ครับ")

    # ส่วนหัวตาราง (Header)
    contents = [
        {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": title, "weight": "bold", "size": "xl", "color": color},
                {"type": "text", "text": "รายการจองที่อนุมัติแล้ว (Real-time)", "size": "xs", "color": "#aaaaaa"}
            ]
        },
        {"type": "separator", "margin": "md"}
    ]

    # วนลูปสร้างแถวข้อมูล (Rows)
    for i, row in enumerate(data_rows):
        # จัดรูปแบบเวลาให้อ่านง่าย
        try:
            t_start = datetime.fromisoformat(row['start_time']).strftime('%H:%M')
            t_end = datetime.fromisoformat(row['end_time']).strftime('%H:%M')
            date_str = datetime.fromisoformat(row['start_time']).strftime('%d/%m')
        except:
            t_start, t_end, date_str = "-", "-", "-"

        row_box = {
            "type": "box",
            "layout": "vertical",
            "margin": "md",
            "contents": [
                # บรรทัด 1: ชื่อทรัพยากร + เวลา (เน้นตัวหนา)
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": f"{i+1}. {row['resource']}", "weight": "bold", "size": "sm", "flex": 2, "color": "#333333"},
                        {"type": "text", "text": f"📅 {date_str} | ⏰ {t_start}-{t_end}", "size": "xs", "align": "end", "flex": 1, "color": color}
                    ]
                },
                # บรรทัด 2: ผู้จอง + ปลายทาง
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": f"👤 {row['requester']}", "size": "xs", "color": "#666666", "flex": 1},
                        {"type": "text", "text": f"📍 {row['destination']}", "size": "xs", "color": "#666666", "align": "end", "flex": 1}
                    ]
                },
                # บรรทัด 3: วัตถุประสงค์ (ตัวเล็ก)
                {
                    "type": "text",
                    "text": f"📝 {row['purpose']}",
                    "size": "xxs",
                    "color": "#999999",
                    "wrap": True
                }
            ]
        }
        contents.append(row_box)
        contents.append({"type": "separator", "margin": "sm"})

    # ประกอบร่าง Flex Bubble
    bubble = {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": contents
        }
    }
    return FlexSendMessage(alt_text=f"ตารางงาน {title}", contents=bubble)

# --- 4. ฟังก์ชันจัดการ Webhook ---
@app.post("/callback")
async def callback(request: Request):
    signature = request.headers.get('X-Line-Signature')
    body = await request.body()
    try:
        handler.handle(body.decode('utf-8'), signature)
    except Exception as e:
        print(f"Webhook Error: {e}")
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    user_id = event.source.user_id
    
    # เมนูเลือกดูข้อมูล (Quick Reply)
    quick_reply_menu = QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="🚗 ตารางรถ", text="ดูตารางรถ")),
        QuickReplyButton(action=MessageAction(label="🏢 ตารางห้อง", text="ดูตารางห้อง")),
        QuickReplyButton(action=MessageAction(label="⏳ รออนุมัติ", text="ดูรายการรออนุมัติ")),
        QuickReplyButton(action=MessageAction(label="📝 จองใหม่", text="จอง"))
    ])

    # 1. กรณีพิมพ์ "ดู" หรือคำทักทาย -> แสดงปุ่มให้เลือก
    if text in ["ดู", "เมนู", "ตารางงาน", "สวัสดี", "ทัก"]:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text="ต้องการดูข้อมูลส่วนไหนครับ? เลือกจากปุ่มด้านล่างได้เลย 👇",
                quick_reply=quick_reply_menu
            )
        )

    # 2. กรณีเลือก "ดูตารางรถ"
    elif text == "ดูตารางรถ":
        now = datetime.now().isoformat()
        # ดึงข้อมูลจาก Supabase เหมือนหน้าเว็บ
        car_list = ["Civic (ตุ้ม)", "Civic (บอล)", "Camry (เนก)", "MG ขับเอง"]
        res = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", now).in_("resource", car_list).order("start_time").execute()
        
        flex_msg = create_schedule_flex("📅 ตารางการใช้รถ", res.data, color="#1E88E5") # สีฟ้า
        line_bot_api.reply_message(event.reply_token, flex_msg)

    # 3. กรณีเลือก "ดูตารางห้อง"
    elif text == "ดูตารางห้อง":
        now = datetime.now().isoformat()
        room_list = ["ห้องชั้น 1 (ห้องใหญ่)", "ห้องชั้น 2", "ห้อง VIP", "ห้องชั้นลอย", "ห้อง Production"]
        res = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", now).in_("resource", room_list).order("start_time").execute()
        
        flex_msg = create_schedule_flex("📅 ตารางห้องประชุม", res.data, color="#43A047") # สีเขียว
        line_bot_api.reply_message(event.reply_token, flex_msg)

    # 4. กรณีเลือก "ดูรายการรออนุมัติ" (สำหรับ Admin)
    elif text == "ดูรายการรออนุมัติ":
        if user_id in ADMIN_IDS:
            res = supabase.table("bookings").select("*").eq("status", "Pending").execute()
            if not res.data:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ ไม่มีรายการรออนุมัติครับ", quick_reply=quick_reply_menu))
            else:
                # สร้าง List ข้อความ Text ง่ายๆ สำหรับ Admin (หรือจะทำ Flex ก็ได้)
                msg = "รายการรออนุมัติ:\n"
                for item in res.data:
                    msg += f"🆔 {item['id']}: {item['resource']} โดย {item['requester']}\n"
                msg += "\n⚠️ ไปที่หน้าเว็บเพื่อกดอนุมัติครับ"
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🚫 ส่วนนี้สำหรับ Admin เท่านั้นครับ", quick_reply=quick_reply_menu))

    # 5. กรณีเลือก "จอง"
    elif text == "จอง":
        url = "https://office-booking-system-hll8ub77ixfgmj2s4slbu4.streamlit.app/"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"📝 กดลิงก์เพื่อทำการจอง:\n{url}", quick_reply=quick_reply_menu))

    # กรณีอื่นๆ
    else:
        # ถ้าพิมพ์มาไม่ตรงคำสั่ง ให้ขึ้นเมนูช่วยเหลือ
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ผมไม่เข้าใจคำสั่งครับ ลองเลือกเมนูด้านล่างนะ", quick_reply=quick_reply_menu))

# --- ส่วนรับ Notification (คงเดิม) ---
@app.post("/notify")
async def notify_booking(request: Request):
    try:
        data = await request.json()
        resource = data.get("resource", "-")
        name = data.get("name", "-")
        date = data.get("date", "-")
        
        msg = f"🔔 มีรายการจองใหม่!\n\n🔹 {resource}\n👤 {name}\n📅 {date}\n\n⚠️ Admin โปรดตรวจสอบ"
        line_bot_api.broadcast(TextSendMessage(text=msg))
        return {"status": "success"}
    except Exception as e:
        print(f"Notify Error: {e}")
        return {"status": "error"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
