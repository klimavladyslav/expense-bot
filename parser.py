import os
import json
import httpx
from datetime import datetime
from zoneinfo import ZoneInfo

KYIV_TZ = ZoneInfo("Europe/Kyiv")

CATEGORIES = [
    "ЗП відділу продажів",
    "Транспортування товару",
    "Затрати на підрядника",
    "Повернення",
    "ЗП вантажників",
    "Комунальні послуги",
    "Реклама",
    "Ремонт приміщень і тех обслуговування",
    "Обслуговування сайту (хостинг)",
    "Сировина і матеріали",
    "Офісне приладдя",
    "Зарплата",
    "ЗП адмін. персоналу",
    "Оренда точок",
    "ЗП працівників виробництва",
    "Паливо",
    "Єдиний податок",
    "Інші адмін витрати",
    "Товари",
    "Оренда транспорту",
]

ACCOUNTS = [
    "Онлайн-продажі",
    "Одеса (Кузьмиха)",
    "Оптові продажі",
    "Хмельницький",
    "Харків",
]

SYSTEM_PROMPT = f"""Ти асистент для розбору фінансових повідомлень українською мовою.

Витягни з повідомлення наступні поля та поверни ТІЛЬКИ валідний JSON без жодного тексту навколо:

{{
  "date": "YYYY-MM-DD",
  "amount": <число або null>,
  "currency": "UAH" або "USD" або "EUR" або null,
  "category": <одна з категорій нижче або null>,
  "account": <один з рахунків нижче або null>,
  "comment": <короткий коментар або null>
}}

Доступні категорії (вибери найбільш відповідну):
{json.dumps(CATEGORIES, ensure_ascii=False)}

Доступні рахунки/магазини:
{json.dumps(ACCOUNTS, ensure_ascii=False)}

Правила:
- Якщо дата не вказана — використай сьогоднішню дату
- "вчора" = вчорашня дата, "сьогодні" = сьогоднішня дата
- Якщо валюта не вказана — null (не вигадуй)
- Якщо сума не вказана — null
- Для категорії та рахунку вибирай найближчий варіант зі списку, навіть якщо написано трохи інакше
- Якщо категорія або рахунок незрозумілі — null
- amount має бути числом (не рядком)
"""

async def parse_expense(text: str) -> dict:
    today = datetime.now(KYIV_TZ).strftime("%Y-%m-%d")

    payload = {
        "model": "claude-sonnet-4-5",
        "max_tokens": 500,
        "system": SYSTEM_PROMPT + f"\nСьогодні: {today}",
        "messages": [{"role": "user", "content": text}]
    }

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            },
            json=payload
        )
        response.raise_for_status()
        data = response.json()

    raw = data["content"][0]["text"].strip()

    # Strip markdown fences if present
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    return json.loads(raw)
