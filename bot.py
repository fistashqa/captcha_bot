import os
import asyncio
import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, ChatMemberHandler, ContextTypes

PENDING_USERS = {}

CAPTCHA_OPTIONS = ["🧢", "💣", "🔫", "🍆"]
CORRECT_ANSWER = "🍆"
TIMEOUT_SECONDS = 60
BAN_DURATION_SECONDS = 1800  # 30 минут

async def on_user_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member = update.chat_member
    if member.new_chat_member.status == "member":
        user_id = member.new_chat_member.user.id
        chat_id = member.chat.id

        keyboard = [
            [InlineKeyboardButton(emoji, callback_data=f"{user_id}:{emoji}") for emoji in CAPTCHA_OPTIONS[:2]],
            [InlineKeyboardButton(emoji, callback_data=f"{user_id}:{emoji}") for emoji in CAPTCHA_OPTIONS[2:]],
        ]

        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"🚪 {member.new_chat_member.user.mention_html()} ворвался в чат!\n\n"
                 f"🧠 Чтобы доказать, что ты не ботяра сильвер — нажми на 🍆.\n"
                 f"У тебя 60 секунд, бро...",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

        # Запретить отправку сообщений до прохождения капчи
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(can_send_messages=False)
        )

        PENDING_USERS[user_id] = {
            "chat_id": chat_id,
            "message_id": msg.message_id
        }

        await asyncio.sleep(TIMEOUT_SECONDS)

        # По истечении времени — бан
        if user_id in PENDING_USERS:
            until = datetime.datetime.now() + datetime.timedelta(seconds=BAN_DURATION_SECONDS)
            await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id, until_date=until)
            await context.bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
            del PENDING_USERS[user_id]

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id_str, choice = query.data.split(":")
    user_id = int(user_id_str)
    from_user = query.from_user

    if from_user.id != user_id:
        await query.answer("🛑 братишка, я понимаю что очень хочется, но не трогай чужую 🍆", show_alert=True)
        return

    data = PENDING_USERS.get(user_id)
    if not data:
        return

    chat_id = data["chat_id"]
    msg_id = data["message_id"]

    if choice == CORRECT_ANSWER:
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
        await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        del PENDING_USERS[user_id]
        await context.bot.send_message(chat_id=chat_id, text=f"✅ {from_user.first_name} прошёл капчу! Welcome, боец 🔫")
    else:
        until = datetime.datetime.now() + datetime.timedelta(seconds=BAN_DURATION_SECONDS)
        await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id, until_date=until)
        await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        del PENDING_USERS[user_id]
        await context.bot.send_message(chat_id=chat_id, text=f"❌ {from_user.first_name} не прошёл проверку на 🍆.\nОтдыхай 30 мин в бане, братан...")

app = ApplicationBuilder().token(os.environ["BOT_TOKEN"]).build()
app.add_handler(ChatMemberHandler(on_user_join, chat_member_types=["member"]))
app.add_handler(CallbackQueryHandler(handle_button))
app.run_polling()
print("Бот стартует...")
