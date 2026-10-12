import os
import requests
import logging
import json
import time
import base64
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ==================== FINAL PRODUCTION - ALL REAL IDS ====================
BOT_TOKEN = "8385686825:AAGWBQTiWAMV4k8c8Zl8dHxxrFoAFRtbLtU"
VIP_CHANNEL_LINK = "https://t.me/+7QqLtVfvtWlkOWFk"
VIP_GROUP_ID = -1003955376374
ADMIN_IDS = [7355302122]

PAYHERO_USERNAME = "iLD9BQWUGewsdB77vNtk"
PAYHERO_PASSWORD = "pcnPdIyVrDRarWZQLYK8hxnXd6vZY3bzqtdQWHK2"
PAYHERO_ACCOUNT_ID = "8898"
PAYHERO_BASIC_TOKEN = "Basic [STRIPPED 84 bytes]"
PAYHERO_CHANNEL_ID = 8506

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

PACKAGES = {
    "pkg_50": {"id": "pkg_50", "name": "Daily VIP", "price": 50, "days": 1},
    "pkg_150": {"id": "pkg_150", "name": "Weekly VIP", "price": 150, "days": 7},
    "pkg_500": {"id": "pkg_500", "name": "Monthly VIP", "price": 500, "days": 30}
}

DB_FILE = "/tmp/killohvip_db.json"
def load_db():
    try:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, 'r') as f:
                return json.load(f)
    except: pass
    return {"users": {}, "payments": {}, "stats": {"total_users": 0, "total_revenue": 0}}
def save_db(db):
    try:
        with open(DB_FILE, 'w') as f:
            json.dump(db, f, indent=2)
    except Exception as e:
        logger.error(f"DB save error: {e}")

db = load_db()
user_state = {}

def telegram_request(method, payload):
    url = f"{TELEGRAM_API}/{method}"
    try:
        r = requests.post(url, json=payload, timeout=15)
        logger.info(f"{method} -> {r.status_code}: {r.text[:800]}")
        return r.json() if r.text else {}
    except Exception as e:
        logger.error(f"{method} error: {e}")
        return {}

def send_message(chat_id, text, reply_markup=None, parse_mode="Markdown"):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return telegram_request("sendMessage", payload)

def send_message_with_packages(chat_id):
    text = (
        "🔥 *KILLOHVIP BOT - PREMIUM ACCESS* 🔥\n\n"
        "Welcome to the most exclusive VIP in KE! 🇰🇪\n\n"
        "💎 *SELECT YOUR PACKAGE:* \n\n"
        "1️⃣ *Daily VIP* - KES 50\n"
        " └ 1 day full access\n\n"
        "2️⃣ *Weekly VIP* - KES 150\n"
        " └ 7 days + BONUS\n\n"
        "3️⃣ *Monthly VIP* - KES 500\n"
        " └ 30 days full access\n\n"
        "👇 Tap a package below to pay via M-Pesa STK Push"
    )
    keyboard = {
        "inline_keyboard": [
            [{"text": "☀️ Daily - KES 50", "callback_data": "pkg_50"}],
            [{"text": "📅 Weekly - KES 150", "callback_data": "pkg_150"}],
            [{"text": "🔥 Monthly - KES 500 (Best Value)", "callback_data": "pkg_500"}],
            [{"text": "📞 Support", "url": "https://t.me/killoh"}]
        ]
    }
    return send_message(chat_id, text, reply_markup=keyboard)

def answer_callback_query(callback_query_id, text=""):
    return telegram_request("answerCallbackQuery", {"callback_query_id": callback_query_id, "text": text})

def create_group_invite_link():
    try:
        payload = {"chat_id": VIP_GROUP_ID, "name": f"VIP-{int(time.time())}", "creates_join_request": False}
        resp = telegram_request("createChatInviteLink", payload)
        if resp.get("ok") and resp.get("result", {}).get("invite_link"):
            return resp["result"]["invite_link"]
    except Exception as e:
        logger.error(f"Invite link error: {e}")
    return VIP_CHANNEL_LINK

def normalize_phone(raw):
    raw = raw.replace(" ", "").replace("+", "").replace("-", "")
    if raw.startswith("07"): return "254" + raw[1:]
    elif raw.startswith("01"): return "254" + raw[1:]
    elif raw.startswith("7") and len(raw) == 9: return "254" + raw
    elif raw.startswith("1") and len(raw) == 9: return "254" + raw
    elif raw.startswith("254"): return raw
    return raw

def is_valid_phone(phone):
    return phone.startswith("254") and len(phone) == 12 and phone[3:].isdigit()

def create_payhero_payment(amount, phone, external_ref):
    try:
        headers = {"Authorization": PAYHERO_BASIC_TOKEN, "Content-Type": "application/json"}
        url = "https://backend.payhero.co.ke/api/v2/payments"
        payload = {
            "amount": int(amount),
            "phone_number": phone,
            "channel_id": int(PAYHERO_CHANNEL_ID),
            "provider": "m-pesa",
            "external_reference": external_ref,
            "callback_url": "https://killohvip-bot.onrender.com/callback"
        }
        logger.info(f"PayHero Request: {payload}")
        resp = requests.post(url, json=payload, headers=headers, timeout=20)
        logger.info(f"PayHero Response {resp.status_code}: {resp.text}")
        try:
            data = resp.json()
        except:
            data = {"raw": resp.text}
        if resp.status_code in [200, 201]:
            return True, data
        auth_str = f"{PAYHERO_USERNAME}:{PAYHERO_PASSWORD}"
        b64_auth = base64.b64encode(auth_str.encode()).decode()
        headers2 = {"Authorization": f"Basic {b64_auth}", "Content-Type": "application/json"}
        resp2 = requests.post(url, json=payload, headers=headers2, timeout=20)
        logger.info(f"Fallback {resp2.status_code}: {resp2.text}")
        try:
            data2 = resp2.json()
        except:
            data2 = {"raw": resp2.text}
        if resp2.status_code in [200, 201]:
            return True, data2
        return False, data
    except Exception as e:
        logger.error(f"PayHero exception: {e}", exc_info=True)
        return False, {"error": str(e)}

@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "status": "KILLOHVIP BOT ONLINE - FINAL 50/150/500",
        "bot": BOT_TOKEN.split(":")[0],
        "admin": ADMIN_IDS,
        "group_id": VIP_GROUP_ID,
        "vip_link": VIP_CHANNEL_LINK,
        "payhero_account": PAYHERO_ACCOUNT_ID,
        "payhero_channel": PAYHERO_CHANNEL_ID,
        "packages": PACKAGES,
        "users": len(db["users"]),
        "revenue": db["stats"].get("total_revenue", 0)
    }), 200

@app.route('/', methods=['POST'])
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        return "KILLOHVIP BOT ONLINE - FINAL 50/150/500", 200
    try:
        update = request.get_json()
        logger.info(f"Update: {json.dumps(update)[:1500]}")
        if not update:
            return jsonify({"ok": True}), 200

        if "callback_query" in update:
            cq = update["callback_query"]
            chat_id = cq["message"]["chat"]["id"]
            data = cq.get("data", "")
            cq_id = cq["id"]
            user = cq.get("from", {})
            if str(chat_id) not in db["users"]:
                db["users"][str(chat_id)] = {"id": chat_id, "username": user.get("username"), "first_name": user.get("first_name"), "joined": datetime.now().isoformat()}
                db["stats"]["total_users"] = len(db["users"])
                save_db(db)
            if data in PACKAGES:
                pkg = PACKAGES[data]
                user_state[chat_id] = {"package_id": data, "package": pkg}
                answer_callback_query(cq_id, f"Selected {pkg['name']}")
                send_message(chat_id, f"✅ You selected: *{pkg['name']}* - KES {pkg['price']}\n\n📱 *Send your M-Pesa number* to receive STK Push\nFormat: `254712345678`")
            return jsonify({"ok": True}), 200

        if "message" not in update:
            return jsonify({"ok": True}), 200

        message = update["message"]
        chat_id = message["chat"]["id"]
        text = message.get("text", "").strip()
        user = message.get("from", {})

        if str(chat_id) not in db["users"]:
            db["users"][str(chat_id)] = {"id": chat_id, "username": user.get("username"), "first_name": user.get("first_name"), "joined": datetime.now().isoformat(), "vip_until": None}
            save_db(db)

        if text.startswith("/start"):
            user_state[chat_id] = {}
            send_message_with_packages(chat_id)

        elif text.startswith("/myid"):
            send_message(chat_id, f"🆔 *Your ID:* `{chat_id}`\nGroup ID: `{VIP_GROUP_ID}`\nChannel ID: {PAYHERO_CHANNEL_ID}\nAccount ID: {PAYHERO_ACCOUNT_ID}")

        elif text.startswith("/help") or text.startswith("/packages"):
            send_message_with_packages(chat_id)

        elif text.startswith("/myvip"):
            u = db["users"].get(str(chat_id), {})
            vip_until = u.get("vip_until")
            if vip_until:
                try:
                    exp = datetime.fromisoformat(vip_until)
                    if exp > datetime.now():
                        group_link = create_group_invite_link()
                        send_message(chat_id, f"✅ *VIP Active* until {exp.strftime('%Y-%m-%d')}\n\n🔥 *VIP GROUP:*\n{group_link}\n\n🔥 *VIP CHANNEL:*\n{VIP_CHANNEL_LINK}")
                    else:
                        send_message(chat_id, f"❌ VIP Expired on {exp.strftime('%Y-%m-%d')}\n\nRenew with /start")
                except:
                    send_message(chat_id, f"VIP info: {vip_until}\nLink: {VIP_CHANNEL_LINK}")
            else:
                send_message(chat_id, "❌ No active VIP. Use /start to buy.")

        elif text.startswith("/admin"):
            if chat_id not in ADMIN_IDS:
                send_message(chat_id, "❌ Not admin.")
            else:
                total_users = len(db["users"])
                total_rev = db["stats"].get("total_revenue", 0)
                payments = len(db.get("payments", {}))
                pending = len([p for p in db["payments"].values() if p.get("status") == "pending"])
                send_message(chat_id, f"👑 *ADMIN PANEL - KILLOHVIP*\n\n🤖 Bot ID: {BOT_TOKEN.split(':')[0]}\n👥 Users: {total_users}\n💰 Revenue: KES {total_rev}\n💳 Payments: {payments}\n⏳ Pending: {pending}\n\n📢 Channel: {PAYHERO_CHANNEL_ID}\n🏦 Account: {PAYHERO_ACCOUNT_ID}\n👑 Admin: {ADMIN_IDS}\n📦 Group: {VIP_GROUP_ID}\n🔗 VIP: {VIP_CHANNEL_LINK}")

        elif is_valid_phone(normalize_phone(text)):
            phone = normalize_phone(text)
            state = user_state.get(chat_id, {})
            package_id = state.get("package_id")
            if not package_id:
                user_state[chat_id] = {"phone": phone}
                keyboard = {"inline_keyboard": [[{"text": "☀️ Daily - KES 50", "callback_data": "pkg_50"}],[{"text": "📅 Weekly - KES 150", "callback_data": "pkg_150"}],[{"text": "🔥 Monthly - KES 500", "callback_data": "pkg_500"}]]}
                send_message(chat_id, f"📱 Number saved: `{phone}`\n\nNow select your package:", reply_markup=keyboard)
                return jsonify({"ok": True}), 200
            pkg = PACKAGES.get(package_id)
            external_ref = f"KILLOH-{chat_id}-{int(time.time())}"
            send_message(chat_id, f"⏳ *Sending STK Push...*\n\n📱 To: `{phone}`\n💰 Amount: KES {pkg['price']}\n📦 Package: {pkg['name']}\n\nCheck your phone and enter M-Pesa PIN!")
            success, resp = create_payhero_payment(pkg['price'], phone, external_ref)
            if success:
                db["payments"][external_ref] = {"chat_id": chat_id, "phone": phone, "amount": pkg['price'], "package_id": package_id, "status": "pending", "created": datetime.now().isoformat()}
                save_db(db)
                user_state[chat_id]["external_ref"] = external_ref
                send_message(chat_id, f"✅ *STK Sent to {phone}!*\n\n1. Check your phone\n2. Enter M-Pesa PIN\n3. Wait for confirmation")
            else:
                error_msg = resp.get("message") or resp.get("error") or str(resp)[:500]
                send_message(chat_id, f"❌ *STK Failed*\n\nReason: {error_msg}\n\nChannel ID: {PAYHERO_CHANNEL_ID}")

        elif text.isdigit() and 10 <= int(text) <= 10000:
            amount = int(text)
            matched_pkg = None
            for pkg in PACKAGES.values():
                if pkg["price"] == amount:
                    matched_pkg = pkg
                    break
            if matched_pkg:
                user_state[chat_id] = {"package_id": matched_pkg["id"], "package": matched_pkg}
                send_message(chat_id, f"💰 KES {amount} = {matched_pkg['name']}\n\nNow send M-Pesa number `2547...`")
            else:
                send_message(chat_id, f"💰 KES {amount} noted. Send M-Pesa number to pay.")
                user_state[chat_id] = {"amount": amount}
        else:
            if text and not text.startswith("/"):
                send_message_with_packages(chat_id)
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
    return jsonify({"ok": True}), 200

@app.route('/callback', methods=['POST', 'GET'])
def payhero_callback():
    try:
        if request.method == 'GET':
            return jsonify({"status": "callback online", "channel_id": PAYHERO_CHANNEL_ID, "account_id": PAYHERO_ACCOUNT_ID, "group_id": VIP_GROUP_ID}), 200
        data = request.get_json() or {}
        logger.info(f"PayHero Callback: {json.dumps(data)[:2000]}")
        external_ref = data.get("external_reference") or data.get("ExternalReference") or data.get("reference") or ""
        if not external_ref and isinstance(data.get("response"), dict):
            external_ref = data["response"].get("ExternalReference", "")
        success = False
        if isinstance(data.get("response"), dict) and data["response"].get("ResultCode") == 0:
            success = True
        if str(data.get("status", "")).lower() in ["success", "successful", "0", "completed"]:
            success = True
        if data.get("MpesaReceiptNumber") or data.get("mpesa_receipt"):
            success = True
        if data.get("CheckoutRequestID") and not data.get("ResultCode"):
            success = True

        payment_key = None
        if external_ref and external_ref in db.get("payments", {}):
            payment_key = external_ref
        else:
            for k in reversed(list(db.get("payments", {}).keys())):
                if db["payments"][k].get("status") == "pending":
                    payment_key = k
                    break

        if payment_key:
            payment = db["payments"][payment_key]
            chat_id = payment["chat_id"]
            package_id = payment.get("package_id")
            pkg = PACKAGES.get(package_id, {"name": "VIP", "days": 30, "price": payment.get("amount", 500)})
            if success:
                payment["status"] = "success"
                payment["callback"] = data
                payment["completed"] = datetime.now().isoformat()
                days = pkg.get("days", 30)
                vip_until = datetime.now() + timedelta(days=days)
                if str(chat_id) in db["users"]:
                    db["users"][str(chat_id)]["vip_until"] = vip_until.isoformat()
                    db["users"][str(chat_id)]["last_package"] = package_id
                    db["users"][str(chat_id)]["phone"] = payment.get("phone")
                db["stats"]["total_revenue"] = db["stats"].get("total_revenue", 0) + payment.get("amount", 0)
                save_db(db)
                group_invite = create_group_invite_link()
                success_text = (
                    f"🎉 *PAYMENT CONFIRMED!* 🎉\n\n"
                    f"✅ KES {payment.get('amount')} received\n"
                    f"📦 Package: {pkg['name']}\n"
                    f"📅 Valid until: {vip_until.strftime('%Y-%m-%d')}\n\n"
                    f"🔥 *YOUR VIP ACCESS:*\n\n"
                    f"📢 *VIP GROUP:*\n{group_invite}\n\n"
                    f"📢 *VIP CHANNEL:*\n{VIP_CHANNEL_LINK}\n\n"
                    f"👇 Tap links to join\n"
                    f"⚠️ Save these links!\n\n"
                    f"Need help? Contact admin"
                )
                send_message(chat_id, success_text)
                for admin_id in ADMIN_IDS:
                    try:
                        send_message(admin_id, f"💰 *NEW PAYMENT*\n\nAmount: KES {payment.get('amount')}\nPackage: {pkg['name']}\nFrom: {chat_id}\nPhone: {payment.get('phone')}\nRef: {payment_key}")
                    except:
                        pass
            else:
                payment["status"] = "failed"
                payment["callback"] = data
                save_db(db)
                send_message(chat_id, f"❌ Payment failed or cancelled.\n\nIf you paid, contact admin with receipt.\n\nTry again: /start")
        return jsonify({"status": "received"}), 200
    except Exception as e:
        logger.error(f"Callback error: {e}", exc_info=True)
        return jsonify({"status": "error"}), 200

@app.route('/stats', methods=['GET'])
def stats():
    return jsonify({
        "users": len(db["users"]),
        "payments": len(db["payments"]),
        "revenue": db["stats"].get("total_revenue", 0),
        "channel_id": PAYHERO_CHANNEL_ID,
        "account_id": PAYHERO_ACCOUNT_ID,
        "group_id": VIP_GROUP_ID,
        "admin_ids": ADMIN_IDS,
        "packages": PACKAGES
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
