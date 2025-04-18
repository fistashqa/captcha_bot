import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions
from telegram.ext import Application, ChatMemberHandler, CallbackQueryHandler, ContextTypes
from telegram.request import HTTPXRequest
from telegram.error import RetryAfter
import os
from time import time
import asyncio

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Получение токена и URL вебхука
TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 8080))

if not TOKEN:
    logger.error("BOT_TOKEN не задан! Завершаю работу.")
    exit(1)
if not WEBHOOK_URL:
    logger.error("WEBHOOK_URL не задан! Завершаю работу.")
    exit(1)

# Константы капчи
CAPTCHA_OPTIONS = ["🥩", "🍆", "💦", "🧼"]
CORRECT_ANSWER = "🍆"
CAPTCHA_TIMEOUT = int(os.getenv("CAPTCHA_TIMEOUT", 60))
BAN_DURATION = int(os.getenv("BAN_DURATION", 30 * 60))

# Словарь для хранения данных капчи
pending_captcha = {}

async def on_user_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def set_webhook_with_retry(bot, webhook_url, max_attempts=5):
    attempt = 0
    while attempt < max_attempts:
        try:
            logger.info(f"Попытка {attempt + 1} установить вебхук...")
            await bot.set_webhook(url=webhook_url)
            logger.info("Вебхук успешно установлен")
            return True
        except RetryAfter as e:
            logger.warning(f"Лимит запросов превышен, жду {e.retry_after} секунд...")
            await asyncio.sleep(e.retry_after)
            attempt += 1
        except Exception as e:
            logger.error(f"Ошибка установки вебхука: {e}")
            return False
    logger.error("Не удалось установить вебхук после всех попыток")
    return False

async def main():
    request = HTTPXRequest(
        connection_pool_size=10,
        read_timeout=30.0,
        connect_timeout=30.0,
        pool_timeout=30.0,
        http_version="1.1"
    )
    application = Application.builder().token(TOKEN).request(request).build()
    application.add_handler(ChatMemberHandler(on_user_join, chat_member_types=["member"]))
    application.add_handler(CallbackQueryHandler(captcha_response, pattern=r"^captcha:\d+:.+"))

    logger.info("Устанавливаю вебхук...")
    if not await set_webhook_with_retry(application.bot, WEBHOOK_URL):
        logger.error("Не удалось запустить бота из-за ошибки вебхука")
        return

    logger.info("Бот стартует в режиме вебхука...")
    try:
        await application.initialize()
        await application.start()
        await application.updater.start_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path="/webhook",
            webhook_url=WEBHOOK_URL
        )
        logger.info("Бот полностью запущен и ожидает обновления")
        # Бесконечное ожидание для поддержания работы
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        logger.info("Получен сигнал завершения, останавливаю бота...")
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        raise
    finally:
        logger.info("Останавливаю приложение...")
        await application.stop()
        await application.shutdown()

if __name__ == "__main__":
    # Используем new_event_loop вместо get_event_loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    except RuntimeError as e:
        if "This event loop is already running" in str(e):
            logger.info("Событийный цикл уже запущен, добавляю задачу...")
            loop.create_task(main())
            loop.run_forever()
        else:
            raise
    except KeyboardInterrupt:
        logger.info("Получен сигнал завершения программы")
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
        logger.info("Событийный цикл завершён")
