import os
import httpx
from datetime import datetime
from zoneinfo import ZoneInfo

KYIV_TZ = ZoneInfo("Europe/Kyiv")

def append_to_sheet(expense: dict) -> None:
    url = os.environ["APPS_SCRIPT_URL"]

    payload = {
        "date": expense.get("date", datetime.now(KYIV_TZ).strftime("%Y-%m-%d")),
        "amount": expense.get("amount"),
        "currency": expense.get("currency"),
        "category": expense.get("category"),
        "account": expense.get("account"),
        "comment": expense.get("comment", ""),
        "created_date": datetime.now(KYIV_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "sent_by": expense.get("sent_by", ""),
    }

    response = httpx.post(url, json=payload, timeout=15, follow_redirects=True)
    response.raise_for_status()

    result = response.json()
    if not result.get("success"):
        raise Exception(f"Sheets error: {result.get('error', 'unknown')}")
