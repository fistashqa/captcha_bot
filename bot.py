import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions
from telegram.ext import Application, ChatMemberHandler, CallbackQueryHandler, ContextTypes
import os
import asyncio
from time import time

TOKEN = os.getenv("BOT_TOKEN")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

pending_captcha = {}
CAPTCHA_OPTIONS = ["🥩", "🍆", "💦", "🧼"]
CORRECT_ANSWER = "🍆"
CAPTCHA_TIMEOUT = 60
BAN_DURATION = 30 * 60

async def on_user_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not TOKEN:
        logger.error("BOT_TOKEN не задан!")
        return

    chat_member = update.chat_member
    user = chat_member.new_chat_member.user
    chat_id = chat_member.chat.id

    if chat_member.old_chat_member.status in ("left", "kicked") and chat_member.new_chat_member.status == "member":
        logger.info(f"{user.full_name} зашел в чат {chat_id}")

        try:
            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user.id,
                permissions=ChatPermissions(can_send_messages=False)
            )
        except Exception as e:
            logger.error(f"Ошибка ограничения прав {user.id}: {e}")
            return

        keyboard = InlineKeyboardMarkup.from_column([
            InlineKeyboardButton(text=opt, callback_data=f"captcha:{user.id}:{opt}")
            for opt in CAPTCHA_OPTIONS
        ])

        try:
            message = await context.bot.send_message(
                chat_id=chat_id,
                text=f"🕹️ {user.first_name}, Чтобы доказать, что ты не ботяра сильвер — нажми на 🍆.\n"
                     f"Выбери правильный предмет, иначе улетишь *в баню* попариться!",
                reply_markup=keyboard,
            )
        except Exception as e:
            logger.error(f"Ошибка отправки капчи {user.id}: {e}")
            return

        async def captcha_timeout():
            await asyncio.sleep(CAPTCHA_TIMEOUT)
            if user.id in pending_captcha:
                try:
                    await context.bot.ban_chat_member(
                        chat_id=chat_id,
                        user_id=user.id,
                        until_date=int(time() + BAN_DURATION)
                    )
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"💥 {user.first_name} не прошёл капчу и был отправлен на 30 минут в гачи-тренажёрку."
                    )
                except Exception as e:
                    logger.error(f"Ошибка бана {user.id}: {e}")
                del pending_captcha[user.id]

        pending_captcha[user.id] = {
            "message_id": message.message_id,
            "chat_id": chat_id,
            "task": asyncio.create_task(captcha_timeout())
        }

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

    try:
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
            await context.bot.ban_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                until_date=int(time() + BAN_DURATION)
            )
            await query.edit_message_text("🚫 Мимо бро, зачилься на пол часика...")
    except Exception as e:
        logger.error(f"Ошибка обработки ответа капчи {user_id}: {e}")

    if user_id in pending_captcha:
        pending_captcha[user_id]["task"].cancel()
        del pending_captcha[user_id]

async def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(ChatMemberHandler(on_user_join, chat_member_types=["member"]))
    application.add_handler(CallbackQueryHandler(captcha_response, pattern=r"^captcha:\d+:.+"))
    logger.info("Бот стартует...")
    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
