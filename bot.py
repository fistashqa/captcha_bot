import logging
import os
import asyncio
from time import time
from flask import Flask, request
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions
from telegram.ext import Application, ChatMemberHandler, CallbackQueryHandler, ContextTypes
from telegram.ext import ApplicationBuilder
from telegram.request import HTTPXRequest

# Константы
TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # В формате https://yourdomain.com/<secret_path>
CAPTCHA_OPTIONS = ["🥩", "🍆", "💦", "🧬"]
CORRECT_ANSWER = "🍆"
CAPTCHA_TIMEOUT = int(os.getenv("CAPTCHA_TIMEOUT", 60))
BAN_DURATION = int(os.getenv("BAN_DURATION", 30 * 60))

if not TOKEN or not WEBHOOK_URL:
    raise RuntimeError("BOT_TOKEN и/или WEBHOOK_URL не заданы!")

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

pending_captcha = {}

app = Flask(__name__)

@app.route('/')
def health_check():
    return 'Bot is alive!'

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot.application.bot)
    asyncio.run(bot.application.process_update(update))
    return "OK"

# Капча при входе
async def on_user_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_member = update.chat_member
    user = chat_member.new_chat_member.user
    chat_id = chat_member.chat.id

    if chat_member.old_chat_member.status in ("left", "kicked") and chat_member.new_chat_member.status == "member":
        logger.info(f"{user.full_name} зашел в чат {chat_id}")

        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user.id,
            permissions=ChatPermissions(can_send_messages=False)
        )

        keyboard = InlineKeyboardMarkup.from_column([
            InlineKeyboardButton(text=opt, callback_data=f"captcha:{user.id}:{opt}")
            for opt in CAPTCHA_OPTIONS
        ])

        message = await context.bot.send_message(
            chat_id=chat_id,
            text=f"🔹 {user.first_name}, Нажми на 🍆, иначе 30 мин в бан.",
            reply_markup=keyboard,
        )

        async def captcha_timeout():
            await asyncio.sleep(CAPTCHA_TIMEOUT)
            if user.id in pending_captcha:
                await context.bot.ban_chat_member(chat_id, user.id, until_date=int(time() + BAN_DURATION))
                await context.bot.send_message(chat_id, text=f"💥 {user.first_name} не прошёл капчу, бан.")
                del pending_captcha[user.id]

        pending_captcha[user.id] = {
            "task": asyncio.create_task(captcha_timeout())
        }

# Ответ на капчу
async def captcha_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split(":")
    if len(data) != 3:
        return

    _, user_id_str, selected = data
    user_id = int(user_id_str)

    if query.from_user.id != user_id:
        await query.edit_message_text("братишка, это не твоя капча")
        return

    chat_id = query.message.chat.id

    if selected == CORRECT_ANSWER:
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(can_send_messages=True)
        )
        await query.edit_message_text("✅ Принят!")
    else:
        await context.bot.ban_chat_member(chat_id, user_id, until_date=int(time() + BAN_DURATION))
        await query.edit_message_text("❌ Мимо. Отдыхай 30 минут.")

    if user_id in pending_captcha:
        pending_captcha[user_id]["task"].cancel()
        del pending_captcha[user_id]

# Запуск приложения и настройка webhook
async def setup():
    request = HTTPXRequest()
    global bot
    bot = ApplicationBuilder().token(TOKEN).request(request).build()

    bot.add_handler(ChatMemberHandler(on_user_join, chat_member_types=["member"]))
    bot.add_handler(CallbackQueryHandler(captcha_response, pattern=r"^captcha:\d+:.+"))

    await bot.initialize()
    await bot.bot.set_webhook(url=f"{WEBHOOK_URL}/{TOKEN}")
    await bot.start()
    logger.info("Webhook установлен и бот запущен")

if __name__ == "__main__":
    asyncio.run(setup())
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
