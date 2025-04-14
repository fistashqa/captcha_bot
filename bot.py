import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions
from telegram.ext import Application, ChatMemberHandler, CallbackQueryHandler, ContextTypes
from telegram.request import HTTPXRequest
import os
from time import time
import asyncio

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Получение токена и URL вебхука
TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Укажи в переменных окружения
PORT = int(os.getenv("PORT", 8080))     # Обычно 8080 для Railway

if not TOKEN:
    logger.error("BOT_TOKEN не задан! Завершаю работу.")
    exit(1)
if not WEBHOOK_URL:
    logger.error("WEBHOOK_URL не задан! Завершаю работу.")
    exit(1)

# Константы капчи
CAPTCHA_OPTIONS = ["🥩", "🍆", "💦", "🧼"]
CORRECT_ANSWER = "🍆"
CAPTCHA_TIMEOUT = int(os.getenv("CAPTCHA_TIMEOUT", 60))  # 60 секунд на ответ
BAN_DURATION = int(os.getenv("BAN_DURATION", 30 * 60))   # 30 минут бана

# Словарь для хранения данных капчи
pending_captcha = {}

async def on_user_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_member = update.chat_member
    user = chat_member.new_chat_member.user
    chat_id = chat_member.chat.id

    # Проверяем, что пользователь только что присоединился
    if chat_member.old_chat_member.status in ("left", "kicked") and chat_member.new_chat_member.status == "member":
        logger.info(f"{user.full_name} зашел в чат {chat_id}")

        # Ограничиваем права новичка
        try:
            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user.id,
                permissions=ChatPermissions(can_send_messages=False)
            )
        except Exception as e:
            logger.error(f"Ошибка ограничения прав {user.id}: {e}")
            return

        # Создаём клавиатуру с вариантами капчи
        keyboard = InlineKeyboardMarkup.from_column([
            InlineKeyboardButton(text=opt, callback_data=f"captcha:{user.id}:{opt}")
            for opt in CAPTCHA_OPTIONS
        ])

        # Отправляем капчу с нашим смешным текстом
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

        # Таймер на прохождение капчи
        async def captcha_timeout():
            try:
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
            except asyncio.CancelledError:
                pass

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

    # Проверяем, что отвечает тот, кому предназначена капча
    if query.from_user.id != user_id:
        await query.edit_message_text("братишка, я понимаю что очень хочется, но не трогай чужую 🍆")
        return

    chat_id = query.message.chat.id

    try:
        if selected == CORRECT_ANSWER:
            # Даём права при правильном ответе
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
            # Баним при неправильном ответе
            await context.bot.ban_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                until_date=int(time() + BAN_DURATION)
            )
            await query.edit_message_text("🚫 Мимо бро, зачилься на пол часика...")
    except Exception as e:
        logger.error(f"Ошибка обработки ответа капчи {user_id}: {e}")

    # Очищаем данные капчи
    if user_id in pending_captcha:
        pending_captcha[user_id]["task"].cancel()
        del pending_captcha[user.id]

async def main():
    # Настройка HTTP-клиента
    request = HTTPXRequest(
        connection_pool_size=10,
        read_timeout=30.0,
        connect_timeout=30.0,
        pool_timeout=30.0,
        http_version="1.1"
    )

    # Создаём приложение
    application = Application.builder().token(TOKEN).request(request).build()

    # Добавляем обработчики
    application.add_handler(ChatMemberHandler(on_user_join, chat_member_types=["member"]))
    application.add_handler(CallbackQueryHandler(captcha_response, pattern=r"^captcha:\d+:.+"))

    # Устанавливаем вебхук
    logger.info("Устанавливаю вебхук...")
    await application.bot.set_webhook(url=WEBHOOK_URL)

    # Запускаем бота в режиме вебхука
    logger.info("Бот стартует в режиме вебхука...")
    await application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="/webhook",
        webhook_url=WEBHOOK_URL
    )

if __name__ == "__main__":
    asyncio.run(main())
