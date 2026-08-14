import os
import asyncio
import requests
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from motor.motor_asyncio import AsyncIOMotorClient

# ================= CONFIGURATION =================
BOT_TOKEN = "8280957760:AAHcUGZEwCMWMI42qSLrwrgaFe-F_M9OKgQ"
MONGO_URI = "mongodb+srv://<db_username>:MfUnSMOIwDJL1ISu@cluster0.vprnblv.mongodb.net/?appName=Cluster0" # Ensure password is correct
ADMIN_ID = 7189814021  # Your Telegram User ID
CHANNELS = ["@flix_num_to_info"] # Force Join Channel

# API Config
API_TOKEN = "@ONE_OF_ALL_OWNER1"
API_URL = "https://spyshadow.site/selling-apis/tg-to-num.php"

# Branding (Add as many lines as you like)
BRANDING = [
    "🚀 OSINT BOT SERVICES",
    "📢 Updates: @flix_num_to_info",
    "👤 Support: @Yflix_num_to_info"
]
# =================================================

# --- Flask Dummy Server for Render ---
server = Flask('')
@server.route('/')
def home(): return "Bot is Alive!"

def run_flask():
    server.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# --- Database Setup ---
client = AsyncIOMotorClient(MONGO_URI)
db = client['osint_database']
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

# --- Force Join Check ---
async def check_joined(bot, user_id):
    for channel in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in [constants.ChatMemberStatus.LEFT, constants.ChatMemberStatus.BANNED]:
                return False
        except: return False
    return True

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await get_user(update.effective_user.id)
    welcome = (
        "👋 **Welcome to Telegram OSINT Bot**\n\n"
        "Use `/tg <userid>` to search.\n\n"
        "💰 **Premium:** 50rs / week\n"
        "Verify your join below to start!"
    )
    btn = [[InlineKeyboardButton("Join Channel", url=f"https://t.me/{c.replace('@','')}") for c in CHANNELS]]
    await update.message.reply_text(welcome, reply_markup=InlineKeyboardMarkup(btn), parse_mode="Markdown")

async def tg_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not await check_joined(context.bot, user_id):
        await update.message.reply_text("❌ Please join our channels first to use the bot!")
        return

    if not context.args:
        await update.message.reply_text("❌ Usage: `/tg 8370153065`", parse_mode="Markdown")
        return

    target_id = context.args[0]
    user = await get_user(user_id)
    limit = await get_daily_limit()
    
    # Premium check
    is_premium = user.get("is_premium", False)
    if is_premium and user["premium_expiry"] < datetime.now():
        await users_col.update_one({"user_id": user_id}, {"$set": {"is_premium": False}})
        is_premium = False

    # Credit check
    today = datetime.now().strftime("%Y-%m-%d")
    if not is_premium:
        if user["last_search_date"] != today:
            await users_col.update_one({"user_id": user_id}, {"$set": {"daily_searches": 0, "last_search_date": today}})
            searches_done = 0
        else:
            searches_done = user["daily_searches"]

        if searches_done >= limit:
            await update.message.reply_text(f"🚫 Daily Limit Reached ({limit}/{limit})\nBuy Premium for Unlimited: /buypremium")
            return

    # API Request
    status = await update.message.reply_text("🔎 Fetching data...")
    try:
        res = requests.get(f"{API_URL}?token={API_TOKEN}&q={target_id}", timeout=20)
        data = res.text

        # Deduct credit if successful
        if not is_premium:
            await users_col.update_one({"user_id": user_id}, {"$inc": {"daily_searches": 1}})

        branding_text = "\n".join(BRANDING)
        response_msg = (
            f"✅ **Search Result for** `{target_id}`\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"{data}\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"{branding_text}"
        )
        await status.edit_text(response_msg, parse_mode="Markdown")
    except:
        await status.edit_text("❌ API Error. Try again later.")

async def buy_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"💎 **Premium Membership**\n\nPrice: 50rs / 1 week\nUnlimited Searches & Priority Support.\n\nContact: {BRANDING[-1].split()[-1]}", parse_mode="Markdown")

# --- Admin ---
async def add_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        uid, days = int(context.args[0]), int(context.args[1])
        exp = datetime.now() + timedelta(days=days)
        await users_col.update_one({"user_id": uid}, {"$set": {"is_premium": True, "premium_expiry": exp}}, upsert=True)
        await update.message.reply_text(f"✅ User {uid} added for {days} days.")
    except: await update.message.reply_text("`/add_premium <id> <days>`")

async def set_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        lim = int(context.args[0])
        await settings_col.update_one({"type": "config"}, {"$set": {"daily_limit": lim}}, upsert=True)
        await update.message.reply_text(f"✅ Daily limit set to {lim}")
    except: await update.message.reply_text("`/set_limit <num>`")

# --- Background Task ---
async def expiry_task(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    # Expire users
    expired = users_col.find({"is_premium": True, "premium_expiry": {"$lt": now}})
    async for u in expired:
        await users_col.update_one({"user_id": u['user_id']}, {"$set": {"is_premium": False}})
        try: await context.bot.send_message(u['user_id'], "⚠️ Your premium plan has expired.")
        except: pass

# --- Main ---
if __name__ == "__main__":
    # Start Dummy Server
    Thread(target=run_flask).start()
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.job_queue.run_repeating(expiry_task, interval=3600, first=10)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tg", tg_search))
    app.add_handler(CommandHandler("buypremium", buy_premium))
    app.add_handler(CommandHandler("add_premium", add_premium))
    app.add_handler(CommandHandler("set_limit", set_limit))

    print("Bot is starting...")
    app.run_polling()
