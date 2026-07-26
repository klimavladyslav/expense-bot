import os
import logging
import tempfile
import json
import httpx
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, MessageHandler, CommandHandler,
    CallbackQueryHandler, filters, ContextTypes
)
from parser import parse_expenses
from sheets import append_to_sheet
from transcriber import transcribe_voice
from invoice_parser import parse_invoice_file
from calculator import calculate_rows, group_products_by_similarity
from sheets_containers import append_rows_to_containers
from categories import CATEGORIES

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

KYIV_TZ = ZoneInfo("Europe/Kyiv")

# ── Expense bot constants ─────────────────────────────────────────────────────
REQUIRED_FIELDS = {
    "amount": "суму",
    "currency": "валюту (UAH/USD/EUR)",
    "category": "категорію",
    "account": "рахунок/магазин (Онлайн-продажі / Одеса (Кузьмиха) / Оптові продажі / Хмельницький / Харків)",
}

# ── Container bot constants ───────────────────────────────────────────────────
S_WAITING_COSTS   = "waiting_costs"
S_WAITING_MULTI   = "waiting_multi_confirm"
S_CATEGORY_GROUPS = "category_groups"
S_CURRENT_GROUP   = "current_group_idx"
S_ROWS            = "rows"
S_INVOICE         = "invoice"
S_CUSTOMS         = "customs"
S_DELIVERY        = "delivery"
S_TRANSFER_PCT    = "transfer_pct"
S_PARSED_RESULT   = "parsed_result"
MAX_CAT_BUTTONS   = 9


# ═══════════════════════════════════════════════════════════════════════════════
# SHARED
# ═══════════════════════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Привіт! Я бот для обліку витрат та контейнерів.*\n\n"
        "📝 *Витрати* — напишіть або надішліть голосове:\n"
        "• `500 UAH реклама Онлайн-продажі`\n"
        "• `Заплатили 1200 грн зарплата вантажники Одеса вчора`\n\n"
        "📦 *Контейнери* — надішліть файл інвойсу (PDF / DOC / Excel)\n\n"
        "*Основні категорії витрат:*\n"
        "• Реклама • Зарплата • Сировина і матеріали\n"
        "• Транспортування • Товари • Комунальні послуги\n"
        "• Оренда точок • Паливо • Повернення • Інші\n\n"
        "*Рахунки:* Онлайн-продажі / Одеса (Кузьмиха) / Оптові продажі / Хмельницький / Харків",
        parse_mode="Markdown"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# EXPENSE FLOW
# ═══════════════════════════════════════════════════════════════════════════════

async def process_text_expense(text: str, sender: str, update: Update, processing_msg):
    expenses = await parse_expenses(text)
    if not expenses:
        await processing_msg.edit_text("❌ Не вдалося розпізнати жодної транзакції. Спробуйте ще раз.")
        return

    results = []
    errors = []

    for i, expense in enumerate(expenses, 1):
        missing = []
        for field, label in REQUIRED_FIELDS.items():
            if not expense.get(field):
                missing.append(label)

        if missing:
            prefix = f"Транзакція {i}: " if len(expenses) > 1 else ""
            errors.append(f"{prefix}не вистачає — {', '.join(missing)}")
            continue

        expense["sent_by"] = sender
        append_to_sheet(expense)

        amount_str = f"{expense['amount']} {expense['currency']}"
        results.append(
            f"✅ *{expense['category']}* — {amount_str}\n"
            f"   📅 {expense['date']} | 🏪 {expense['account']}"
            + (f"\n   📝 {expense['comment']}" if expense.get('comment') else "")
        )

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
    # Container flow takes priority if waiting for costs
    if context.user_data.get(S_WAITING_COSTS):
        await _process_costs(update, context)
        return

    text = update.message.text
    user = update.effective_user
    sender = user.full_name or user.username or "Невідомий"
    logger.info(f"Текст від {sender}: {text}")
    processing = await update.message.reply_text("⏳ Обробляю...")
    try:
        await process_text_expense(text, sender, update, processing)
    except Exception as e:
        logger.error(f"Помилка: {e}", exc_info=True)
        await processing.edit_text("⚠️ Сталася помилка при обробці. Спробуйте ще раз.")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    sender = user.full_name or user.username or "Невідомий"
    logger.info(f"Голосове від {sender}")
    processing = await update.message.reply_text("🎤 Розпізнаю голосове повідомлення...")
    try:
        voice = update.message.voice
        file = await context.bot.get_file(voice.file_id)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name
        await file.download_to_drive(tmp_path)
        await processing.edit_text("🎤 Транскрибую аудіо...")
        text = await transcribe_voice(tmp_path)
        logger.info(f"Транскрипція від {sender}: {text}")
        await processing.edit_text(f"🎤 Розпізнано: _{text}_\n\n⏳ Обробляю...", parse_mode="Markdown")
        await process_text_expense(text, sender, update, processing)
        os.unlink(tmp_path)
    except Exception as e:
        logger.error(f"Помилка голосового: {e}", exc_info=True)
        await processing.edit_text("⚠️ Помилка при обробці голосового. Спробуйте надіслати текстом.")


# ═══════════════════════════════════════════════════════════════════════════════
# CONTAINER FLOW
# ═══════════════════════════════════════════════════════════════════════════════

def _suggest_categories(product_name: str) -> list:
    name_lower = product_name.lower()
    keywords = {
        "плед":      ["Пледы Стандарт","Пледы Улучшенные","Пледы Люкс","Пледы Премиум","Пледы на диван","Пледы на кровать","Плюшевые пледы","Детские пледы","Меховые покрывала"],
        "blanket":   ["Пледы Стандарт","Пледы Улучшенные","Пледы Люкс","Пледы Премиум","Пледы на диван","Пледы на кровать","Плюшевые пледы","Детские пледы","Покрывала Муслин"],
        "pillow":    ["Декоративные подушки","Меховые подушки","Ортопедические подушки","Подушки для беременных","Пуховые подушки","Антиаллергенные подушки","Детские подушки","Подушки игрушки","Меховые подушки Сердце"],
        "подушк":    ["Декоративные подушки","Меховые подушки","Ортопедические подушки","Подушки для беременных","Пуховые подушки","Антиаллергенные подушки","Детские подушки","Подушки игрушки","Меховые подушки Сердце"],
        "comforter": ["Постельное белье Сатин","Постельное белье Хлопок","Бамбуковые одеяла","Одеяла из микрофибры","Пуховые одеяла","Меховые одеяла","Антиаллергенные подушки","Плюшевое постельное белье","Фланелевое постельное белье"],
        "одеял":     ["Бамбуковые одеяла","Пуховые одеяла","Меховые одеяла","Одеяла из микрофибры","Антиаллергенные подушки","Постельное белье Сатин","Стеганные сатиновые покрывала","Детское постельное белье","Плюшевое постельное белье"],
        "towel":     ["Покрывала Муслин","Пледы Стандарт","Халаты","Детские халаты","Наматрасники","Тапочки","Носки-тапочки","Коврики для дома","Скатерти"],
        "seat":      ["Подвесные качели","Надувные кресла с пуфом","Лежаки для животных","Коврики для дома","Чехлы на диван 3D Принт","Пледы на диван","Декоративные игрушки","Игрушки","Інше"],
        "recliner":  ["Надувные кресла с пуфом","Подвесные качели","Чехлы на диван 3D Принт","Пледы на диван","Коврики для дома","Лежаки для животных","Декоративные игрушки","Игрушки","Інше"],
        "jacquard":  ["Постельное белье Сатин","Стеганные сатиновые покрывала","Атласные покрывала","Покрывала из микрофибры","Постельное белье 3д","Постельное белье Хлопок","Плюшевое постельное белье","Летние покрывала","Льняное постельное белье"],
    }
    for kw, cats in keywords.items():
        if kw in name_lower:
            return cats[:MAX_CAT_BUTTONS]
    return sorted(CATEGORIES)[:MAX_CAT_BUTTONS]


def _make_category_keyboard(top_cats: list, include_mixed: bool = True) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for cat in top_cats[:MAX_CAT_BUTTONS]:
        row.append(InlineKeyboardButton(cat, callback_data=f"cat:{cat}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    if include_mixed:
        buttons.append([InlineKeyboardButton("⚠️ Не однакові в групі", callback_data="cat:__mixed__")])
    return InlineKeyboardMarkup(buttons)


def _format_preview(rows: list) -> str:
    lines = ["📋 *Попередній перегляд:*\n"]
    for i, r in enumerate(rows, 1):
        lines.append(
            f"{i}. *{r['product']}*\n"
            f"   📦 {r['qty']} {r['unit']} | 🏷 {r['category'] or '—'}\n"
            f"   💵 Unit: ${r['unit_price']} → Total: *${r['total_unit_cost']}*\n"
            f"   🏭 {r['supplier']} | {r['invoice_no']}"
        )
    return "\n".join(lines)


def _preview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Підтвердити та записати", callback_data="confirm:yes")],
        [InlineKeyboardButton("✏️ Змінити категорію", callback_data="confirm:edit_cat")],
        [InlineKeyboardButton("💰 Змінити витрати", callback_data="confirm:edit_costs")],
    ])


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    filename = doc.file_name or "invoice"
    ext = os.path.splitext(filename)[1].lower()

    if ext not in (".pdf", ".doc", ".docx", ".xlsx", ".xls", ".xlsm"):
        await update.message.reply_text(
            "⚠️ Непідтримуваний формат. Надішліть PDF, DOC, DOCX або Excel файл."
        )
        return

    processing = await update.message.reply_text("⏳ Читаю файл та розпізнаю інвойс...")
    try:
        file = await context.bot.get_file(doc.file_id)
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp_path = tmp.name
        await file.download_to_drive(tmp_path)

        result = await parse_invoice_file(tmp_path, filename)
        os.unlink(tmp_path)

        invoices = result.get("invoices", [])
        if not invoices:
            await processing.edit_text("❌ Не вдалося знайти інвойс у файлі. Спробуйте ще раз.")
            return

        context.user_data.clear()
        context.user_data[S_PARSED_RESULT] = result

        if result.get("multiple_containers") is None and len(invoices) > 1:
            context.user_data[S_WAITING_MULTI] = True
            inv_list = "\n".join(
                f"• {inv['invoice_no']} — {inv.get('supplier','?')} — ${inv.get('invoice_amount_total','?')}"
                for inv in invoices
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Один контейнер", callback_data="multi:one")],
                [InlineKeyboardButton("📦 Різні контейнери", callback_data="multi:separate")],
            ])
            await processing.edit_text(
                f"🔍 Знайдено кілька документів:\n{inv_list}\n\nЦе один контейнер чи окремі?",
                reply_markup=keyboard
            )
            return

        invoice = invoices[0]
        if len(invoices) > 1 and not result.get("multiple_containers"):
            for inv in invoices[1:]:
                invoice["products"].extend(inv.get("products", []))

        context.user_data[S_INVOICE] = invoice
        await _ask_costs(update, context, processing)

    except Exception as e:
        logger.error(f"Error processing document: {e}", exc_info=True)
        await processing.edit_text(f"⚠️ Помилка при обробці файлу: `{str(e)}`", parse_mode="Markdown")


async def _ask_costs(update, context, msg=None):
    invoice = context.user_data[S_INVOICE]
    text = (
        f"✅ Інвойс *{invoice['invoice_no']}* розпізнано\n"
        f"🏭 {invoice.get('supplier','—')}\n"
        f"💵 ${invoice.get('invoice_amount_total','?')} | {len(invoice['products'])} товарів\n\n"
        f"*Крок 1/3 — Вкажіть витрати (USD):*\n"
        f"`9500 розмитнення 2500 фрахт 3%`\n\n"
        f"• Розмитнення (митниця)\n"
        f"• Фрахт (доставка)\n"
        f"• Переказ (% або сума)"
    )
    context.user_data[S_WAITING_COSTS] = True
    if msg:
        await msg.edit_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, parse_mode="Markdown")


async def _process_costs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    context.user_data[S_WAITING_COSTS] = False

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    payload = {
        "model": "claude-sonnet-4-5",
        "max_tokens": 200,
        "system": 'Extract customs, delivery, transfer costs. Return ONLY JSON: {"customs": number, "delivery": number, "transfer_pct": number_or_null, "transfer_fixed": number_or_null}. transfer_pct is a percentage (e.g. 3 for 3%). If not mentioned use null.',
        "messages": [{"role": "user", "content": text}]
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"Content-Type": "application/json", "x-api-key": api_key, "anthropic-version": "2023-06-01"},
            json=payload
        )
        data = resp.json()

    raw = data["content"][0]["text"].strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    costs = json.loads(raw.strip())

    customs = costs.get("customs") or 0
    delivery = costs.get("delivery") or 0
    invoice_amount = context.user_data[S_INVOICE].get("invoice_amount_total", 0)

    if costs.get("transfer_pct"):
        transfer_pct = costs["transfer_pct"]
    elif costs.get("transfer_fixed") and invoice_amount:
        transfer_pct = round(costs["transfer_fixed"] / invoice_amount * 100, 4)
    else:
        transfer_pct = 0

    context.user_data[S_CUSTOMS] = customs
    context.user_data[S_DELIVERY] = delivery
    context.user_data[S_TRANSFER_PCT] = transfer_pct

    transaction = round(transfer_pct / 100 * invoice_amount, 2)
    await update.message.reply_text(
        f"✅ *Витрати зафіксовано:*\n"
        f"• Розмитнення: ${customs:,.2f}\n"
        f"• Фрахт: ${delivery:,.2f}\n"
        f"• Переказ: {transfer_pct}% = ${transaction:,.2f}\n\n"
        f"*Крок 2/3 — Оберіть категорії*",
        parse_mode="Markdown"
    )
    await _start_category_selection(update, context)


async def _start_category_selection(update, context):
    products = context.user_data[S_INVOICE]["products"]
    groups = group_products_by_similarity(products)
    context.user_data[S_CATEGORY_GROUPS] = groups
    context.user_data[S_CURRENT_GROUP] = 0
    for p in products:
        p.setdefault("category", "")
    await _ask_category_for_current_group(update, context)


async def _ask_category_for_current_group(update, context):
    groups = context.user_data[S_CATEGORY_GROUPS]
    idx = context.user_data[S_CURRENT_GROUP]

    if idx >= len(groups):
        await _show_preview(update, context)
        return

    group = groups[idx]
    product_names = "\n".join(f"• {p['product']}" for p in group)
    suggested = _suggest_categories(group[0]["product"])
    keyboard = _make_category_keyboard(suggested, include_mixed=(len(group) > 1))

    text = (
        f"*Крок 2/3 — Категорія {idx+1}/{len(groups)}*\n\n"
        f"Товар(и):\n{product_names}\n\n"
        f"Оберіть категорію:"
    )
    if hasattr(update, "callback_query") and update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def _show_preview(update, context):
    invoice = context.user_data[S_INVOICE]
    rows = calculate_rows(
        invoice,
        context.user_data[S_CUSTOMS],
        context.user_data[S_DELIVERY],
        context.user_data[S_TRANSFER_PCT]
    )
    context.user_data[S_ROWS] = rows
    text = f"*Крок 3/3 — Перевірте дані:*\n\n{_format_preview(rows)}"
    keyboard = _preview_keyboard()
    target = update.callback_query.message if hasattr(update, "callback_query") and update.callback_query else update.message
    await target.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("multi:"):
        choice = data.split(":")[1]
        invoices = context.user_data[S_PARSED_RESULT]["invoices"]
        if choice == "one":
            invoice = invoices[0]
            for inv in invoices[1:]:
                invoice["products"].extend(inv.get("products", []))
            context.user_data[S_INVOICE] = invoice
            await query.message.reply_text("✅ Оброблятимемо як один контейнер.")
        else:
            context.user_data[S_INVOICE] = invoices[0]
            await query.message.reply_text(
                f"📦 Обробляємо перший інвойс: *{invoices[0]['invoice_no']}*",
                parse_mode="Markdown"
            )
        await _ask_costs(update, context)

    elif data.startswith("cat:"):
        cat = data[4:]
        groups = context.user_data[S_CATEGORY_GROUPS]
        idx = context.user_data[S_CURRENT_GROUP]

        # Edit mode
        if "editing_row_idx" in context.user_data:
            row_idx = context.user_data.pop("editing_row_idx")
            rows = context.user_data.get(S_ROWS, [])
            rows[row_idx]["category"] = cat
            products = context.user_data[S_INVOICE].get("products", [])
            if row_idx < len(products):
                products[row_idx]["category"] = cat
            await query.edit_message_text(f"✅ Категорію змінено на *{cat}*", parse_mode="Markdown")
            await _show_preview(update, context)
            return

        group = groups[idx]
        if cat == "__mixed__":
            new_groups = groups[:idx] + [[p] for p in group] + groups[idx+1:]
            context.user_data[S_CATEGORY_GROUPS] = new_groups
            await query.message.reply_text("↩️ Розбиваю на окремі товари...")
            await _ask_category_for_current_group(update, context)
            return

        for p in group:
            p["category"] = cat
        await query.edit_message_text(
            f"✅ *{cat}*\n" + "\n".join(f"• {p['product']}" for p in group),
            parse_mode="Markdown"
        )
        context.user_data[S_CURRENT_GROUP] = idx + 1
        await _ask_category_for_current_group(update, context)

    elif data.startswith("confirm:"):
        action = data.split(":")[1]
        if action == "yes":
            rows = context.user_data.get(S_ROWS, [])
            try:
                count = append_rows_to_containers(rows)
                await query.edit_message_text(
                    f"✅ *Записано {count} рядків* до вкладки Containers!\n\nНадішліть наступний файл або повідомлення.",
                    parse_mode="Markdown"
                )
                context.user_data.clear()
            except Exception as e:
                await query.edit_message_text(f"⚠️ Помилка запису: `{e}`", parse_mode="Markdown")

        elif action == "edit_cat":
            rows = context.user_data.get(S_ROWS, [])
            buttons = [
                [InlineKeyboardButton(f"{i+1}. {r['product'][:35]} → {r['category'] or '—'}", callback_data=f"editcat:{i}")]
                for i, r in enumerate(rows)
            ]
            buttons.append([InlineKeyboardButton("↩️ Назад", callback_data="confirm:back")])
            await query.edit_message_text("Який рядок змінити?", reply_markup=InlineKeyboardMarkup(buttons))

        elif action == "edit_costs":
            context.user_data[S_WAITING_COSTS] = True
            await query.edit_message_text(
                "💰 Введіть нові витрати:\n`9500 розмитнення 2500 фрахт 3%`",
                parse_mode="Markdown"
            )

        elif action == "back":
            await _show_preview(update, context)

    elif data.startswith("editcat:"):
        row_idx = int(data.split(":")[1])
        rows = context.user_data.get(S_ROWS, [])
        row = rows[row_idx]
        context.user_data["editing_row_idx"] = row_idx
        suggested = _suggest_categories(row["product"])
        keyboard = _make_category_keyboard(suggested, include_mixed=False)
        await query.edit_message_text(
            f"Нова категорія для:\n*{row['product']}*\nПоточна: _{row['category'] or '—'}_",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
