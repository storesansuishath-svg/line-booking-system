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
# (ใส่ Token ของคุณตรงนี้)
LINE_ACCESS_TOKEN = "ILJVHrD24hZCe/stNR6wKxglGerAEtefHwB0HlDzq2vx5zc+hx0JoS2fDQe6BFzsOCwMD47HldTFuCBve9JRa1uAlAuq24sK2Iv/C5T/+p8Vkh1ppr3MKOb0ghP9MGO1kVj4UmgSzdyrI8P0vKHprgdB04t89/1O/w1cDnyilFU="
LINE_SECRET = "92765784656c2d17a334add0233d9e2f"

SUPABASE_URL = "https://qejqynbxdflwebzzwfzu.supabase.co"
SUPABASE_KEY = "sb_publishable_hvNQEPvuEAlXfVeCzpy7Ug_kzvihQqq"

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_SECRET)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 2. รายชื่อ Admin (ใส่ User ID) ---
ADMIN_IDS = [
    "Ub5588daf37957fe7625abce16bd8bb8e","U39cfc5182354b7fe5174f181983e4d1a",
    # เพิ่ม ID Admin คนอื่นได้ที่นี่
]

# --- 3. ฟังก์ชันสร้างตารางสวยๆ (Flex Message) - แก้ไขเพิ่ม "วัตถุประสงค์" ---
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
                {"type": "text", "text": f"📍 {row.get('destination', '-')}", "size": "xs", "color": "#666666"},
                # --- ส่วนที่เพิ่มใหม่: วัตถุประสงค์ ---
                {
                    "type": "text", 
                    "text": f"📝 {row.get('purpose', '-')}", 
                    "size": "xs", 
                    "color": "#666666", 
                    "wrap": True, 
                    "margin": "xs"
                }
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
    
    # เมนู Quick Reply (ปุ่มลอยเหนือคีย์บอร์ด)
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

    elif text == "รออนุมัติ" or text == "อนุมัติ/ไม่อนุมัติ":
        if event.source.user_id in ADMIN_IDS:
            res = supabase.table("bookings").select("*").eq("status", "Pending").execute()
            if not res.data:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ ไม่มีรายการรออนุมัติครับ", quick_reply=quick_menu))
            else:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"มี {len(res.data)} รายการรออนุมัติ (กรุณารอแจ้งเตือน หรือกดจองใหม่เพื่อทดสอบ)", quick_reply=quick_menu))
        else:
             line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🚫 สำหรับ Admin เท่านั้นครับ", quick_reply=quick_menu))
            
    elif text == "เช็ค ID":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"ID ของคุณ: {event.source.user_id}"))

# --- 7. จัดการกดปุ่ม (Postback) ---
@handler.add(PostbackEvent)
def handle_postback(event):
    # ตรวจสอบสิทธิ์ Admin
    if event.source.user_id not in ADMIN_IDS:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🚫 คุณไม่มีสิทธิ์อนุมัติครับ"))
        return

    # แกะข้อมูลจากปุ่ม
    data = dict(parse_qsl(event.postback.data))
    action = data.get('action')
    booking_id = data.get('id')
    user_name = data.get('user')

    if action and booking_id:
        # 1. อัปเดตสถานะใน Supabase ทันที
        status = "Approved" if action == "approve" else "Rejected"
        supabase.table("bookings").update({"status": status}).eq("id", booking_id).execute()
        
        # 2. เตรียมข้อความยืนยันตัวหนังสือ
        msg_text = f"✅ อนุมัติคุณ {user_name} เรียบร้อยแล้ว" if action == "approve" else f"❌ ปฏิเสธคุณ {user_name} แล้ว"
        
        # สร้างรายการข้อความที่จะส่ง (List of Messages)
        reply_content = [TextSendMessage(text=msg_text)]

        # 3. ถ้ากด 'อนุมัติ' ให้ดึงตารางมาแถมไปด้วย
        if action == "approve":
            try:
                # ดึงข้อมูลใหม่ล่าสุดหลังอัปเดต
                now_iso = datetime.now().isoformat()
                res = supabase.table("bookings").select("*").eq("status", "Approved").gt("end_time", now_iso).order("start_time").execute()
                
                if res.data:
                    # สร้าง Flex Message ตารางงาน
                    table_flex = create_schedule_flex("📅 ตารางงานอัปเดตล่าสุด", res.data, "#2E7D32")
                    reply_content.append(table_flex)
            except Exception as e:
                print(f"Error fetching schedule: {e}")

        # 4. ส่งคำตอบกลับ (Reply) ทีเดียวทั้งชุด
        try:
            line_bot_api.reply_message(event.reply_token, reply_content)
        except Exception as e:
            print(f"Reply Error: {e}")
            # ถ้า Reply ไม่ได้ ให้ลองส่งแบบ Push (ป้องกันกรณี Token หมดอายุ)
            line_bot_api.push_message(event.source.user_id, reply_content)

# --- 8. รับ Notify จาก Streamlit ---

@app.post("/notify")
async def notify_booking(request: Request):
    data = await request.json()
    # ส่งเข้ากลุ่มโดย Broadcast (หรือเปลี่ยนเป็น push_message หากทราบ Group ID)
    line_bot_api.broadcast(create_approval_flex(data.get("id"), data))
    return {"status": "success"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)






