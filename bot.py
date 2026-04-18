import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
from parser import parse_expense
from sheets import append_to_sheet

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

REQUIRED_FIELDS = {
    "amount": "суму",
    "currency": "валюту (UAH/USD/EUR)",
    "category": "категорію",
    "account": "рахунок/магазин (Онлайн-продажі / Одеса (Кузьмиха) / Оптові продажі / Хмельницький / Харків)",
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привіт! Я записую витрати та надходження до таблиці.\n\n"
        "Просто напишіть мені будь-яким зручним способом, наприклад:\n"
        "• _500 UAH реклама онлайн-продажі вчора_\n"
        "• _Заплатили 1200 грн зарплата вантажники Одеса_\n"
        "• _Повернення 300 USD Харків сьогодні_\n\n"
        "Я уточню, якщо чогось не вистачає.",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    sender = user.full_name or user.username or "Невідомий"

    logger.info(f"Повідомлення від {sender}: {text}")

    processing = await update.message.reply_text("⏳ Обробляю...")

    try:
        expense = await parse_expense(text)

        # Check for missing required fields
        missing = []
        for field, label in REQUIRED_FIELDS.items():
            if not expense.get(field):
                missing.append(label)

        if missing:
            missing_str = "\n".join(f"• {m}" for m in missing)
            await processing.edit_text(
                f"❗ Не вистачає наступної інформації:\n{missing_str}\n\n"
                f"Будь ласка, надішліть повідомлення ще раз із цими даними."
            )
            return

        expense["sent_by"] = sender

        row_num = append_to_sheet(expense)

        await processing.edit_text(
            f"✅ *Записано!*\n\n"
            f"📅 Дата: {expense['date']}\n"
            f"💰 Сума: {expense['amount']} {expense['currency']}\n"
            f"🏷 Категорія: {expense['category']}\n"
            f"🏪 Рахунок: {expense['account']}\n"
            f"📝 Коментар: {expense.get('comment') or '—'}\n"
            f"👤 Записав: {sender}",
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Помилка: {e}", exc_info=True)
        await processing.edit_text(
            f"⚠️ Сталася помилка при обробці. Спробуйте ще раз або зверніться до адміністратора."
        )

def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Бот запущено...")
    app.run_polling()

if __name__ == "__main__":
    main()
