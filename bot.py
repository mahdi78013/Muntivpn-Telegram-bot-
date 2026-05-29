# -*- coding: utf-8 -*-
"""
ربات تلگرام اینترنت آزاد³⁶۹
نسخه: 11.0.0 - اصلاح کامل باگ‌ها
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ═══════════════════════════════════════════════
# 🔑 تنظیمات — از متغیر محیطی بخوانید
# ═══════════════════════════════════════════════
TOKEN = os.getenv("BOT_TOKEN", "8725809008:AAGjjYo0sKSq_Z1_ODfxVjR5AjcGiZXC4Mk")
ADMIN_ID = int(os.getenv("ADMIN_ID", "748538264"))
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "muntivpn")
REMINDER_TIMEOUT_MINUTES = 10

# ═══════════════════════════════════════════════
# 💳 اطلاعات پرداخت — از متغیر محیطی بخوانید
# ═══════════════════════════════════════════════
CARD_NUMBER = os.getenv("CARD_NUMBER", "XXXX-XXXX-XXXX-XXXX")
CARD_OWNER = os.getenv("CARD_OWNER", "نام صاحب کارت")

# ═══════════════════════════════════════════════
# 📦 پلن‌های سرویس
# ═══════════════════════════════════════════════
PLANS = {
    "20GB": {"price": 390000, "gb": 20},
    "30GB": {"price": 520000, "gb": 30},
    "50GB": {"price": 790000, "gb": 50},
    "100GB": {"price": 1090000, "gb": 100},
}

# ═══════════════════════════════════════════════
# 🗄️ ذخیره‌سازی داخلی
# ═══════════════════════════════════════════════
users = {}
orders = {}
order_counter = 0
order_lock = asyncio.Lock()
active_receipts = {}
waiting_for_config = {}
pending_admin_order_id = {}
user_states = {}

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
RECEIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "receipts")

# ═══════════════════════════════════════════════
# 📝 لاگ‌ینگ
# ═══════════════════════════════════════════════
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════
# 💾 سیستم ذخیره‌سازی JSON
# ═══════════════════════════════════════════════
def save_data():
    try:
        data = {
            "orders": orders,
            "order_counter": order_counter,
            "users": {str(k): v for k, v in users.items()},
            "active_receipts": {str(k): v for k, v in active_receipts.items()},
            "waiting_for_config": {str(k): v for k, v in waiting_for_config.items()},
        }
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"خطا در ذخیره‌سازی: {e}")


def load_data():
    global orders, order_counter, users, active_receipts, waiting_for_config
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            orders = data.get("orders", {})
            order_counter = data.get("order_counter", 0)
            # کلیدهای user_id را به int تبدیل کنید
            users = {int(k): v for k, v in data.get("users", {}).items()}
            active_receipts = {int(k): v for k, v in data.get("active_receipts", {}).items()}
            waiting_for_config = {int(k): v for k, v in data.get("waiting_for_config", {}).items()}
            logger.info(f"داده‌ها بارگذاری شد: {len(orders)} سفارش، {len(users)} کاربر")
    except Exception as e:
        logger.error(f"خطا در بارگذاری داده: {e}")


# ═══════════════════════════════════════════════
# 🔒 بررسی عضویت در کانال
# ═══════════════════════════════════════════════
async def check_channel_membership(update, context):
    user = update.effective_user
    user_id = user.id
    try:
        member = await context.bot.get_chat_member(f"@{CHANNEL_USERNAME}", user_id)
        return member.status not in ["left", "kicked"]
    except Exception as e:
        # اگه ربات ادمین کانال نیست یا خطا داد، کاربر رو بلاک نکن
        logger.warning(f"بررسی عضویت کانال ناموفق: {e}")
        return True


async def send_not_member_message(update, query=None):
    keyboard = [
        [InlineKeyboardButton("📢 عضویت در کانال", url=f"https://t.me/{CHANNEL_USERNAME}")],
        [InlineKeyboardButton("✅ عضو شدم", callback_data="check_join")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = (
        f"🔒 <b>برای استفاده از ربات، ابتدا باید در کانال ما عضو شوید.</b>\n\n"
        f"📌 کانال ما: <a href=\"https://t.me/{CHANNEL_USERNAME}\">@{CHANNEL_USERNAME}</a>\n\n"
        f"✅ پس از عضویت، دکمه «عضو شدم» را بزنید."
    )
    if query:
        await query.answer()
        await query.edit_message_text(msg, parse_mode="HTML", reply_markup=reply_markup)
    elif update.message:
        await update.message.reply_text(msg, parse_mode="HTML", reply_markup=reply_markup)


# ═══════════════════════════════════════════════
# 🏠 منوی اصلی
# ═══════════════════════════════════════════════
def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 خرید سرویس", callback_data="buy_service")],
        [InlineKeyboardButton("⚡️ درباره سرور", callback_data="about_server")],
        [InlineKeyboardButton("📞 پشتیبانی", callback_data="support")],
    ])


# ═══════════════════════════════════════════════
# 🚀 دستور /start
# ═══════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id

    users[user_id] = {
        "name": user.full_name or user.username or "کاربر",
        "username": user.username,
        "registered_at": datetime.now().isoformat(),
    }
    save_data()

    if not await check_channel_membership(update, context):
        await send_not_member_message(update)
        return

    name = user.full_name or user.username or "کاربر"
    msg = (
        f"👋 <b>سلام {name}!</b>\n\n"
        f"🟢 به ربات <b>اینترنت آزاد³⁶۹</b> خوش آمدید.\n\n"
        f"از منوی زیر یکی از گزینه‌ها را انتخاب کنید:"
    )
    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=get_main_keyboard())


# ═══════════════════════════════════════════════
# 🚀 دستور /admin
# ═══════════════════════════════════════════════
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ شما دسترسی ادمین ندارید.")
        return
    await show_admin_panel_message(update.message)


# ═══════════════════════════════════════════════
# 🔘 هندلر کال‌بک‌ها
# ═══════════════════════════════════════════════
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    # FIX: همیشه اول answer() بده تا دکمه loading نماند
    await query.answer()

    # ──── جوین چک ────
    if data == "check_join":
        if await check_channel_membership(update, context):
            name = query.from_user.full_name or query.from_user.username or "کاربر"
            msg = (
                f"✅ <b>عضویت شما تأیید شد!</b>\n\n"
                f"سلام {name}! اکنون می‌توانید از ربات استفاده کنید."
            )
            await query.edit_message_text(msg, parse_mode="HTML", reply_markup=get_main_keyboard())
        else:
            keyboard = [
                [InlineKeyboardButton("📢 عضویت در کانال", url=f"https://t.me/{CHANNEL_USERNAME}")],
                [InlineKeyboardButton("✅ عضو شدم", callback_data="check_join")],
            ]
            msg = "❌ <b>عضویت شما تأیید نشد.</b>\n\n📌 لطفاً ابتدا در کانال عضو شوید، سپس دوباره تلاش کنید."
            await query.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # ──── بررسی عضویت برای بقیه دکمه‌ها ────
    if not await check_channel_membership(update, context):
        await send_not_member_message(update, query=query)
        return

    # ──── بازگشت به منو ────
    if data == "back_to_menu":
        user_states[user_id] = "idle"
        name = query.from_user.full_name or query.from_user.username or "کاربر"
        msg = (
            f"🏠 <b>منوی اصلی</b>\n\n"
            f"سلام {name}! یکی از گزینه‌های زیر را انتخاب کنید:"
        )
        await query.edit_message_text(msg, parse_mode="HTML", reply_markup=get_main_keyboard())
        return

    # ──── پشتیبانی ────
    if data == "support":
        msg = (
            "📞 <b>پشتیبانی اینترنت آزاد³⁶۹</b>\n\n"
            "برای ارتباط با پشتیبانی از طریق روش‌های زیر اقدام کنید:\n\n"
            f"📢 کانال: @{CHANNEL_USERNAME}\n\n"
            "⏰ ساعات پاسخگویی: ۹ صبح تا ۱۲ شب"
        )
        keyboard = [[InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_menu")]]
        await query.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # ──── درباره سرور ────
    if data == "about_server":
        await show_about_server(query)
        return

    # ──── ادمین: پنل ────
    if data == "admin_panel":
        if user_id != ADMIN_ID:
            await query.edit_message_text("❌ شما دسترسی ادمین ندارید.")
            return
        await show_admin_panel_query(query)
        return

    # ──── ادمین: مدیریت سفارش ────
    if data.startswith("order_"):
        if user_id != ADMIN_ID:
            await query.edit_message_text("❌ دسترسی ندارید.")
            return
        order_id = data.replace("order_", "", 1)
        await admin_manage_order(query, context, order_id)
        return

    # ──── ادمین: تأیید سفارش ────
    if data.startswith("confirm_order_"):
        if user_id != ADMIN_ID:
            return
        order_id = data.replace("confirm_order_", "", 1)
        if order_id in orders:
            await admin_confirm_order(query, context, order_id)
        return

    # ──── ادمین: رد سفارش ────
    if data.startswith("reject_order_"):
        if user_id != ADMIN_ID:
            return
        order_id = data.replace("reject_order_", "", 1)
        if order_id in orders:
            await admin_reject_order(query, context, order_id)
        return

    # ──── ادمین: لیست سفارش‌ها ────
    if data == "show_orders":
        if user_id != ADMIN_ID:
            await query.edit_message_text("❌ دسترسی ندارید.")
            return
        await show_all_orders(query, context)
        return

    # ──── کاربر: ارسال مجدد رسید ────
    if data == "retry_receipt":
        await retry_receipt(query, context)
        return

    # ──── کاربر: تأیید و مشاهده پرداخت ────
    if data == "confirm_payment_info":
        await show_payment_info(query, context)
        return

    # ──── خرید: شروع ────
    if data == "buy_service":
        await start_buy_flow(query, context)
        return

    # ──── خرید: انتخاب سرور ────
    if data == "server_cloudflare":
        await select_server_type(query, context)
        return

    # ──── خرید: انتخاب پلن ────
    if data.startswith("plan_"):
        await select_plan(query, context)
        return


# ═══════════════════════════════════════════════
# 🛒 فرآیند خرید
# ═══════════════════════════════════════════════
async def start_buy_flow(query, context) -> None:
    user_id = query.from_user.id
    user_states[user_id] = "buying"
    context.user_data["step"] = "server"

    keyboard = [
        [InlineKeyboardButton("☁️ Cloudflare", callback_data="server_cloudflare")],
        [InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_menu")],
    ]
    msg = "🛒 <b>خرید سرویس</b>\n\n📌 نوع سرور را انتخاب کنید:"
    await query.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def select_server_type(query, context) -> None:
    user_id = query.from_user.id
    context.user_data["server_type"] = "Cloudflare"
    context.user_data["step"] = "plan"

    keyboard = []
    for plan_key, plan_info in PLANS.items():
        price_str = f"{plan_info['price']:,}".replace(",", "٬")
        keyboard.append([InlineKeyboardButton(
            f"📦 {plan_key} — {price_str} تومان",
            callback_data=f"plan_{plan_key}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_menu")])

    plan_list = "\n".join([
        f"📦 <b>{key}</b> — {info['price']:,}".replace(",", "٬") + " تومان"
        for key, info in PLANS.items()
    ])
    msg = f"⚡ <b>پلن خود را انتخاب کنید:</b>\n\n{plan_list}"
    await query.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def select_plan(query, context) -> None:
    # FIX: استخراج plan_key از callback_data
    plan_key = query.data.replace("plan_", "", 1)

    # FIX: بررسی اینکه plan_key معتبر است
    if plan_key not in PLANS:
        await query.edit_message_text("❌ پلن انتخابی معتبر نیست. لطفاً دوباره تلاش کنید.", parse_mode="HTML")
        return

    plan_info = PLANS[plan_key]
    user_id = query.from_user.id

    context.user_data["plan"] = plan_key
    context.user_data["plan_price"] = plan_info["price"]
    context.user_data["step"] = "payment"

    price_str = f"{plan_info['price']:,}".replace(",", "٬")
    keyboard = [
        [InlineKeyboardButton("✅ تأیید و مشاهده اطلاعات پرداخت", callback_data="confirm_payment_info")],
        [InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_menu")],
    ]
    msg = (
        f"✅ <b>پلن انتخابی: {plan_key}</b>\n\n"
        f"💰 قیمت: {price_str} تومان\n"
        f"📅 مدت: ۳۰ روز\n\n"
        f"📌 برای مشاهده اطلاعات پرداخت، دکمه تأیید را بزنید."
    )
    await query.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def show_payment_info(query, context) -> None:
    plan_key = context.user_data.get("plan", "")
    plan_price = context.user_data.get("plan_price", 0)
    user_id = query.from_user.id

    # FIX: اگر plan_key خالی بود، به منوی خرید برگردان
    if not plan_key:
        await query.edit_message_text(
            "⚠️ لطفاً ابتدا یک پلن انتخاب کنید.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="buy_service")]]),
        )
        return

    user_states[user_id] = "waiting_receipt"
    context.user_data["step"] = "receipt"

    price_str = f"{plan_price:,}".replace(",", "٬")
    keyboard = [[InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_menu")]]
    msg = (
        f"🛒 <b>اطلاعات پرداخت</b>\n\n"
        f"📋 <b>مشخصات سفارش:</b>\n"
        f"   • نوع سرور: ☁️ Cloudflare\n"
        f"   • حجم: {plan_key}\n"
        f"   • مدت: ۳۰ روز\n"
        f"   • پروتکل: VLESS/VMESS\n\n"
        f"💰 <b>مبلغ: {price_str} تومان</b>\n\n"
        f"🏦 <b>اطلاعات کارت:</b>\n"
        f"   شماره کارت: <code>{CARD_NUMBER}</code>\n"
        f"   به نام: {CARD_OWNER}\n\n"
        f"📌 مبلغ را واریز کنید و <b>عکس رسید</b> را در همین چت ارسال کنید."
    )
    await query.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


# ═══════════════════════════════════════════════
# 📸 دریافت رسید
# ═══════════════════════════════════════════════
async def receive_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if user_states.get(user_id) != "waiting_receipt":
        return

    # FIX: بررسی سفارش pending موجود
    if user_id in active_receipts and active_receipts[user_id] in orders:
        existing_order = orders[active_receipts[user_id]]
        if existing_order["status"] == "pending":
            await update.message.reply_text(
                "⚠️ <b>شما یک رسید در انتظار بررسی دارید.</b>\n\n"
                "📌 لطفاً صبر کنید تا ادمین رسید فعلی شما را بررسی کند.",
                parse_mode="HTML"
            )
            return

    # FIX: order_counter با lock امن است
    global order_counter
    async with order_lock:
        order_counter += 1
        order_id = f"ORD-{order_counter:04d}"

    plan_key = context.user_data.get("plan", "نامشخص")
    plan_price = context.user_data.get("plan_price", 0)
    server_type = context.user_data.get("server_type", "Cloudflare")

    user = update.effective_user
    orders[order_id] = {
        "order_id": order_id,
        "user_id": user.id,
        "username": user.username or "بدون نام کاربری",
        "name": user.full_name or "نامشخص",
        "plan": plan_key,
        "price": plan_price,
        "status": "pending",
        "date": datetime.now().isoformat(),
        "receipt_photo": None,
        "server_type": server_type,
    }

    active_receipts[user_id] = order_id
    context.user_data["current_order_id"] = order_id

    # FIX: مسیر مطلق برای ذخیره رسید
    photo_path = os.path.join(RECEIPTS_DIR, f"{order_id}_{user_id}.jpg")
    os.makedirs(RECEIPTS_DIR, exist_ok=True)

    photo_file = await update.message.photo[-1].get_file()
    await photo_file.download_to_drive(photo_path)

    orders[order_id]["receipt_photo"] = photo_path
    save_data()

    # FIX: callback_data حاوی order_id برای جلوگیری از تداخل
    admin_keyboard = [
        [InlineKeyboardButton("✅ تأیید", callback_data=f"confirm_order_{order_id}")],
        [InlineKeyboardButton("❌ رد", callback_data=f"reject_order_{order_id}")],
    ]

    price_str = f"{plan_price:,}".replace(",", "٬")
    receipt_text = (
        f"📦 <b>سفارش جدید: {order_id}</b>\n\n"
        f"👤 <b>کاربر:</b> @{user.username or 'بدون نام'} | ID: <code>{user.id}</code>\n"
        f"📋 <b>پلن:</b> {plan_key}\n"
        f"💰 <b>مبلغ:</b> {price_str} تومان\n"
        f"📅 <b>تاریخ:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        f"📸 رسید پرداخت:"
    )

    try:
        with open(photo_path, "rb") as pf:
            await context.bot.send_photo(
                chat_id=ADMIN_ID,
                photo=pf,
                caption=receipt_text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(admin_keyboard),
            )
    except Exception as e:
        logger.error(f"خطا در ارسال رسید به ادمین: {e}")

    user_states[user_id] = "idle"
    context.user_data.clear()

    await update.message.reply_text(
        "✅ <b>رسید شما با موفقیت ارسال شد.</b>\n\n"
        f"🔖 شماره سفارش: <code>{order_id}</code>\n\n"
        "⏳ پس از بررسی توسط ادمین، کانفیگ شما ارسال خواهد شد.\n"
        "معمولاً کمتر از ۳۰ دقیقه طول می‌کشد.",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )


# ═══════════════════════════════════════════════
# ⚡️ درباره سرور
# ═══════════════════════════════════════════════
async def show_about_server(query):
    msg = (
        "⚡️ <b>درباره سرورهای اینترنت آزاد³⁶۹</b>\n\n"
        "🔒 <b>پروتکل:</b> VLESS / VMESS روی Cloudflare\n"
        "🌍 <b>لوکیشن سرور:</b> اروپا (آلمان / هلند)\n"
        "👥 <b>ظرفیت هر سرور:</b> ۲۰ کاربر اختصاصی\n"
        "⏱ <b>آپتایم:</b> بیش از ۹۹٪\n\n"
        "📦 <b>پلن‌های موجود:</b>\n"
        + "\n".join([
            f"   • {key}: {info['price']:,}".replace(",", "٬") + " تومان / ۳۰ روز"
            for key, info in PLANS.items()
        ]) +
        "\n\n🟢 <b>اینترنت آزاد³⁶۹ — تفاوت را احساس کنید.</b>"
    )
    await query.edit_message_text(
        msg,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_menu")]]),
    )


# ═══════════════════════════════════════════════
# 👤 پنل ادمین
# ═══════════════════════════════════════════════
def _build_admin_panel_text():
    pending = sum(1 for o in orders.values() if o["status"] == "pending")
    confirmed = sum(1 for o in orders.values() if o["status"] == "confirmed")
    rejected = sum(1 for o in orders.values() if o["status"] == "rejected")
    delivered = sum(1 for o in orders.values() if o["status"] == "delivered")
    return (
        "👑 <b>پنل ادمین — اینترنت آزاد³⁶۹</b>\n\n"
        "📊 <b>آمار سفارش‌ها:</b>\n"
        f"   ⏳ در انتظار: {pending}\n"
        f"   ✅ تأیید شده: {confirmed}\n"
        f"   ❌ رد شده: {rejected}\n"
        f"   📦 تحویل شده: {delivered}\n\n"
        "📌 از گزینه‌های زیر استفاده کنید:"
    )


def _admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 لیست سفارش‌ها", callback_data="show_orders")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_menu")],
    ])


async def show_admin_panel_query(query):
    await query.edit_message_text(_build_admin_panel_text(), parse_mode="HTML", reply_markup=_admin_keyboard())


async def show_admin_panel_message(message):
    await message.reply_text(_build_admin_panel_text(), parse_mode="HTML", reply_markup=_admin_keyboard())


async def admin_manage_order(query, context, order_id):
    if order_id not in orders:
        await query.edit_message_text("❌ سفارش یافت نشد.")
        return

    order = orders[order_id]
    price_str = f"{order['price']:,}".replace(",", "٬")
    status_map = {
        "pending": "⏳ در انتظار بررسی",
        "confirmed": "✅ تأیید شده",
        "rejected": "❌ رد شده",
        "delivered": "📦 تحویل شده",
    }

    msg = (
        f"📦 <b>جزئیات سفارش: {order_id}</b>\n\n"
        f"👤 <b>کاربر:</b> @{order['username']} | ID: <code>{order['user_id']}</code>\n"
        f"📋 <b>پلن:</b> {order['plan']}\n"
        f"💰 <b>مبلغ:</b> {price_str} تومان\n"
        f"📅 <b>تاریخ:</b> {order['date']}\n"
        f"📊 <b>وضعیت:</b> {status_map.get(order['status'], 'نامشخص')}\n"
    )

    keyboard = []
    if order["status"] == "pending":
        # FIX: order_id در callback_data گنجانده شده تا تداخل نداشته باشد
        keyboard = [
            [InlineKeyboardButton("✅ تأیید", callback_data=f"confirm_order_{order_id}")],
            [InlineKeyboardButton("❌ رد", callback_data=f"reject_order_{order_id}")],
        ]
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="admin_panel")])

    if order.get("receipt_photo") and os.path.exists(order["receipt_photo"]):
        try:
            with open(order["receipt_photo"], "rb") as pf:
                await context.bot.send_photo(
                    chat_id=ADMIN_ID,
                    photo=pf,
                    caption=msg,
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
            await query.edit_message_text("📦 جزئیات سفارش در پیام جدید ارسال شد.", parse_mode="HTML")
        except Exception as e:
            logger.error(f"خطا در ارسال عکس رسید: {e}")
            await query.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await query.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_confirm_order(query, context, order_id):
    if orders[order_id]["status"] != "pending":
        await query.edit_message_text(f"⚠️ سفارش {order_id} قبلاً پردازش شده است.")
        return

    orders[order_id]["status"] = "confirmed"
    save_data()

    user_info = orders[order_id]
    msg = (
        f"✅ <b>سفارش {order_id} تأیید شد.</b>\n\n"
        f"👤 کاربر: @{user_info['username']} | ID: <code>{user_info['user_id']}</code>\n"
        f"📋 پلن: {user_info['plan']}\n\n"
        f"📌 کانفیگ کاربر را <b>فوروارد</b> کنید.\n"
        f"⏰ اگر ظرف ۱۰ دقیقه ارسال نکنید، یادآوری دریافت خواهید کرد."
    )
    await context.bot.send_message(chat_id=ADMIN_ID, text=msg, parse_mode="HTML")

    waiting_for_config[ADMIN_ID] = order_id
    schedule_reminder(context, ADMIN_ID, order_id)
    await query.edit_message_text(f"✅ سفارش {order_id} تأیید شد. لطفاً کانفیگ را فوروارد کنید.", parse_mode="HTML")


async def admin_reject_order(query, context, order_id):
    if orders[order_id]["status"] != "pending":
        await query.edit_message_text(f"⚠️ سفارش {order_id} قبلاً پردازش شده است.")
        return

    orders[order_id]["status"] = "rejected"
    user_id = orders[order_id]["user_id"]

    if user_id in active_receipts:
        del active_receipts[user_id]
    save_data()

    keyboard = [[InlineKeyboardButton("📤 ارسال مجدد رسید", callback_data="retry_receipt")]]
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "❌ <b>رسید شما تأیید نشد.</b>\n\n"
                "📌 سفارش شما لغو شد.\n\n"
                "اگر اشتباهی رخ داده، می‌توانید مجدداً رسید ارسال کنید."
            ),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    except Exception as e:
        logger.error(f"خطا در اطلاع‌رسانی رد سفارش به کاربر: {e}")

    await query.edit_message_text(f"❌ سفارش {order_id} رد شد. کاربر اطلاع‌رسانی شد.", parse_mode="HTML")


# ═══════════════════════════════════════════════
# 📤 ارسال مجدد رسید
# ═══════════════════════════════════════════════
async def retry_receipt(query, context):
    user_id = query.from_user.id

    user_orders = [o for o in orders.values() if o["user_id"] == user_id and o["status"] == "rejected"]
    if not user_orders:
        await query.edit_message_text(
            "⚠️ <b>سفارش رد شده‌ای یافت نشد.</b>\n\n📌 برای خرید جدید، از منوی اصلی اقدام کنید.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_menu")]]),
        )
        return

    last_order = sorted(user_orders, key=lambda o: o["date"])[-1]
    order_id = last_order["order_id"]

    orders[order_id]["status"] = "pending"
    active_receipts[user_id] = order_id
    context.user_data["current_order_id"] = order_id
    context.user_data["plan"] = last_order["plan"]
    context.user_data["plan_price"] = last_order["price"]
    user_states[user_id] = "waiting_receipt"
    save_data()

    price_str = f"{last_order['price']:,}".replace(",", "٬")
    msg = (
        f"📤 <b>ارسال مجدد رسید</b>\n\n"
        f"🔖 سفارش: <code>{order_id}</code>\n"
        f"📋 پلن: {last_order['plan']}\n"
        f"💰 مبلغ: {price_str} تومان\n\n"
        f"لطفاً عکس رسید جدید را همین الان ارسال کنید."
    )
    await query.edit_message_text(msg, parse_mode="HTML")


# ═══════════════════════════════════════════════
# 📋 آرشیو سفارش‌ها
# ═══════════════════════════════════════════════
async def show_all_orders(query, context):
    if not orders:
        await query.edit_message_text(
            "📋 <b>هنوز سفارشی ثبت نشده است.</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")]]),
        )
        return

    status_map = {"pending": "⏳", "confirmed": "✅", "rejected": "❌", "delivered": "📦"}
    orders_text = "📋 <b>لیست سفارش‌ها (جدیدترین اول):</b>\n\n"
    for oid, order in sorted(orders.items(), key=lambda x: x[1]["date"], reverse=True):
        price_str = f"{order['price']:,}".replace(",", "٬")
        status_icon = status_map.get(order["status"], "❓")
        orders_text += f"🔹 <b>{oid}</b> {status_icon}\n"
        orders_text += f"   👤 @{order['username']} | {order['plan']} | {price_str} تومان\n\n"
    orders_text += f"📊 مجموع: {len(orders)} سفارش"

    # FIX: تلگرام حداکثر ۴۰۹۶ کاراکتر در edit قبول می‌کند
    if len(orders_text) > 4000:
        orders_text = orders_text[:3900] + "\n\n... (ادامه دارد)"

    await query.edit_message_text(
        orders_text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")]]),
    )


# ═══════════════════════════════════════════════
# ⏰ سیستم یادآوری
# ═══════════════════════════════════════════════
async def reminder_callback(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    admin_id = job.data.get("admin_id")
    order_id = job.data.get("order_id")

    if admin_id and admin_id in waiting_for_config and waiting_for_config[admin_id] == order_id:
        order = orders.get(order_id, {})
        msg = (
            f"⏰ <b>یادآوری: کانفیگ ارسال نشده!</b>\n\n"
            f"👤 کاربر: @{order.get('username', 'نامشخص')}\n"
            f"📦 سفارش: {order_id}\n"
            f"📋 پلن: {order.get('plan', 'نامشخص')}\n\n"
            f"📌 لطفاً کانفیگ را فوروارد کنید."
        )
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=msg, parse_mode="HTML")
        except Exception as e:
            logger.error(f"خطا در ارسال یادآوری: {e}")


def schedule_reminder(context: ContextTypes.DEFAULT_TYPE, admin_id: int, order_id: str):
    try:
        context.job_queue.run_once(
            reminder_callback,
            when=timedelta(minutes=REMINDER_TIMEOUT_MINUTES),
            data={"admin_id": admin_id, "order_id": order_id},
            name=f"reminder_{order_id}",
        )
        logger.info(f"یادآوری برای سفارش {order_id} تنظیم شد")
    except Exception as e:
        logger.error(f"خطا در تنظیم یادآوری: {e}")


# ═══════════════════════════════════════════════
# 📨 دریافت کانفیگ از ادمین
# ═══════════════════════════════════════════════
async def admin_config_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        return
    if ADMIN_ID not in waiting_for_config:
        return

    order_id = waiting_for_config[ADMIN_ID]
    if order_id not in orders:
        del waiting_for_config[ADMIN_ID]
        return

    target_user_id = orders[order_id]["user_id"]

    try:
        await update.message.forward(chat_id=target_user_id)
        del waiting_for_config[ADMIN_ID]

        orders[order_id]["status"] = "delivered"
        orders[order_id]["delivered_at"] = datetime.now().isoformat()
        save_data()

        await context.bot.send_message(
            chat_id=target_user_id,
            text=(
                "🎉 <b>کانفیگ شما آماده است!</b>\n\n"
                "📱 برای اتصال از یکی از اپ‌های زیر استفاده کنید:\n\n"
                "🔹 <b>v2rayN</b> — ویندوز\n"
                "🔹 <b>v2rayNG</b> — اندروید\n"
                "🔹 <b>Hiddify</b> — همه پلتفرم‌ها\n"
                "🔹 <b>Streisand</b> — iOS\n\n"
                "📌 کانفیگ را import کنید و متصل شوید.\n\n"
                "🟢 <b>اینترنت آزاد³⁶۹ — موفق باشید!</b>"
            ),
            parse_mode="HTML",
        )
        await update.message.reply_text(
            f"✅ کانفیگ برای @{orders[order_id]['username']} ارسال شد.\n"
            f"📦 سفارش {order_id} تحویل داده شد.",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"خطا در ارسال کانفیگ: {e}")
        await update.message.reply_text(f"❌ خطا در ارسال کانفیگ: {e}", parse_mode="HTML")


# ═══════════════════════════════════════════════
# 📨 هندلر پیام‌ها
# ═══════════════════════════════════════════════
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    # ادمین: ارسال کانفیگ
    if user_id == ADMIN_ID:
        if ADMIN_ID in waiting_for_config:
            await admin_config_handler(update, context)
        return

    # کاربر: ارسال رسید عکسی
    if update.message and update.message.photo:
        if user_states.get(user_id) == "waiting_receipt":
            await receive_receipt(update, context)
        else:
            await update.message.reply_text(
                "📌 برای ارسال رسید، ابتدا فرآیند خرید را از منو شروع کنید.",
                parse_mode="HTML",
                reply_markup=get_main_keyboard(),
            )


# ═══════════════════════════════════════════════
# 🔄 هندلر خطا
# ═══════════════════════════════════════════════
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("خطا در پردازش آپدیت:", exc_info=context.error)


# ═══════════════════════════════════════════════
# 🚀 اجرای ربات
# ═══════════════════════════════════════════════
def main() -> None:
    os.makedirs(RECEIPTS_DIR, exist_ok=True)
    load_data()

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, message_handler))
    application.add_error_handler(error_handler)

    logger.info("🚀 ربات اینترنت آزاد³⁶۹ در حال اجرا...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
