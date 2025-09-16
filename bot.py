import os
import re
import logging
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, ContextTypes, filters
)
import gspread

# ------------------ НАСТРОЙКИ ------------------
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
MANAGER_CHAT_ID = os.getenv("MANAGER_CHAT_ID")
SPREADSHEET_NAME = os.getenv("SPREADSHEET_NAME", "iPhone17_Orders")
GOOGLE_JSON = os.getenv("GOOGLE_JSON", "google.json")

if not TOKEN:
    raise RuntimeError("Не найден BOT_TOKEN в .env")

if MANAGER_CHAT_ID:
    try:
        MANAGER_CHAT_ID = int(MANAGER_CHAT_ID)
    except Exception:
        logging.warning("MANAGER_CHAT_ID некорректен")
        MANAGER_CHAT_ID = None

# Google Sheets
try:
    gc = gspread.service_account(filename=GOOGLE_JSON)
    sheet = gc.open(SPREADSHEET_NAME).sheet1
    print("✅ Google Sheets подключена")
except Exception as e:
    logging.warning("Ошибка подключения к Google Sheets: %s", e)
    sheet = None

# ------------------ Конфиг сцен ------------------
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

async def cb_start_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Выберите модель iPhone:", reply_markup=build_model_kb())
    return MODEL

async def cb_choose_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    idx = int(query.data.split("_")[1])
    model = MODELS[idx]
    context.user_data["model"] = model
    context.user_data["memory"] = set()
    context.user_data["colors"] = set()
    context.user_data["memory_options"] = MEMORY_BY_MODEL[model]
    context.user_data["color_options"] = COLOR_BY_MODEL[model]

    await query.edit_message_text(
        f"Вы выбрали: *{model}* ✅\n\nТеперь выберите объём памяти (можно несколько):",
        reply_markup=build_multi_kb(context.user_data["memory_options"], context.user_data["memory"], prefix="mem"),
        parse_mode="Markdown"
    )
    return MEMORY

async def cb_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    memory_options = context.user_data["memory_options"]

    if data.endswith("_done"):
        model = context.user_data["model"]
        photo_path = COLOR_IMAGES.get(model)
        if photo_path and os.path.exists(photo_path):
            with open(photo_path, "rb") as photo:
                sent_photo = await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=photo,
                    caption=f"🎨 Доступные цвета для {model}:"
                )
            context.user_data["color_photo_id"] = sent_photo.message_id

        await query.message.reply_text(
            "Теперь выберите цвет (можно несколько):",
            reply_markup=build_multi_kb(context.user_data["color_options"], context.user_data["colors"], prefix="col")
        )
        return COLOR
    else:
        opt = data.split("_", 1)[1].replace("_", " ")
        sel = context.user_data.setdefault("memory", set())
        if opt in sel:
            sel.remove(opt)
        else:
            sel.add(opt)
        await query.edit_message_reply_markup(reply_markup=build_multi_kb(memory_options, sel, prefix="mem"))
        return MEMORY

async def cb_color(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    color_options = context.user_data["color_options"]

    if query.data.endswith("_done"):
        photo_id = context.user_data.pop("color_photo_id", None)
        if photo_id:
            try:
                await context.bot.delete_message(chat_id=query.message.chat_id, message_id=photo_id)
            except Exception:
                pass

        model = context.user_data["model"]
        mem = ", ".join(sorted(context.user_data["memory"])) or "(не выбрано)"
        cols = ", ".join(sorted(context.user_data["colors"])) or "(не выбрано)"
        summary = f"Ваш выбор:\n📱 {model}\n💾 {mem}\n🎨 {cols}"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Подтвердить заказ", callback_data="confirm_order")],
            [InlineKeyboardButton("✏️ Изменить выбор", callback_data="edit_order")]
        ])
        await query.edit_message_text(summary, reply_markup=kb)
        return CONFIRM
    else:
        opt = query.data.split("_", 1)[1].replace("_", " ")
        sel = context.user_data.setdefault("colors", set())
        if opt in sel:
            sel.remove(opt)
        else:
            sel.add(opt)
        await query.edit_message_reply_markup(reply_markup=build_multi_kb(color_options, sel, prefix="col"))
        return COLOR

# ------------------ Контакт и проверка телефона ------------------
PHONE_RE = re.compile(r"(\+?\d[\d\s\-()]{5,}\d)")

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
    m = PHONE_RE.search(text)
    if not m:
        await update.message.reply_text(
            "⚠️ Введите корректный номер телефона вместе с ФИО.\nПример: Иванов Иван +79001234567"
        )
        return CONTACT

    phone = m.group(1).strip()
    fio = text.replace(m.group(1), "").strip()
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

    if MANAGER_CHAT_ID:
        try:
            await context.bot.send_message(chat_id=MANAGER_CHAT_ID, text=msg, parse_mode="Markdown")
        except Exception:
            pass

    await update.message.reply_text(
        "🚀 Спасибо! Мы сохранили ваш заказ 🎉\nМенеджеры скоро свяжутся с вами 📞",
        reply_markup=post_order_menu(),
        parse_mode="Markdown"
    )
    context.user_data.clear()
    return ConversationHandler.END

# ------------------ Кнопки после заказа ------------------
async def cb_edit_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔄 Давайте пересчитаем заново!\n\nВыберите модель:", reply_markup=build_model_kb())
    return MODEL

async def cb_contact_manager(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "📞 Связаться с менеджером:\nТелефон: +7 (900) 123-45-67\nTelegram: @manager\nEmail: support@techstore.com"
    await query.message.reply_text(text, reply_markup=post_order_menu())

async def cb_show_sales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "🔥 Текущие акции:\n- Скидка 20% на аксессуары при предзаказе\n- Рассрочка 0% на 6 месяцев"
    await query.message.reply_text(text, reply_markup=post_order_menu())

async def cb_about_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "ℹ️ О магазине TechStore:\n"
        "🏬 Адрес: ул. Примерная, 10, Москва\n"
        "📞 Телефон: +7 (900) 123-45-67\n"
        "🌐 Соц.сети: @techstore_vk, @techstore_telegram\n"
        "🛡 Гарантия: 1 год на всю технику\n"
        "🕒 Режим работы: Пн–Пт 10:00–20:00, Сб–Вс 11:00–18:00"
    )
    await query.message.reply_text(text, reply_markup=post_order_menu())

# ------------------ Прочие команды ------------------
async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ℹ️ Наш магазин TechStore — официальные продажи, гарантия 1 год. Адрес: ул. Примерная, 10, Москва")

async def cmd_sales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔥 Текущие акции:\n- Скидка 20% на аксессуары при предзаказе\n- Рассрочка 0% на 6 месяцев")

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Операция отменена.", reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END

# ------------------ Запуск ------------------
def main():
    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", cmd_start),
            CallbackQueryHandler(cb_start_order, pattern="^start_order$"),
            CallbackQueryHandler(cb_start_order, pattern="^new_order$"),
        ],
        states={
            CHOOSING: [CallbackQueryHandler(cb_start_order, pattern="^start_order$")],
            MODEL: [CallbackQueryHandler(cb_choose_model, pattern="^model_")],
            MEMORY: [CallbackQueryHandler(cb_memory, pattern="^mem_")],
            COLOR: [CallbackQueryHandler(cb_color, pattern="^col_")],
            CONFIRM: [
                CallbackQueryHandler(cb_confirm_order, pattern="^confirm_order$"),
                CallbackQueryHandler(cb_edit_order, pattern="^edit_order$")
            ],
            CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact_handler)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(cb_edit_order, pattern="^edit_order$"))
    app.add_handler(CallbackQueryHandler(cb_contact_manager, pattern="^contact_manager$"))
    app.add_handler(CallbackQueryHandler(cb_show_sales, pattern="^show_sales$"))
    app.add_handler(CallbackQueryHandler(cb_about_shop, pattern="^about_shop$"))
    app.add_handler(CommandHandler("info", cmd_info))
    app.add_handler(CommandHandler("sales", cmd_sales))
    app.add_handler(CommandHandler("cancel", cmd_cancel))

    print("🤖 Bot started — запустите в терминале. Ctrl+C для остановки.")
    app.run_polling()

if __name__ == "__main__":
    main()