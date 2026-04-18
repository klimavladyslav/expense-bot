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
        "👋 *Привіт! Я бот для запису витрат і надходжень.*\n\n"
        "Просто напишіть мені в довільній формі, наприклад:\n"
        "• `500 UAH реклама Онлайн-продажі`\n"
        "• `Заплатили 1200 грн зарплата вантажники Одеса вчора`\n\n"
        "*Обов'язково вкажіть:*\n"
        "💰 Суму\n"
        "💵 Валюту (UAH / USD / EUR)\n"
        "🏷 Категорію\n"
        "🏪 Рахунок (Онлайн-продажі / Одеса (Кузьмиха) / Оптові продажі / Хмельницький / Харків)\n\n"
        "*Основні категорії:*\n"
        "• Реклама\n"
        "• Зарплата / ЗП відділу продажів / ЗП вантажників / ЗП адмін. персоналу / ЗП працівників виробництва\n"
        "• Сировина і матеріали\n"
        "• Транспортування товару\n"
        "• Товари\n"
        "• Комунальні послуги\n"
        "• Оренда точок / Оренда транспорту\n"
        "• Паливо\n"
        "• Ремонт приміщень і тех обслуговування\n"
        "• Обслуговування сайту (хостинг)\n"
        "• Офісне приладдя\n"
        "• Затрати на підрядника\n"
        "• Єдиний податок\n"
        "• Повернення\n"
        "• Інші адмін витрати\n\n"
        "Якщо щось не вказано — я запитаю окремо.",
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
            "⚠️ Сталася помилка при обробці. Спробуйте ще раз або зверніться до адміністратора."
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
