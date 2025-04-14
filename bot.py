import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions
from telegram.ext import Application, ChatMemberHandler, CallbackQueryHandler, ContextTypes
import os
import asyncio

TOKEN = os.getenv("BOT_TOKEN")  # На Railway нужно выставить переменную окружения BOT_TOKEN

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Запоминаем пользователей, ожидающих капчу
pending_captcha = {}

CAPTCHA_OPTIONS = ["🥩", "🍆", "💦", "🧼"]
CORRECT_ANSWER = "🍆"
CAPTCHA_TIMEOUT = 60  # секунд
BAN_DURATION = 30 * 60  # 30 минут

async def on_user_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_member = update.chat_member
    user = chat_member.new_chat_member.user
    chat_id = chat_member.chat.id

    if chat_member.old_chat_member.status in ("left", "kicked") and chat_member.new_chat_member.status == "member":
        logger.info(f"{user.full_name} зашел в чат {chat_id}")

        # Блокируем отправку сообщений
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user.id,
            permissions=ChatPermissions(can_send_messages=False)
        )

        # Кнопочная капча
        keyboard = InlineKeyboardMarkup.from_column([
            InlineKeyboardButton(text=opt, callback_data=f"captcha:{user.id}:{opt}")
            for opt in CAPTCHA_OPTIONS
        ])

        message = await context.bot.send_message(
            chat_id=chat_id,
            text=f"🕹️ {user.first_name}, Чтобы доказать, что ты не ботяра сильвер — нажми на 🍆.\n"
                 f"Выбери правильный предмет, иначе улетишь *в баню* попариться!",
            reply_markup=keyboard,
        )

        # Сохраняем ID сообщения и пользователя
        pending_captcha[user.id] = {
            "message_id": message.message_id,
            "chat_id": chat_id
        }

        # Таймер на авто-бан
        await asyncio.sleep(CAPTCHA_TIMEOUT)

        # Если не прошёл капчу за время — бан
        if user.id in pending_captcha:
            await context.bot.ban_chat_member(chat_id=chat_id, user_id=user.id, until_date=asyncio.get_event_loop().time() + BAN_DURATION)
            await context.bot.send_message(chat_id=chat_id, text=f"💥 {user.first_name} не прошёл капчу и был отправлен на 30 минут в гачи-тренажёрку.")
            del pending_captcha[user.id]

async def captcha_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.split(":")
    if len(data) != 3:
        return

    _, user_id_str, selected = data
    user_id = int(user_id_str)

    if query.from_user.id != user_id:
        await query.edit_message_text("братишка, я понимаю что очень хочется, но не трогай чужую 🍆")
        return

    chat_id = query.message.chat.id

    if selected == CORRECT_ANSWER:
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            )
        )
        await query.edit_message_text("✅ Верно! прошёл капчу! Welcome, боец 🔫")
    else:
        await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id, until_date=asyncio.get_event_loop().time() + BAN_DURATION)
        await query.edit_message_text("🚫 Мимо бро, зачилься на пол часика...")

    if user_id in pending_captcha:
        del pending_captcha[user_id]

async def main():
    application = Application.builder().token(TOKEN).build()

    # Хэндлеры
    application.add_handler(ChatMemberHandler(on_user_join, chat_member_types=["member"]))
    application.add_handler(CallbackQueryHandler(captcha_response, pattern=r"^captcha:\d+:.+"))

    logger.info("Бот стартует...")
    await application.run_polling()

if __name__ == "__main__":
    import asyncio

    try:
        asyncio.run(main())
    except RuntimeError as e:
        if str(e).startswith("This event loop is already running"):
            loop = asyncio.get_event_loop()
            loop.create_task(main())
            loop.run_forever()
        else:
            raise
