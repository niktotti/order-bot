import os
import re
import logging
from datetime import datetime
import tempfile
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, Bot
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, ContextTypes, filters
)
import gspread

# ------------------ Настройки ------------------
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
MANAGER_CHAT_ID = os.getenv("MANAGER_CHAT_ID")
SPREADSHEET_NAME = os.getenv("SPREADSHEET_NAME", "iPhone17_Orders")

if not TOKEN:
    raise RuntimeError("Не найден BOT_TOKEN в .env")

if MANAGER_CHAT_ID:
    try:
        MANAGER_CHAT_ID = int(MANAGER_CHAT_ID)
    except Exception:
        logging.warning("MANAGER_CHAT_ID некорректен")
        MANAGER_CHAT_ID = None

# ------------------ Google Sheets через переменную окружения ------------------
GOOGLE_JSON_CONTENT = os.getenv("GOOGLE_JSON_CONTENT")
if GOOGLE_JSON_CONTENT:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
    tmp.write(GOOGLE_JSON_CONTENT.encode())
    tmp.close()
    GOOGLE_JSON_PATH = tmp.name
else:
    GOOGLE_JSON_PATH = "google.json"

try:
    gc = gspread.service_account(filename=GOOGLE_JSON_PATH)
    sheet = gc.open(SPREADSHEET_NAME).sheet1
    print("✅ Google Sheets подключена")
except Exception as e:
    logging.warning("Ошибка подключения к Google Sheets: %s", e)
    sheet = None

# ------------------ Сцены ------------------
CHOOSING, MODEL, MEMORY, COLOR, CONFIRM, CONTACT = range(6)
MODELS = ["iPhone 17", "iPhone 17 Pro", "iPhone 17 Pro Max", "iPhone 17 Air"]

MEMORY_BY_MODEL = {
    "iPhone 17": ["256GB", "512GB"],
    "iPhone 17 Pro": ["256GB", "512GB", "1TB"],
    "iPhone 17 Pro Max": ["256GB", "512GB", "1TB", "2TB"],
    "iPhone 17 Air": ["256GB", "512GB", "1TB"],
}

COLOR_BY_MODEL = {
    "iPhone 17": ["Black", "White", "Sage", "Mist Blue", "Lavender"],
    "iPhone 17 Pro": ["Silver", "Cosmic Orange", "Deep Blue"],
    "iPhone 17 Pro Max": ["Silver", "Cosmic Orange", "Deep Blue"],
    "iPhone 17 Air": ["Sky Blue", "Light Gold", "Cloud White", "Space Black"],
}

COLOR_IMAGES = {
    "iPhone 17": "images/iphone17.png",
    "iPhone 17 Air": "images/iphone17_air.png",
    "iPhone 17 Pro": "images/iphone17_pro.png",
    "iPhone 17 Pro Max": "images/iphone17_pro_max.png",
}

logging.basicConfig(level=logging.INFO)

# ------------------ Webhook cleanup ------------------
bot = Bot(TOKEN)
try:
    bot.delete_webhook()
    print("✅ Удалены все существующие webhooks, можно запускать polling")
except Exception as e:
    logging.warning(f"Не удалось удалить webhook: {e}")

# ------------------ Клавиатуры ------------------
def build_model_kb():
    kb = [[InlineKeyboardButton(m, callback_data=f"model_{i}")] for i, m in enumerate(MODELS)]
    return InlineKeyboardMarkup(kb)

def build_multi_kb(options, selected_set, prefix="opt"):
    kb = []
    for opt in options:
        text = ("✅ " if opt in selected_set else "") + opt
        cb = f"{prefix}_{opt}".replace(" ", "_")
        kb.append([InlineKeyboardButton(text, callback_data=cb)])
    kb.append([InlineKeyboardButton("Готово", callback_data=f"{prefix}_done")])
    return InlineKeyboardMarkup(kb)

def post_order_menu():
    kb = [
        [InlineKeyboardButton("📱 Новый предзаказ", callback_data="new_order")],
        [InlineKeyboardButton("📞 Связаться с менеджером", callback_data="contact_manager")],
        [InlineKeyboardButton("🔥 Акции", callback_data="show_sales")],
        [InlineKeyboardButton("ℹ️ О магазине", callback_data="about_shop")]
    ]
    return InlineKeyboardMarkup(kb)

# ------------------ Хендлеры ------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Запустить", callback_data="start_order")]])
    await update.message.reply_text(
        "👋 Добро пожаловать в магазин *TechStore*!\n\n"
        "Этот бот поможет вам оформить предзаказ на новый *iPhone 17* 📱.\n\n"
        "Нажмите кнопку, чтобы начать 🚀",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    return CHOOSING

# --- остальные cb_start_order, cb_choose_model, cb_memory, cb_color аналогично твоему коду ---

# ------------------ Контакт и проверка телефона ------------------
PHONE_RE = re.compile(r"(?:\+7|8)?(\d{10})")

async def cb_confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "✍️ Пожалуйста, введите ваше *ФИО* и *номер телефона* в одной строке.\n\nПример: Иванов Иван +79001234567",
        parse_mode="Markdown"
    )
    return CONTACT

async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    digits_only = re.sub(r"\D", "", text)
    m = PHONE_RE.search(digits_only)
    if not m:
        await update.message.reply_text(
            "⚠️ Введите корректный номер телефона вместе с ФИО.\n"
            "Допустимые форматы:\n"
            "+7XXXXXXXXXX\n8XXXXXXXXXX\nXXXXXXXXXX (10 цифр)\nПример: Иванов Иван +79001234567"
        )
        return CONTACT

    digits = m.group(1)
    phone = "+7" + digits[-10:]  # нормализуем к +7XXXXXXXXXX

    fio = re.sub(r"\+?\d[\d\s\-()]+", "", text).strip()
    user = update.message.from_user
    nick = f"@{user.username}" if user.username else f"{user.first_name or ''} {user.last_name or ''}".strip() or str(user.id)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    model = context.user_data["model"]
    memory = ", ".join(sorted(context.user_data["memory"]))
    colors = ", ".join(sorted(context.user_data["colors"]))

    if sheet:
        try:
            sheet.append_row([nick, phone, now, fio, model, memory, colors])
        except Exception as e:
            logging.warning("Ошибка при записи в Google Sheets: %s", e)

    from telegram.helpers import escape_markdown
    msg = (
        f"📦 *Новый предзаказ!*\n\n"
        f"👤 Пользователь: {nick}\n"
        f"📇 ФИО: {fio}\n"
        f"📞 Телефон: {phone}\n"
        f"📱 Модель: {model}\n"
        f"💾 Память: {memory}\n"
        f"🎨 Цвет: {colors}\n"
        f"🕒 Дата: {now}"
    )
    msg_safe = escape_markdown(msg, version=2)

    if MANAGER_CHAT_ID:
        try:
            await context.bot.send_message(chat_id=MANAGER_CHAT_ID, text=msg_safe, parse_mode="MarkdownV2")
        except Exception as e:
            logging.warning(f"Не удалось отправить сообщение менеджеру: {e}")

    await update.message.reply_text(
        "🚀 Спасибо! Мы сохранили ваш заказ 🎉\nМенеджеры скоро свяжутся с вами 📞",
        reply_markup=post_order_menu(),
        parse_mode="Markdown"
    )
    context.user_data.clear()
    return ConversationHandler.END

# ------------------ Запуск ------------------
def main():
    app = Application.builder().token(TOKEN).build()

    # Добавляешь все свои хендлеры и ConversationHandler здесь, как в текущем коде
    # ...

    print("🤖 Бот запущен — polling активен")
    app.run_polling()

if __name__ == "__main__":
    main()