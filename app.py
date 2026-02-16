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
    "Ub5588daf37957fe7625abce16bd8bb8e","U39cfc5182354b7fe5174f181983e4d1a"
]

# --- 3. ฟังก์ชันสร้างตารางสวยๆ (Flex Message) - เพิ่ม "ปลายทาง" และ "วัตถุประสงค์" ---
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
        except:
            t_start, t_end, date_str = "-", "-", "-"

        contents.append({
            "type": "box", "layout": "vertical", "margin": "md",
            "contents": [
                {"type": "text", "text": f"{i+1}. {row['resource']}", "weight": "bold", "color": "#333333"},
                {"type": "text", "text": f"📅 {date_str} | ⏰ {t_start}-{t_end}", "size": "sm", "color": color},
                {"type": "text", "text": f"👤 {row['requester']} ({row.get('dept', '-')})", "size": "xs", "color": "#666666"},
                # แก้ไขเพิ่มคำว่า "ปลายทาง" และทำให้ Wrap ข้อความได้
                {"type": "text", "text": f"📍 ปลายทาง: {row.get('destination', '-')}", "size": "xs", "color": "#666666", "wrap": True},
                {"type": "text", "text": f"📝 วัตถุประสงค์: {row.get('purpose', '-')}", "size": "xs", "color": "#666666", "wrap": True, "margin": "xs"}
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
                # แทรกบรรทัด "ปลายทาง" เพิ่มเติมตรงนี้
                {"type": "text", "text": f"📍 ปลายทาง: {data.get('destination', '-')}", "size": "sm", "color": "#666666", "wrap": True},
                {"type": "text", "text": f"📝 {data.get('purpose', '-')}", "size": "sm", "wrap": True, "color": "#555555"}
            ]
        },
        "footer": {
            "type": "box", "layout": "horizontal", "spacing": "sm",
            "contents": [
                {"type": "button", "style": "primary", "color": "#2E7D32", "action": PostbackAction(label="✅ อนุมัติ", data=f"action=approve&id={booking_id}&user={data.get('name')}", display_text="อนุมัติครับ")},
                {"type": "button", "style": "primary", "color": "#C62828", "action": PostbackAction(label="❌ ปฏิเสธ", data=f"action=reject&id={booking_id}&user={data.get('name')}", display_text="ปฏิเสธครับ")}
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
@app.get("/")
def home():
    return {"status": "Bot is running"}

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
        line_bot_api.reply_message(
