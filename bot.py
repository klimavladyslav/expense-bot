import os
import logging
import tempfile
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
from parser import parse_expenses
from sheets import append_to_sheet
from transcriber import transcribe_voice

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
        "Просто напишіть або надішліть голосове повідомлення, наприклад:\n"
        "• `500 UAH реклама Онлайн-продажі`\n"
        "• `Заплатили 1200 грн зарплата вантажники Одеса вчора`\n"
        "• `Вчора: реклама 500 грн онлайн, сировина 3000 грн Харків`\n\n"
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


async def process_text(text: str, sender: str, update: Update, processing_msg):
    expenses = await parse_expenses(text)

    if not expenses:
        await processing_msg.edit_text(
            "❌ Не вдалося розпізнати жодної транзакції. Спробуйте ще раз."
        )
        return

    results = []
    errors = []

    for i, expense in enumerate(expenses, 1):
        # Check for missing required fields
        missing = []
        for field, label in REQUIRED_FIELDS.items():
            if not expense.get(field):
                missing.append(label)

        if missing:
            prefix = f"Транзакція {i}: " if len(expenses) > 1 else ""
            missing_str = ", ".join(missing)
            errors.append(f"{prefix}не вистачає — {missing_str}")
            continue

        expense["sent_by"] = sender
        append_to_sheet(expense)

        amount_str = f"{expense['amount']} {expense['currency']}"
        results.append(
            f"✅ *{expense['category']}* — {amount_str}\n"
            f"   📅 {expense['date']} | 🏪 {expense['account']}"
            + (f"\n   📝 {expense['comment']}" if expense.get('comment') else "")
        )

    # Build reply
    reply_parts = []

    if results:
        count = len(results)
        reply_parts.append(f"*Записано {count} транзакці{'я' if count == 1 else 'ї' if count < 5 else 'й'}:*\n")
        reply_parts.extend(results)

    if errors:
        reply_parts.append("\n⚠️ *Не записано (відсутні дані):*")
        for err in errors:
            reply_parts.append(f"• {err}")
        reply_parts.append("\nНадішліть ці транзакції окремо з повною інформацією.")

    reply_parts.append(f"\n👤 {sender}")

    await processing_msg.edit_text("\n".join(reply_parts), parse_mode="Markdown")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    sender = user.full_name or user.username or "Невідомий"

    logger.info(f"Текст від {sender}: {text}")
    processing = await update.message.reply_text("⏳ Обробляю...")

    try:
        await process_text(text, sender, update, processing)
    except Exception as e:
        logger.error(f"Помилка: {e}", exc_info=True)
        await processing.edit_text(
            "⚠️ Сталася помилка при обробці. Спробуйте ще раз або зверніться до адміністратора."
        )


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    sender = user.full_name or user.username or "Невідомий"

    logger.info(f"Голосове від {sender}")
    processing = await update.message.reply_text("🎤 Розпізнаю голосове повідомлення...")

    try:
        # Download voice file
        voice = update.message.voice
        file = await context.bot.get_file(voice.file_id)

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name

        await file.download_to_drive(tmp_path)

        # Transcribe
        await processing.edit_text("🎤 Транскрибую аудіо...")
        text = await transcribe_voice(tmp_path)

        logger.info(f"Транскрипція від {sender}: {text}")
        await processing.edit_text(f"🎤 Розпізнано: _{text}_\n\n⏳ Обробляю...", parse_mode="Markdown")

        # Parse and record
        await process_text(text, sender, update, processing)

        # Cleanup
        os.unlink(tmp_path)

    except Exception as e:
        logger.error(f"Помилка голосового: {e}", exc_info=True)
        await processing.edit_text(
            "⚠️ Сталася помилка при обробці голосового. Спробуйте надіслати текстом."
        )


def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    logger.info("Бот запущено...")
    app.run_polling()


if __name__ == "__main__":
    main()
