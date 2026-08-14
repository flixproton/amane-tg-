import asyncio
import requests
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from motor.motor_asyncio import AsyncIOMotorClient

# --- CONFIGURATION ---
BOT_TOKEN = "8280957760:AAHcUGZEwCMWMI42qSLrwrgaFe-F_M9OKgQ"
MONGO_URI = "mongodb+srv://<db_username>:MfUnSMOIwDJL1ISu@cluster0.vprnblv.mongodb.net/?appName=Cluster0"
CHANNELS = ["@flix_num_to_info"]  # Add multiple channel usernames here
ADMIN_ID = 7189814021  # Your Telegram User ID
BRAND_NAME = "🛡️ Telegram OSINT Bot"
OWNER_USERNAME = "@ardgi23"
PREMIUM_PRICE = "50rs for 1 week"

# --- DATABASE SETUP ---
client = AsyncIOMotorClient(MONGO_URI)
db = client['osint_bot_db']
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

# --- FORCE JOIN CHECK ---
async def is_subscribed(bot, user_id):
    for channel in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in [constants.ChatMemberStatus.LEFT, constants.ChatMemberStatus.BANNED]:
                return False
        except Exception:
            return False
    return True

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await get_user(user_id)
    
    welcome_text = (
        f"👋 Welcome to **{BRAND_NAME}**\n\n"
        "I can help you find information using Telegram User IDs.\n\n"
        "📜 **Commands:**\n"
        "🔹 `/tg <userid>` - Search information\n"
        "🔹 `/buypremium` - Get unlimited searches\n"
        "🔹 `/myinfo` - Check your status\n\n"
        "⚠️ *Please make sure you have joined all our channels!*"
    )
    
    # Force Join Buttons
    buttons = [[InlineKeyboardButton(f"Join Channel", url=f"https://t.me/{c.replace('@','')}") for c in CHANNELS]]
    buttons.append([InlineKeyboardButton("✅ Joined / Verify", callback_data="check_joined")])
    
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

async def buy_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        f"💎 **Premium Plan**\n\n"
        f"💰 Price: {PREMIUM_PRICE}\n"
        f"🚀 Benefits: Unlimited Searches, Priority Support.\n\n"
        f"Contact Admin to buy: {OWNER_USERNAME}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def tg_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # 1. Force Join Check
    if not await is_subscribed(context.bot, user_id):
        await update.message.reply_text("❌ You must join all channels to use this command! Use /start to see links.")
        return

    # 2. Argument Check
    if not context.args:
        await update.message.reply_text("❌ Usage: `/tg <userid>`\nExample: `/tg 8370153065`", parse_mode="Markdown")
        return
    
    search_id = context.args[0]
    user = await get_user(user_id)
    
    # 3. Premium/Limit Check
    is_premium = user.get("is_premium", False)
    if is_premium and user["premium_expiry"] < datetime.now():
        await users_col.update_one({"user_id": user_id}, {"$set": {"is_premium": False}})
        is_premium = False

    today = datetime.now().strftime("%Y-%m-%d")
    daily_limit = await get_daily_limit()
    
    if not is_premium:
        if user.get("last_search_date") != today:
            await users_col.update_one({"user_id": user_id}, {"$set": {"daily_searches": 0, "last_search_date": today}})
            current_searches = 0
        else:
            current_searches = user.get("daily_searches", 0)

        if current_searches >= daily_limit:
            await update.message.reply_text(f"🚫 Limit Reached ({daily_limit}/{daily_limit})\nBuy Premium for Unlimited: /buypremium")
            return

    # 4. API Call
    wait_msg = await update.message.reply_text("🔍 Searching database...")
    try:
        api_url = f"https://yash-tg-2-num.alphamovies.workers.dev/?userid={search_id}"
        response = requests.get(api_url, timeout=10).text
        
        # 5. Success - Deduct Credit
        if not is_premium:
            await users_col.update_one({"user_id": user_id}, {"$inc": {"daily_searches": 1}})
            rem = daily_limit - (user.get("daily_searches", 0) + 1)
        else:
            rem = "Unlimited"

        final_reply = (
            f"**{BRAND_NAME} Result**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{response}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 User: {OWNER_USERNAME}\n"
            f"🔋 Searches Left: {rem}"
        )
        await wait_msg.edit_text(final_reply)

    except Exception as e:
        await wait_msg.edit_text("❌ Data not found or API error.")

# --- ADMIN COMMANDS ---
async def set_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        new_limit = int(context.args[0])
        await settings_col.update_one({"type": "config"}, {"$set": {"daily_limit": new_limit}}, upsert=True)
        await update.message.reply_text(f"✅ Daily limit updated to {new_limit}")
    except:
        await update.message.reply_text("Use: /set_limit <number>")

async def add_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        target_id = int(context.args[0])
        days = int(context.args[1])
        expiry = datetime.now() + timedelta(days=days)
        await users_col.update_one({"user_id": target_id}, {"$set": {"is_premium": True, "premium_expiry": expiry}}, upsert=True)
        await update.message.reply_text(f"✅ User {target_id} added to Premium for {days} days.")
    except:
        await update.message.reply_text("Use: /add_premium <userid> <days>")

# --- AUTO EXPIRY TASK ---
async def check_expiry_task(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    # Notice 12h before
    cursor = users_col.find({"is_premium": True, "premium_expiry": {"$gt": now, "$lt": now + timedelta(hours=12)}})
    async for u in cursor:
        try: await context.bot.send_message(u['user_id'], "⚠️ Your premium expires in 12 hours! Renew soon.")
        except: pass
    
    # Expiry
    expired = users_col.find({"is_premium": True, "premium_expiry": {"$lt": now}})
    async for u in expired:
        await users_col.update_one({"user_id": u['user_id']}, {"$set": {"is_premium": False}})
        try: await context.bot.send_message(u['user_id'], "❌ Your premium has expired.")
        except: pass

# --- MAIN ---
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Background job to check expiry every hour
    app.job_queue.run_repeating(check_expiry_task, interval=3600, first=10)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tg", tg_search))
    app.add_handler(CommandHandler("buypremium", buy_premium))
    app.add_handler(CommandHandler("set_limit", set_limit))
    app.add_handler(CommandHandler("add_premium", add_premium))

    print("Bot is running...")
    app.run_polling()
