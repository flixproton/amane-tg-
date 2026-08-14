import asyncio
import requests
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from motor.motor_asyncio import AsyncIOMotorClient

# --- CONFIGURATION ---
BOT_TOKEN = "8280957760:AAHcUGZEwCMWMI42qSLrwrgaFe-F_M9OKgQ"
MONGO_URI = "mongodb+srv://<db_username>:MfUnSMOIwDJL1ISu@cluster0.vprnblv.mongodb.net/?appName=Cluster0"
ADMIN_ID = 7189814021  # Your Telegram ID
CHANNELS = ["@flix_num_to_info"]  # Channels for Force Join

# API Config
API_TOKEN = "@ONE_OF_ALL_OWNER1"
API_BASE_URL = "https://spyshadow.site/selling-apis/tg-to-num.php"

# Branding (Add as many as you want)
BRANDING_LIST = [
    "✨ Powered by OSINT Master",
    "📢 Join: @flix_num_to_info",
    "🛠 Developer: @flix_num_to_info"
]

# --- DATABASE SETUP ---
client = AsyncIOMotorClient(MONGO_URI)
db = client['tg_osint_bot']
users_col = db['users']
settings_col = db['settings']

async def get_daily_limit():
    config = await settings_col.find_one({"type": "config"})
    return config.get("daily_limit", 2) if config else 2

async def get_user(user_id):
    user = await users_col.find_one({"user_id": user_id})
    if not user:
        user = {
            "user_id": user_id,
            "is_premium": False,
            "premium_expiry": None,
            "daily_searches": 0,
            "last_search_date": datetime.now().strftime("%Y-%m-%d")
        }
        await users_col.insert_one(user)
    return user

# --- HELPERS ---
async def check_force_join(bot, user_id):
    for channel in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in [constants.ChatMemberStatus.LEFT, constants.ChatMemberStatus.BANNED]:
                return False
        except: return False
    return True

def get_branding_text():
    return "\n".join(BRANDING_LIST)

# --- BOT HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await get_user(user_id)
    
    welcome_text = (
        "👋 **Welcome to Telegram OSINT Bot**\n\n"
        "To search for a user ID, use the command:\n"
        "👉 `/tg 8370153065`\n\n"
        "**Pricing:**\n"
        "• 2 Free searches daily\n"
        "• Premium: 50rs / week (Unlimited)\n\n"
        "Please join our channels and click 'Verify' to start."
    )
    
    buttons = [[InlineKeyboardButton("Join Channel", url=f"https://t.me/{c.replace('@','')}") for c in CHANNELS]]
    buttons.append([InlineKeyboardButton("✅ Verify Join", callback_data="check")])
    
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

async def tg_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # 1. Force Join Check
    if not await check_force_join(context.bot, user_id):
        await update.message.reply_text("❌ Join all channels first! Use /start to see links.")
        return

    # 2. Argument Check
    if not context.args:
        await update.message.reply_text("❌ Usage: `/tg <userid>`")
        return
    
    target_id = context.args[0]
    user = await get_user(user_id)
    
    # 3. Premium Expiry Check
    is_premium = user.get("is_premium", False)
    if is_premium and user["premium_expiry"] < datetime.now():
        await users_col.update_one({"user_id": user_id}, {"$set": {"is_premium": False}})
        is_premium = False
        await update.message.reply_text("⚠️ Your premium expired. Switched to free plan.")

    # 4. Limit Check
    today = datetime.now().strftime("%Y-%m-%d")
    daily_limit = await get_daily_limit()
    
    if not is_premium:
        if user.get("last_search_date") != today:
            await users_col.update_one({"user_id": user_id}, {"$set": {"daily_searches": 0, "last_search_date": today}})
            searches_done = 0
        else:
            searches_done = user.get("daily_searches", 0)

        if searches_done >= daily_limit:
            await update.message.reply_text(f"🚫 Limit Reached! ({daily_limit}/{daily_limit})\nBuy Premium for unlimited: /buypremium")
            return

    # 5. API Call
    status_msg = await update.message.reply_text("🔎 Searching...")
    try:
        response = requests.get(f"{API_BASE_URL}?token={API_TOKEN}&q={target_id}", timeout=15)
        api_data = response.text
        
        # 6. Deduct Credit
        if not is_premium:
            await users_col.update_one({"user_id": user_id}, {"$inc": {"daily_searches": 1}})
        
        # 7. Format Result
        result_msg = (
            f"📍 **OSINT SEARCH RESULT**\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🔍 **ID:** `{target_id}`\n\n"
            f"{api_data}\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"{get_branding_text()}"
        )
        await status_msg.edit_text(result_msg, parse_mode="Markdown")

    except Exception as e:
        await status_msg.edit_text("❌ API Error or Data Not Found.")

async def buy_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "💎 **Get Premium Membership**\n\n"
        "✅ Unlimited Searches\n"
        "✅ No Daily Limits\n"
        "✅ 1 Week: 50rs\n\n"
        f"Contact Owner to Buy: {BRANDING_LIST[-1].split()[-1]}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

# --- ADMIN COMMANDS ---

async def add_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        uid = int(context.args[0])
        days = int(context.args[1])
        expiry = datetime.now() + timedelta(days=days)
        await users_col.update_one({"user_id": uid}, {"$set": {"is_premium": True, "premium_expiry": expiry}}, upsert=True)
        await update.message.reply_text(f"✅ User {uid} is now Premium for {days} days.")
    except:
        await update.message.reply_text("Usage: `/add_premium <id> <days>`")

async def set_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        limit = int(context.args[0])
        await settings_col.update_one({"type": "config"}, {"$set": {"daily_limit": limit}}, upsert=True)
        await update.message.reply_text(f"✅ Daily limit set to {limit}")
    except:
        await update.message.reply_text("Usage: `/set_limit <number>`")

# --- AUTO TASKS ---

async def check_premium_expiry(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    # Notice 12h before
    reminder_cursor = users_col.find({"is_premium": True, "premium_expiry": {"$gt": now, "$lt": now + timedelta(hours=12)}})
    async for user in reminder_cursor:
        try: await context.bot.send_message(user['user_id'], "⚠️ Your Premium expires in 12 hours. Renew soon!")
        except: pass

    # Perform Expiry
    expired_cursor = users_col.find({"is_premium": True, "premium_expiry": {"$lt": now}})
    async for user in expired_cursor:
        await users_col.update_one({"user_id": user['user_id']}, {"$set": {"is_premium": False}})
        try: await context.bot.send_message(user['user_id'], "❌ Your Premium has expired.")
        except: pass

# --- MAIN RUNNER ---
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Background job
    app.job_queue.run_repeating(check_premium_expiry, interval=3600, first=10)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tg", tg_search))
    app.add_handler(CommandHandler("buypremium", buy_premium))
    app.add_handler(CommandHandler("add_premium", add_premium))
    app.add_handler(CommandHandler("set_limit", set_limit))

    print("Bot started successfully...")
    app.run_polling()
