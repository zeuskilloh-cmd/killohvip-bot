import os
import sqlite3
import uuid
import requests
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify

app = Flask(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8385686825:AAGEfwg9sZHzy56HjoqT5GfgZRG0WThguks")
PAYHERO_USERNAME = os.environ.get("PAYHERO_USERNAME", "4rVB4X6Qq3X5LHM2lg5T")
PAYHERO_PASSWORD = os.environ.get("PAYHERO_PASSWORD", "wS5jv1wfvbXlNqBzr4VIW21nyGQ1WalpGinCGuwM")
ADMIN_ID = 7355302122
VIP_CHAT_ID = -1003955376374
BASE_URL = os.environ.get("BASE_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "https://killohvip.pythonanywhere.com"
BASE_URL = BASE_URL.rstrip("/")
PAYHERO_URL = "https://api.payhero.africa/api/v2/payments"
PAYHERO_ACCOUNT_ID = 8898
PAYHERO_CHANNEL_ID = int(os.environ.get("PAYHERO_CHANNEL_ID", "8506"))
DB_FILE = "vipbot.db"
PLANS = {"day": {"name": "1 Day", "price": 50, "days": 1}, "week": {"name": "1 Week", "price": 150, "days": 7}, "month": {"name": "1 Month", "price": 500, "days": 30}}

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("CREATE TABLE IF NOT EXISTS users (telegram_id INTEGER PRIMARY KEY, phone TEXT, plan TEXT, created_at TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, external_reference TEXT UNIQUE, telegram_id INTEGER, phone TEXT, plan TEXT, amount INTEGER, status TEXT, payhero_reference TEXT, transaction_id TEXT, created_at TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS subscriptions (id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER, plan TEXT, expires_at TEXT, active INTEGER DEFAULT 1, created_at TEXT)")
    conn.commit()
    conn.close()
init_db()

def telegram(method, data=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    try:
        response = requests.post(url, json=data or {}, timeout=30)
        print("TELEGRAM:", response.status_code, response.text)
        return response.json()
    except Exception as e:
        print("TELEGRAM ERROR:", repr(e))
        return {"ok": False, "error": str(e)}

def send_message(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text}
    if reply_markup:
        data["reply_markup"] = reply_markup
    return telegram("sendMessage", data)

def welcome_message(chat_id):
    send_message(chat_id, "👋 Welcome to KillohVIP!\n\n💎 Welcome to our exclusive VIP community.\n\nGet access to premium content and VIP updates.\n\nChoose a subscription plan below to get started.")
    show_plans(chat_id)

def show_plans(chat_id):
    keyboard = {"inline_keyboard": [[{"text": "💰 1 Day — KSh 50", "callback_data": "plan_day"}], [{"text": "📅 1 Week — KSh 150", "callback_data": "plan_week"}], [{"text": "🔥 1 Month — KSh 500", "callback_data": "plan_month"}]]}
    send_message(chat_id, "💎 SELECT YOUR VIP PLAN:\n\n💰 1 Day — KSh 50\n📅 1 Week — KSh 150\n🔥 1 Month — KSh 500", keyboard)

def normalize_phone(phone):
    phone = phone.strip().replace(" ", "").replace("-", "")
    if phone.startswith("+254"):
        phone = phone[1:]
    if phone.startswith("254") and len(phone) == 12:
        return phone
    if (phone.startswith("07") or phone.startswith("01")) and len(phone) == 10:
        return "254" + phone[1:]
    return None

def start_payment(telegram_id, phone, plan_key):
    plan = PLANS.get(plan_key)
    if not plan:
        return False, "Invalid plan."
    external_reference = f"VIP-{telegram_id}-{uuid.uuid4().hex[:12]}"
    conn = get_db()
    conn.execute("INSERT INTO payments (external_reference, telegram_id, phone, plan, amount, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (external_reference, telegram_id, phone, plan_key, plan["price"], "pending", datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()
    payload = {"amount": plan["price"], "phone_number": phone, "provider": "m-pesa", "channel_id": PAYHERO_CHANNEL_ID, "account_id": PAYHERO_ACCOUNT_ID, "external_reference": external_reference, "callback_url": f"{BASE_URL}/payhero/callback"}
    try:
        response = requests.post(PAYHERO_URL, auth=(PAYHERO_USERNAME, PAYHERO_PASSWORD), json=payload, timeout=30)
        print("PAYHERO STATUS:", response.status_code)
        print("PAYHERO RESPONSE:", response.text)
        if response.status_code not in [200, 201]:
            return False, f"PayHero error {response.status_code}:\n{response.text}"
        try:
            result = response.json()
        except Exception:
            result = {}
        if result.get("success") is False:
            return False, f"PayHero rejected the STK request:\n\n{result}"
        return True, external_reference
    except Exception as e:
        print("PAYHERO REQUEST ERROR:", repr(e))
        return False, f"Could not connect to PayHero:\n{e}"

def create_vip_invite():
    expire_time = int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp())
    result = telegram("createChatInviteLink", {"chat_id": VIP_CHAT_ID, "member_limit": 1, "expire_date": expire_time})
    print("INVITE RESULT:", result)
    if result.get("ok"):
        return result["result"]["invite_link"]
    return None

def activate_subscription(telegram_id, plan_key):
    plan = PLANS.get(plan_key)
    if not plan:
        return None
    now = datetime.now(timezone.utc)
    conn = get_db()
    existing = conn.execute("SELECT expires_at FROM subscriptions WHERE telegram_id = ? AND active = 1 ORDER BY expires_at DESC LIMIT 1", (telegram_id,)).fetchone()
    start_time = now
    if existing:
        try:
            old_expiry = datetime.fromisoformat(existing["expires_at"])
            if old_expiry > now:
                start_time = old_expiry
        except Exception:
            pass
    expires_at = start_time + timedelta(days=plan["days"])
    conn.execute("UPDATE subscriptions SET active = 0 WHERE telegram_id = ?", (telegram_id,))
    conn.execute("INSERT INTO subscriptions (telegram_id, plan, expires_at, active, created_at) VALUES (?, ?, ?, ?, ?)", (telegram_id, plan_key, expires_at.isoformat(), 1, now.isoformat()))
    conn.commit()
    conn.close()
    return expires_at

@app.route("/payhero/callback", methods=["POST"])
def payhero_callback():
    data = request.get_json(silent=True) or {}
    print("PAYHERO CALLBACK:", data)
    external_reference = data.get("external_reference")
    status = str(data.get("status", "")).lower()
    if not external_reference:
        return jsonify({"received": True}), 200
    conn = get_db()
    payment = conn.execute("SELECT * FROM payments WHERE external_reference = ?", (external_reference,)).fetchone()
    if not payment:
        conn.close()
        return jsonify({"received": True}), 200
    if payment["status"] == "success":
        conn.close()
        return jsonify({"received": True}), 200
    if status != "success":
        conn.execute("UPDATE payments SET status = ?, payhero_reference = ?, transaction_id = ? WHERE external_reference = ?", (status or "failed", data.get("reference"), data.get("transaction_id"), external_reference))
        conn.commit()
        conn.close()
        send_message(payment["telegram_id"], "❌ Payment was not completed.\n\nPlease try again with /start.")
        return jsonify({"received": True}), 200
    conn.execute("UPDATE payments SET status = ?, payhero_reference = ?, transaction_id = ? WHERE external_reference = ?", ("success", data.get("reference"), data.get("transaction_id"), external_reference))
    conn.commit()
    conn.close()
    telegram_id = payment["telegram_id"]
    plan_key = payment["plan"]
    plan = PLANS[plan_key]
    expires_at = activate_subscription(telegram_id, plan_key)
    invite_link = create_vip_invite()
    if invite_link:
        send_message(telegram_id, f"✅ PAYMENT SUCCESSFUL!\n\n💎 Plan: {plan['name']}\n💰 Amount: KSh {plan['price']}\n\n🎉 Your KillohVIP access is ready!\n\n👇 Join here:\n{invite_link}\n\n⏰ Expires:\n{expires_at.strftime('%d %B %Y, %H:%M UTC')}\n\n⚠️ This link is for one person only.")
    else:
        send_message(telegram_id, "✅ Payment received!\n\nYour payment has been confirmed, but the VIP invite could not be created.\n\nPlease contact the administrator.")
    send_message(ADMIN_ID, f"💰 NEW KILLOHVIP PAYMENT\n\nTelegram ID: {telegram_id}\nPhone: {payment['phone']}\nPlan: {plan['name']}\nAmount: KSh {plan['price']}\n\nStatus: ✅ PAID")
    return jsonify({"received": True}), 200

@app.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    update = request.get_json(silent=True) or {}
    print("TELEGRAM UPDATE:", update)
    message = update.get("message")
    if message:
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "").strip()
        if text.startswith("/start"):
            welcome_message(chat_id)
            return jsonify({"ok": True})
        if text.startswith("/plans"):
            show_plans(chat_id)
            return jsonify({"ok": True})
        phone = normalize_phone(text)
        if phone:
            conn = get_db()
            user = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (chat_id,)).fetchone()
            conn.close()
            if user and user["plan"]:
                plan_key = user["plan"]
                plan = PLANS[plan_key]
                send_message(chat_id, "⏳ PROCESSING PAYMENT...\n\nAn M-Pesa STK Push will be sent to your phone.")
                success, result = start_payment(chat_id, phone, plan_key)
                if success:
                    conn = get_db()
                    conn.execute("UPDATE users SET phone = ? WHERE telegram_id = ?", (phone, chat_id))
                    conn.commit()
                    conn.close()
                    send_message(chat_id, "📲 STK PUSH SENT!\n\nCheck your M-Pesa phone and enter your M-Pesa PIN to complete the payment.")
                else:
                    send_message(chat_id, f"❌ STK PUSH COULD NOT BE SENT.\n\n{result}\n\nPlease check the details and try again with /start.")
                return jsonify({"ok": True})
        send_message(chat_id, "Please use /start to choose a VIP plan.")
        return jsonify({"ok": True})
    callback = update.get("callback_query")
    if callback:
        callback_id = callback.get("id")
        telegram("answerCallbackQuery", {"callback_query_id": callback_id})
        data = callback.get("data", "")
        chat_id = callback.get("message", {}).get("chat", {}).get("id")
        if data.startswith("plan_"):
            plan_key = data.replace("plan_", "")
            if plan_key not in PLANS:
                send_message(chat_id, "❌ Invalid plan.")
                return jsonify({"ok": True})
            plan = PLANS[plan_key]
            conn = get_db()
            conn.execute("INSERT INTO users (telegram_id, phone, plan, created_at) VALUES (?, ?, ?, ?) ON CONFLICT(telegram_id) DO UPDATE SET plan = excluded.plan", (chat_id, None, plan_key, datetime.now(timezone.utc).isoformat()))
            conn.commit()
            conn.close()
            send_message(chat_id, f"✅ PLAN SELECTED\n\n💎 {plan['name']}\n💰 Price: KSh {plan['price']}\n\n📱 Enter your M-Pesa number.\n\nExample:\n0712345678")
        return jsonify({"ok": True})
    return jsonify({"ok": True})

@app.route("/set-webhook")
def set_webhook():
    result = telegram("setWebhook", {"url": f"{BASE_URL}/telegram/webhook"})
    return jsonify(result)

@app.route("/delete-webhook")
def delete_webhook():
    result = telegram("deleteWebhook")
    return jsonify(result)

@app.route("/")
def home():
    return "KILLOHVIP BOT ONLINE - Updated"

@app.route("/health")
def health():
    return jsonify({"status": "online", "bot": "KillohVIP", "payment": "PayHero", "base_url": BASE_URL, "vip_chat_id": VIP_CHAT_ID, "account_id": PAYHERO_ACCOUNT_ID, "channel_id": PAYHERO_CHANNEL_ID, "plans": PLANS})

if __name__ == "__main__":
    app.run()
