import os
import httpx
from datetime import datetime
from zoneinfo import ZoneInfo

KYIV_TZ = ZoneInfo("Europe/Kyiv")

def format_amount(amount) -> str:
    """Format amount as Ukrainian style: ##,# (e.g. 145,6)"""
    if amount is None:
        return ""
    # Format with comma as decimal separator
    formatted = f"{float(amount):.2f}".rstrip('0').rstrip('.')
    return formatted.replace('.', ',')

def format_date(date_str: str) -> str:
    """Convert YYYY-MM-DD to DD/MM/YYYY"""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return date_str

def append_to_sheet(expense: dict) -> None:
    url = os.environ["APPS_SCRIPT_URL"]

    raw_date = expense.get("date", datetime.now(KYIV_TZ).strftime("%Y-%m-%d"))
    raw_amount = expense.get("amount")

    payload = {
        "date": format_date(raw_date),
        "amount": format_amount(raw_amount),
        "currency": expense.get("currency"),
        "category": expense.get("category"),
        "account": expense.get("account"),
        "comment": expense.get("comment", ""),
        "created_date": datetime.now(KYIV_TZ).strftime("%d/%m/%Y %H:%M:%S"),
        "sent_by": expense.get("sent_by", ""),
    }

    response = httpx.post(url, json=payload, timeout=15, follow_redirects=True)
    response.raise_for_status()

    result = response.json()
    if not result.get("success"):
        raise Exception(f"Sheets error: {result.get('error', 'unknown')}")
