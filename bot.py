# -*- coding: utf-8 -*-
"""
Kairozen Referral Bot
----------------------
Bot ណែនាំមិត្តភក្តិ (Referral Bot) - ទទួលលុយ $0.05 ក្នុង 1 នាក់ដែលណែនាំចូលជោគជ័យ
អាចដកលុយចាប់ពី $0.50 ឡើងទៅ (ផ្ញើ QR Bakong មកអោយ admin ផ្ទាល់)
+ ត្រូវ verify ចូលរួម Telegram Channel សិន ទើបប្រើ Bot បាន (Force-Subscribe)
+ បើ user ចេញពី Channel ពេលក្រោយ → សមតុល្យទាំងអស់ត្រូវដកចេញ (forfeit) ដោយស្វ័យប្រវត្តិ
+ [V2] បើ user ដែលត្រូវបានណែនាំចេញពី Channel → ដកលុយ $REFERRAL_REWARD ត្រឡប់ពីអ្នកណែនាំវិញដែរ
+ [V3] admin អាចប្រើ /broadcast ដើម្បីផ្ញើអត្ថបទ, រូបភាព, ឬ Video ទៅ user ទាំងអស់ម្តងតែមួយ
+ [V4] ពេលដកលុយ → ដកចេញពី Top (reset referrals_count) + cooldown 1 ម៉ោង ទើបដកបានម្តងទៀត (ណែនាំថ្មីនៅតែបាន)
+ [V5] FIX: បើ user ចូលរួម Channel រួចវាយ /start ម្តងទៀត (មិនចុចប៊ូតុង verify) → ref_code ចាស់មិនបាត់ទៀតទេ, អ្នកណែនាំទទួលលុយត្រូវ

តម្រូវការ:
    pip install pyTelegramBotAPI>=4.14.0   (ត្រូវការ version ថ្មីដើម្បីប្រើ chat_member_handler)

របៀបប្រើ:
    1. ដាក់ BOT_TOKEN, ADMIN_ID, CHANNEL_USERNAME, CHANNEL_URL ខាងក្រោម
    2. បន្ថែម Bot នេះជា admin ក្នុង Channel (ត្រូវការដើម្បីពិនិត្យសមាជិកភាព និងតាមដានពេលគេចេញ)
    3. python kairozen_referral_bot.py

រចនាសម្ព័ន្ធទិន្នន័យរក្សាទុកក្នុង db.json (មិនត្រូវការ database server)
"""

import telebot
from telebot import types
import json
import os
import threading
import time
from datetime import datetime

# ====================== CONFIG ======================
# សំខាន់៖ តម្លៃទាំងអស់ខាងក្រោមអានពី Environment Variables (កំណត់ក្នុង Render Dashboard)
# កុំដាក់ token ឬ id ផ្ទាល់ក្នុងកូដនេះទៀត ដើម្បីសុវត្ថិភាព
BOT_TOKEN = os.environ["BOT_TOKEN"]                     # ត្រូវកំណត់ក្នុង Render Environment Variables
ADMIN_ID = int(os.environ["ADMIN_ID"])                  # admin telegram user id
REFERRAL_REWARD = float(os.environ.get("REFERRAL_REWARD", "0.05"))   # ទឹកប្រាក់ទទួលបានក្នុង 1 ការណែនាំជោគជ័យ
MIN_WITHDRAW = float(os.environ.get("MIN_WITHDRAW", "0.50"))         # ទឹកប្រាក់អប្បបរមាសម្រាប់ដក
WITHDRAW_COOLDOWN_SECONDS = int(os.environ.get("WITHDRAW_COOLDOWN_SECONDS", "3600"))   # [V4] cooldown 1 ម៉ោង
DB_FILE = os.environ.get("DB_FILE", "db.json")
LOCK = threading.Lock()

# ត្រូវចូលរួម Channel នេះសិន ទើបអាចប្រើ Bot បាន (Force-Subscribe Verification)
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "@kairozen_store3")   # username channel
CHANNEL_URL = os.environ.get("CHANNEL_URL", "https://t.me/kairozen_store3")  # link សម្រាប់ user ចុចចូល

# រក្សាទុក ref_code បណ្តោះអាសន្នខណៈពេលកំពុងរង់ចាំ user verify channel
pending_ref_code = {}

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ====================== DATABASE HELPERS ======================

def load_db():
    if not os.path.exists(DB_FILE):
        return {"users": {}, "withdraws": [], "transactions": []}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            data.setdefault("transactions", [])
            return data
        except json.JSONDecodeError:
            return {"users": {}, "withdraws": [], "transactions": []}


def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def log_transaction(data, tx_type, user_id, amount, note=""):
    """កត់ត្រាប្រវត្តិ transaction ទាំងអស់ (referral, withdraw, forfeit) សម្រាប់ audit
    ត្រូវហៅខណៈពេលកាន់ LOCK ហើយ, និងហៅ save_db ខ្លួនឯងនៅខាងក្រៅ"""
    data["transactions"].append({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": tx_type,          # "referral" | "withdraw_request" | "withdraw_approved" | "withdraw_rejected" | "forfeit"
        "user_id": str(user_id),
        "amount": round(amount, 2),
        "note": note,
    })


def get_user(data, user_id):
    uid = str(user_id)
    if uid not in data["users"]:
        data["users"][uid] = {
            "balance": 0.0,
            "referred_by": None,
            "referrals_count": 0,
            "username": None,
            "pending_withdraw": False,
            "last_withdraw_time": 0,   # [V4] timestamp (epoch) នៃការដកលុយចុងក្រោយ សម្រាប់គណនា cooldown
        }
    return data["users"][uid]


def bot_username():
    try:
        return bot.get_me().username
    except Exception:
        return "your_bot"


def main_reply_keyboard():
    """ម៉ឺនុយ Reply Keyboard ជាប់ស្ថិតនៅខាងក្រោម chat (ងាយស្រួលជាងវាយ command)"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("💰 សមតុល្យ"),
        types.KeyboardButton("🔗 លីងណែនាំ"),
    )
    markup.add(
        types.KeyboardButton("💸 ដកលុយ"),
        types.KeyboardButton("🏆 Top"),
    )
    markup.add(
        types.KeyboardButton("ℹ️ ជំនួយ"),
    )
    return markup


# ====================== CHANNEL VERIFICATION ======================

def is_member(user_id):
    """ពិនិត្យមើលថា user បានចូលរួម Channel ឬនៅ"""
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception:
        # បើ bot មិនមែនជា admin ក្នុង channel ឬ channel ខុស, ចាត់ទុកថាមិនអាច verify បាន
        return False


def send_join_prompt(chat_id, user_id, ref_code=None):
    """ផ្ញើសារសុំអោយចូលរួម Channel មុនពេលប្រើ Bot"""
    if ref_code:
        pending_ref_code[user_id] = ref_code

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📢 ចូលរួម Channel", url=CHANNEL_URL))
    markup.add(types.InlineKeyboardButton("✅ ខ្ញុំបានចូលរួចហើយ", callback_data="verify_channel"))
    bot.send_message(
        chat_id,
        "🔒 <b>សូមចូលរួម Channel របស់យើងសិន</b> ទើបអាចប្រើ Bot នេះបាន!\n\n"
        "1️⃣ ចុចប៊ូតុង 'ចូលរួម Channel' ខាងក្រោម\n"
        "2️⃣ បន្ទាប់ពីចូលរួមរួច ចុច '✅ ខ្ញុំបានចូលរួចហើយ'",
        reply_markup=markup,
    )


def require_membership(chat_id, user_id):
    """ត្រឡប់ True បើ user ជា member ហើយ, បើអត់ផ្ញើសារសុំចូលរួម ហើយត្រឡប់ False"""
    if is_member(user_id):
        return True
    send_join_prompt(chat_id, user_id)
    return False


def forfeit_balance(user_id):
    """លុបសមតុល្យ user ចោលទាំងអស់ ពេលគេចេញពី Channel
    + ដកលុយ $REFERRAL_REWARD ត្រឡប់ពីអ្នកណែនាំវិញដែរ (ព្រោះមិត្តភក្តិដែលគេបានណែនាំចេញពី channel ហើយ)
    ត្រឡប់ dict: {"lost_amount": ..., "referrer_id": ..., "referrer_clawback": ..., "referrer_new_balance": ...} ឬ None"""
    uid = str(user_id)
    with LOCK:
        data = load_db()
        if uid not in data["users"]:
            return None
        user = data["users"][uid]
        lost_amount = user["balance"]
        user["balance"] = 0.0
        user["pending_withdraw"] = False
        if lost_amount > 0:
            log_transaction(data, "forfeit", uid, lost_amount, "ចេញពី channel")

        result = {"lost_amount": lost_amount, "referrer_id": None, "referrer_clawback": 0.0, "referrer_new_balance": None}

        # ដកលុយត្រឡប់ពីអ្នកណែនាំ ដែលធ្លាប់ទទួលលុយពីការណែនាំ user នេះ
        referrer_id = user.get("referred_by")
        if referrer_id and referrer_id in data["users"]:
            referrer = data["users"][referrer_id]
            clawback = min(REFERRAL_REWARD, referrer["balance"])
            referrer["balance"] = round(referrer["balance"] - clawback, 2)
            referrer["referrals_count"] = max(0, referrer["referrals_count"] - 1)
            if clawback > 0:
                log_transaction(data, "referral_clawback", referrer_id, clawback, f"មិត្តភក្តិ {uid} ចេញពី channel")
            result["referrer_id"] = referrer_id
            result["referrer_clawback"] = clawback
            result["referrer_new_balance"] = referrer["balance"]

        save_db(data)
    return result


@bot.chat_member_handler()
def handle_channel_membership_change(update: types.ChatMemberUpdated):
    """ត្រួតពិនិត្យពេល user ចេញ/ត្រូវ kick ពី Channel -> លុបសមតុល្យចោលទាំងអស់"""
    try:
        chat_username = f"@{update.chat.username}" if update.chat.username else None
        if chat_username != CHANNEL_USERNAME:
            return

        old_status = update.old_chat_member.status
        new_status = update.new_chat_member.status

        was_in = old_status in ("member", "administrator", "creator")
        still_in = new_status in ("member", "administrator", "creator")

        if was_in and not still_in:
            user_id = update.new_chat_member.user.id
            result = forfeit_balance(user_id)

            if result is not None:
                lost_amount = result["lost_amount"]
                try:
                    bot.send_message(
                        user_id,
                        "⚠️ <b>អ្នកបានចេញពី Channel របស់យើង!</b>\n"
                        f"💸 សមតុល្យ <b>${lost_amount:.2f}</b> របស់អ្នកត្រូវបានដកចេញទាំងអស់។\n"
                        "🔄 សូមចូលរួម Channel ម្តងទៀតដើម្បីបន្តប្រើ Bot។"
                    )
                except Exception:
                    pass

                admin_text = (
                    "🚪 <b>User បានចេញពី Channel!</b>\n"
                    f"🆔 ID: <code>{user_id}</code>\n"
                    f"💸 សមតុល្យត្រូវបានដកចេញ: ${lost_amount:.2f}"
                )

                # ប្រសិនបើ user នេះមាន referrer ដែលធ្លាប់ទទួលលុយពីការណែនាំគេ -> ដកលុយត្រឡប់
                if result["referrer_id"] and result["referrer_clawback"] > 0:
                    referrer_id = result["referrer_id"]
                    clawback = result["referrer_clawback"]
                    new_balance = result["referrer_new_balance"]
                    try:
                        bot.send_message(
                            int(referrer_id),
                            f"⚠️ <b>មិត្តភក្តិដែលអ្នកណែនាំបានចេញពី Channel!</b>\n"
                            f"💸 លុយណែនាំ <b>${clawback:.2f}</b> ត្រូវបានដកត្រឡប់ពីសមតុល្យអ្នក។\n"
                            f"💰 សមតុល្យថ្មី: ${new_balance:.2f}"
                        )
                    except Exception:
                        pass
                    admin_text += (
                        f"\n👤 អ្នកណែនាំ: <code>{referrer_id}</code>\n"
                        f"💸 ដកត្រឡប់ពីអ្នកណែនាំ: ${clawback:.2f}"
                    )

                try:
                    bot.send_message(ADMIN_ID, admin_text)
                except Exception:
                    pass
    except Exception:
        pass


# ====================== START / REFERRAL ======================

@bot.message_handler(commands=["start"])
def handle_start(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    parts = message.text.split()
    ref_code = parts[1] if len(parts) > 1 else None

    if not require_membership(chat_id, user_id):
        # require_membership បានផ្ញើ prompt ហើយ, ហើយបានរក្សា ref_code ទុករង់ចាំ
        if ref_code:
            pending_ref_code[user_id] = ref_code
        return

    # [FIX] បើ user ចូលរួម Channel រួច ហើយវាយ /start ម្តងទៀត (ដោយមិនចុចប៊ូតុង verify)
    # ref_code ថ្មីនេះអាចគ្មាន → ត្រូវយក ref_code ចាស់ដែលធ្លាប់ផ្ទុកទុកមកប្រើវិញ កុំអោយបាត់លុយអ្នកណែនាំ
    if not ref_code:
        ref_code = pending_ref_code.get(user_id)
    pending_ref_code.pop(user_id, None)

    complete_registration(chat_id, user_id, message.from_user, ref_code)


def complete_registration(chat_id, user_id, from_user, ref_code):
    """ចុះឈ្មោះ user (បើថ្មី), គណនា referral reward, ជូនដំណឹង admin, និងផ្ញើ welcome menu"""
    username = from_user.username or from_user.first_name or "គ្មានឈ្មោះ"

    with LOCK:
        data = load_db()
        user = get_user(data, user_id)
        is_new_user = user["username"] is None
        user["username"] = username

        if is_new_user and ref_code and ref_code.isdigit() and int(ref_code) != user_id:
            # int(ref_code) != user_id  =>  ការពារ user ណែនាំខ្លួនឯង (self-referral) មិនអោយទទួលលុយ
            referrer_id = ref_code
            if referrer_id in data["users"]:
                referrer = data["users"][referrer_id]
                referrer["balance"] = round(referrer["balance"] + REFERRAL_REWARD, 2)
                referrer["referrals_count"] += 1
                user["referred_by"] = referrer_id
                log_transaction(data, "referral", referrer_id, REFERRAL_REWARD, f"ណែនាំ user {user_id}")

                # ជូនដំណឹង referrer
                try:
                    bot.send_message(
                        int(referrer_id),
                        f"🎉 អ្នកទទួលបាន <b>${REFERRAL_REWARD:.2f}</b> ដោយសារមិត្តភក្តិថ្មីចូលរួមតាមលីងណែនាំរបស់អ្នក!\n"
                        f"💰 សមតុល្យបច្ចុប្បន្ន: <b>${referrer['balance']:.2f}</b>\n"
                        f"👥 ចំនួនមិត្តភក្តិសរុប: {referrer['referrals_count']}"
                    )
                except Exception:
                    pass

        save_db(data)

        # ជូនដំណឹង admin រាល់ពេលមាន user ថ្មីចូល bot
        if is_new_user:
            ref_text = f"\n🔗 ណែនាំដោយ: <code>{user['referred_by']}</code>" if user["referred_by"] else "\n🔗 ចូលដោយផ្ទាល់ (គ្មាន referral)"
            try:
                bot.send_message(
                    ADMIN_ID,
                    f"🆕 <b>User ថ្មីចូល Bot!</b>\n"
                    f"👤 ឈ្មោះ: {username}\n"
                    f"🆔 ID: <code>{user_id}</code>{ref_text}"
                )
            except Exception:
                pass

    link = f"https://t.me/{bot_username()}?start={user_id}"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💰 មើលសមតុល្យ", callback_data="balance"))
    markup.add(types.InlineKeyboardButton("🔗 លីងណែនាំរបស់ខ្ញុំ", callback_data="myref"))
    markup.add(types.InlineKeyboardButton("💸 ដកលុយ", callback_data="withdraw"))

    bot.send_message(
        chat_id,
        "👋 សូមស្វាគមន៍មកកាន់ <b>Kairozen Referral Bot</b>!\n\n"
        f"💵 ណែនាំមិត្តភក្តិ 1 នាក់ = <b>${REFERRAL_REWARD:.2f}</b>\n"
        f"💸 ដកលុយចាប់ពី <b>${MIN_WITHDRAW:.2f}</b>\n\n"
        f"🔗 លីងណែនាំរបស់អ្នក:\n<code>{link}</code>",
        reply_markup=markup,
    )

    bot.send_message(
        chat_id,
        "👇 ឬប្រើម៉ឺនុយខាងក្រោមឲ្យលឿនជាងមុន:",
        reply_markup=main_reply_keyboard(),
    )


@bot.callback_query_handler(func=lambda c: c.data == "verify_channel")
def handle_verify_channel(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    if is_member(user_id):
        try:
            bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
        except Exception:
            pass
        bot.answer_callback_query(call.id, "✅ Verify ជោគជ័យ!")
        ref_code = pending_ref_code.pop(user_id, None)
        complete_registration(chat_id, user_id, call.from_user, ref_code)
    else:
        bot.answer_callback_query(call.id, "❌ អ្នកមិនទាន់បានចូលរួម Channel ទេ! សូមចូលរួមជាមុនសិន។", show_alert=True)


# ====================== BALANCE ======================

def send_balance(chat_id, user_id):
    with LOCK:
        data = load_db()
        user = get_user(data, user_id)
        save_db(data)
    bot.send_message(
        chat_id,
        f"💰 សមតុល្យរបស់អ្នក: <b>${user['balance']:.2f}</b>\n"
        f"👥 ចំនួនមិត្តភក្តិបានណែនាំ: {user['referrals_count']}"
    )


@bot.message_handler(commands=["balance"])
def handle_balance(message):
    if not require_membership(message.chat.id, message.from_user.id):
        return
    send_balance(message.chat.id, message.from_user.id)


# ====================== REFERRAL LINK ======================

def send_myref(chat_id, user_id):
    link = f"https://t.me/{bot_username()}?start={user_id}"
    with LOCK:
        data = load_db()
        user = get_user(data, user_id)
        save_db(data)
    bot.send_message(
        chat_id,
        f"🔗 លីងណែនាំរបស់អ្នក:\n<code>{link}</code>\n\n"
        f"👥 មិត្តភក្តិបានណែនាំ: {user['referrals_count']}\n"
        f"💰 ប្រាក់ចំណេញសរុបពី referral: ${round(user['referrals_count'] * REFERRAL_REWARD, 2):.2f}"
    )


@bot.message_handler(commands=["myref", "referral"])
def handle_myref(message):
    if not require_membership(message.chat.id, message.from_user.id):
        return
    send_myref(message.chat.id, message.from_user.id)


# ====================== WITHDRAW ======================

withdraw_waiting_qr = {}  # user_id -> True (កំពុងរង់ចាំ QR/account)


def start_withdraw(chat_id, user_id):
    with LOCK:
        data = load_db()
        user = get_user(data, user_id)

        if user["balance"] < MIN_WITHDRAW:
            bot.send_message(
                chat_id,
                f"⚠️ សមតុល្យអ្នកមិនទាន់គ្រប់ដកទេ។\n"
                f"💰 សមតុល្យបច្ចុប្បន្ន: ${user['balance']:.2f}\n"
                f"💸 ត្រូវការយ៉ាងតិច: ${MIN_WITHDRAW:.2f}"
            )
            save_db(data)
            return

        if user.get("pending_withdraw"):
            bot.send_message(chat_id, "⏳ សំណើដកលុយរបស់អ្នកកំពុងរង់ចាំ admin អនុម័តរួចហើយ។")
            save_db(data)
            return

        elapsed = time.time() - user.get("last_withdraw_time", 0)
        if elapsed < WITHDRAW_COOLDOWN_SECONDS:
            remaining = int(WITHDRAW_COOLDOWN_SECONDS - elapsed)
            mins, secs = divmod(remaining, 60)
            bot.send_message(
                chat_id,
                f"⏳ អ្នកទើបតែដកលុយរួច។ សូមរង់ចាំ <b>{mins} នាទី {secs} វិនាទី</b> ទៀត ទើបអាចដកលុយម្តងទៀតបាន។\n"
                f"💡 ប៉ុន្តែអ្នកនៅតែអាចណែនាំមិត្តភក្តិថ្មីៗ ដើម្បីទទួលលុយបន្ថែមបានដដែល!"
            )
            save_db(data)
            return

        save_db(data)

    withdraw_waiting_qr[user_id] = True
    bot.send_message(
        chat_id,
        "📤 សូមផ្ញើ <b>រូបភាព QR Bakong</b> ឬ <b>Bakong ID</b> របស់អ្នកមកទីនេះ "
        "ដើម្បីផ្ញើទៅ admin សម្រាប់ដំណើរការដកលុយ។\n\n"
        "🚫 ប្រសិនបើចង់បោះបង់ វាយ /cancel"
    )


@bot.message_handler(commands=["withdraw"])
def handle_withdraw(message):
    if not require_membership(message.chat.id, message.from_user.id):
        return
    start_withdraw(message.chat.id, message.from_user.id)


@bot.message_handler(commands=["cancel"])
def handle_cancel(message):
    user_id = message.from_user.id
    cancelled = False

    if withdraw_waiting_qr.pop(user_id, None):
        cancelled = True
        bot.send_message(message.chat.id, "🚫 ការដកលុយត្រូវបានបោះបង់។ សមតុល្យរបស់អ្នកនៅដដែល។")

    if user_id == ADMIN_ID and ADMIN_ID in broadcast_waiting:
        broadcast_waiting.discard(ADMIN_ID)
        cancelled = True
        bot.send_message(message.chat.id, "🚫 ការផ្សាយ (broadcast) ត្រូវបានបោះបង់។")

    if not cancelled:
        bot.send_message(message.chat.id, "ℹ️ គ្មានដំណើរការអ្វីកំពុងរង់ចាំសម្រាប់បោះបង់ទេ។")


# ====================== BROADCAST (admin → ផ្ញើសារ/រូប/video ទៅ user ទាំងអស់) ======================

broadcast_waiting = set()  # admin id ដែលកំពុងត្រូវបានស្នើសុំផ្ញើ content សម្រាប់ផ្សាយ


@bot.message_handler(commands=["broadcast"])
def handle_broadcast_cmd(message):
    if message.from_user.id != ADMIN_ID:
        return
    broadcast_waiting.add(ADMIN_ID)
    bot.send_message(
        message.chat.id,
        "📢 សូមផ្ញើ <b>អត្ថបទ, រូបភាព ឬ Video</b> ដែលអ្នកចង់ផ្សាយទៅ user ទាំងអស់ (អាចដាក់ caption ជាមួយរូប/video បាន)។\n\n"
        "🚫 វាយ /cancel ដើម្បីបោះបង់។"
    )


def run_broadcast(content_type, file_id, caption, report_chat_id):
    """ផ្ញើ content ទៅ user ទាំងអស់ក្នុង db (run ក្នុង thread ដាច់ដោយឡែក ដើម្បីកុំអោយ bot ខ្ទេច)"""
    with LOCK:
        data = load_db()
        user_ids = list(data["users"].keys())

    sent, failed = 0, 0
    for uid in user_ids:
        try:
            target = int(uid)
            if content_type == "text":
                bot.send_message(target, caption)
            elif content_type == "photo":
                bot.send_photo(target, file_id, caption=caption or None)
            elif content_type == "video":
                bot.send_video(target, file_id, caption=caption or None)
            sent += 1
        except Exception:
            failed += 1
        time.sleep(0.05)  # ការពារ rate limit របស់ Telegram

    try:
        bot.send_message(
            report_chat_id,
            f"✅ <b>ផ្សាយរួចរាល់!</b>\n📨 ជោគជ័យ: {sent} នាក់\n❌ បរាជ័យ: {failed} នាក់"
        )
    except Exception:
        pass


@bot.message_handler(
    content_types=["text", "photo", "video"],
    func=lambda m: m.from_user.id == ADMIN_ID
    and ADMIN_ID in broadcast_waiting
    and not (m.content_type == "text" and m.text.startswith("/")),
)
def handle_broadcast_content(message):
    broadcast_waiting.discard(ADMIN_ID)

    if message.content_type == "text":
        content_type, file_id, caption = "text", None, message.text
    elif message.content_type == "photo":
        content_type, file_id, caption = "photo", message.photo[-1].file_id, (message.caption or "")
    else:  # video
        content_type, file_id, caption = "video", message.video.file_id, (message.caption or "")

    bot.send_message(message.chat.id, "🚀 កំពុងផ្សាយទៅ user ទាំងអស់... សូមរង់ចាំ")
    threading.Thread(
        target=run_broadcast,
        args=(content_type, file_id, caption, message.chat.id),
        daemon=True,
    ).start()


@bot.message_handler(content_types=["photo"])
def handle_qr_photo(message):
    user_id = message.from_user.id
    if not withdraw_waiting_qr.get(user_id):
        return  # មិនមែនកំពុងដក, មិនធ្វើអ្វីទេ

    process_withdraw_request(message, qr_photo=message.photo[-1].file_id, qr_text=None)


@bot.message_handler(func=lambda m: withdraw_waiting_qr.get(m.from_user.id) and m.content_type == "text")
def handle_qr_text(message):
    process_withdraw_request(message, qr_photo=None, qr_text=message.text)


def process_withdraw_request(message, qr_photo, qr_text):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "គ្មានឈ្មោះ"

    with LOCK:
        data = load_db()
        user = get_user(data, user_id)
        amount = user["balance"]
        user["pending_withdraw"] = True
        data["withdraws"].append({
            "user_id": str(user_id),
            "username": username,
            "amount": amount,
            "qr_text": qr_text,
            "status": "pending",
        })
        log_transaction(data, "withdraw_request", user_id, amount, "សំណើដកលុយថ្មី")
        save_db(data)

    withdraw_waiting_qr.pop(user_id, None)

    admin_caption = (
        f"💸 <b>សំណើដកលុយថ្មី!</b>\n"
        f"👤 ឈ្មោះ: {username}\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"💰 ចំនួនទឹកប្រាក់: <b>${amount:.2f}</b>\n"
    )
    if qr_text:
        admin_caption += f"🏦 Bakong ID / Info: <code>{qr_text}</code>\n"

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ អនុម័ត", callback_data=f"approve_{user_id}"),
        types.InlineKeyboardButton("❌ បដិសេធ", callback_data=f"reject_{user_id}"),
    )

    try:
        if qr_photo:
            bot.send_photo(ADMIN_ID, qr_photo, caption=admin_caption, reply_markup=markup)
        else:
            bot.send_message(ADMIN_ID, admin_caption, reply_markup=markup)
    except Exception:
        pass

    bot.send_message(
        message.chat.id,
        "✅ សំណើដកលុយរបស់អ្នកត្រូវបានផ្ញើទៅ admin ហើយ។ សូមរង់ចាំការអនុម័ត។"
    )


# ====================== ADMIN APPROVE / REJECT ======================

@bot.callback_query_handler(func=lambda c: c.data.startswith("approve_") or c.data.startswith("reject_"))
def handle_admin_decision(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "អ្នកមិនមែនជា admin ទេ។")
        return

    action, target_id = call.data.split("_", 1)

    with LOCK:
        data = load_db()
        user = get_user(data, target_id)
        user["pending_withdraw"] = False

        if action == "approve":
            approved_amount = user["balance"]
            user["balance"] = 0.0
            user["referrals_count"] = 0          # [V4] ដកចេញពី Top បន្ទាប់ពីដកលុយរួច
            user["last_withdraw_time"] = time.time()   # [V4] ចាប់ផ្តើម cooldown 1 ម៉ោង
            for w in reversed(data["withdraws"]):
                if w["user_id"] == target_id and w["status"] == "pending":
                    w["status"] = "approved"
                    break
            log_transaction(data, "withdraw_approved", target_id, approved_amount, "admin អនុម័ត")
            save_db(data)
            try:
                bot.send_message(
                    int(target_id),
                    "✅ ការដកលុយរបស់អ្នកត្រូវបានអនុម័ត និងផ្ញើរួចរាល់!\n"
                    f"⏳ អ្នកអាចដកលុយម្តងទៀតបាន បន្ទាប់ពី <b>1 ម៉ោង</b>។\n"
                    "💵 ប៉ុន្តែអ្នកនៅតែអាចណែនាំមិត្តភក្តិថ្មីៗ ដើម្បីទទួលលុយបន្ថែមបានដដែលគ្រប់ពេល!"
                )
            except Exception:
                pass
            bot.answer_callback_query(call.id, "បានអនុម័ត ✅")
        else:
            for w in reversed(data["withdraws"]):
                if w["user_id"] == target_id and w["status"] == "pending":
                    w["status"] = "rejected"
                    break
            log_transaction(data, "withdraw_rejected", target_id, 0, "admin បដិសេធ")
            save_db(data)
            try:
                bot.send_message(int(target_id), "❌ សំណើដកលុយរបស់អ្នកត្រូវបានបដិសេធ។ សូមទាក់ទង admin សម្រាប់ព័ត៌មានបន្ថែម។")
            except Exception:
                pass
            bot.answer_callback_query(call.id, "បានបដិសេធ ❌")

    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass


# ====================== CALLBACK BUTTONS (menu) ======================

@bot.callback_query_handler(func=lambda c: c.data in ["balance", "myref", "withdraw"])
def handle_menu_callbacks(call):
    if not require_membership(call.message.chat.id, call.from_user.id):
        bot.answer_callback_query(call.id)
        return
    if call.data == "balance":
        send_balance(call.message.chat.id, call.from_user.id)
    elif call.data == "myref":
        send_myref(call.message.chat.id, call.from_user.id)
    elif call.data == "withdraw":
        start_withdraw(call.message.chat.id, call.from_user.id)
    bot.answer_callback_query(call.id)


# ====================== REPLY KEYBOARD (bottom menu) ======================

@bot.message_handler(func=lambda m: m.text in ["💰 សមតុល្យ", "🔗 លីងណែនាំ", "💸 ដកលុយ", "🏆 Top", "ℹ️ ជំនួយ"])
def handle_reply_keyboard(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not require_membership(chat_id, user_id):
        return

    if message.text == "💰 សមតុល្យ":
        send_balance(chat_id, user_id)
    elif message.text == "🔗 លីងណែនាំ":
        send_myref(chat_id, user_id)
    elif message.text == "💸 ដកលុយ":
        start_withdraw(chat_id, user_id)
    elif message.text == "🏆 Top":
        send_top(chat_id)
    elif message.text == "ℹ️ ជំនួយ":
        bot.send_message(
            chat_id,
            "ℹ️ <b>របៀបប្រើ Bot</b>\n\n"
            f"💵 ណែនាំមិត្តភក្តិ 1 នាក់ = ${REFERRAL_REWARD:.2f}\n"
            f"💸 ដកលុយចាប់ពី ${MIN_WITHDRAW:.2f}\n"
            "🔗 ប្រើប៊ូតុង 'លីងណែនាំ' ដើម្បីយកលីងផ្ញើទៅមិត្តភក្តិ\n"
            "💰 ប្រើប៊ូតុង 'សមតុល្យ' ដើម្បីពិនិត្យលុយរបស់អ្នក\n"
            "💸 ប្រើប៊ូតុង 'ដកលុយ' ដើម្បីដកលុយចេញ (ត្រូវផ្ញើ QR/Bakong ID, ប្រើ /cancel បើចង់បោះបង់)\n"
            "🏆 ប្រើប៊ូតុង 'Top' ដើម្បីមើល leaderboard អ្នកណែនាំច្រើនជាងគេ",
            reply_markup=main_reply_keyboard(),
        )


# ====================== ADMIN COMMANDS ======================

@bot.message_handler(commands=["stats"])
def handle_stats(message):
    if message.from_user.id != ADMIN_ID:
        return
    with LOCK:
        data = load_db()
        total_users = len(data["users"])
        total_balance = round(sum(u["balance"] for u in data["users"].values()), 2)
        pending = len([w for w in data["withdraws"] if w["status"] == "pending"])
    bot.send_message(
        message.chat.id,
        f"📊 <b>ស្ថិតិ Bot</b>\n"
        f"👥 User សរុប: {total_users}\n"
        f"💰 សមតុល្យសរុបនៅជំពាក់ user: ${total_balance:.2f}\n"
        f"⏳ សំណើដកលុយរង់ចាំ: {pending}"
    )


@bot.message_handler(commands=["history"])
def handle_history(message):
    if message.from_user.id != ADMIN_ID:
        return
    with LOCK:
        data = load_db()
        recent = data["transactions"][-15:]

    if not recent:
        bot.send_message(message.chat.id, "📭 មិនទាន់មាន transaction ណាមួយនៅឡើយទេ។")
        return

    type_icons = {
        "referral": "🎉",
        "withdraw_request": "📤",
        "withdraw_approved": "✅",
        "withdraw_rejected": "❌",
        "forfeit": "🚪",
        "referral_clawback": "↩️",
    }
    lines = ["📜 <b>Transaction ថ្មីៗ (15 ចុងក្រោយ)</b>\n"]
    for tx in reversed(recent):
        icon = type_icons.get(tx["type"], "•")
        lines.append(f"{icon} {tx['time']} | <code>{tx['user_id']}</code> | ${tx['amount']:.2f} | {tx['note']}")

    bot.send_message(message.chat.id, "\n".join(lines))


# ====================== LEADERBOARD ======================

@bot.message_handler(commands=["top"])
def handle_top(message):
    if not require_membership(message.chat.id, message.from_user.id):
        return
    send_top(message.chat.id)


def send_top(chat_id):
    with LOCK:
        data = load_db()
        ranked = sorted(
            data["users"].items(),
            key=lambda item: item[1]["referrals_count"],
            reverse=True,
        )

    top10 = [(uid, u) for uid, u in ranked if u["referrals_count"] > 0][:10]

    if not top10:
        bot.send_message(chat_id, "📭 មិនទាន់មាន user ណាមួយណែនាំជោគជ័យនៅឡើយទេ។")
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 <b>Top 10 អ្នកណែនាំច្រើនជាងគេ</b>\n"]
    for i, (uid, u) in enumerate(top10):
        rank = medals[i] if i < 3 else f"{i + 1}."
        name = u.get("username") or uid
        lines.append(f"{rank} {name} — {u['referrals_count']} នាក់ (${round(u['referrals_count'] * REFERRAL_REWARD, 2):.2f})")

    bot.send_message(chat_id, "\n".join(lines))


# ====================== RUN ======================

if __name__ == "__main__":
    print("🤖 Kairozen Referral Bot កំពុងដំណើរការ...")
    bot.infinity_polling(
        skip_pending=True,
        allowed_updates=["message", "callback_query", "chat_member"],
    )
