import os
import httpx


def append_rows_to_containers(rows: list[dict]) -> int:
    """Write all rows to the Containers sheet via Apps Script. Returns row count."""
    url = os.environ["CONTAINERS_APPS_SCRIPT_URL"]

    payload = {"rows": []}
    for r in rows:
        payload["rows"].append([
            r.get("invoice_no", ""),
            r.get("invoice_date", ""),
            r.get("supplier", ""),
            r.get("category", ""),
            r.get("product", ""),
            r.get("qty", ""),
            r.get("cbm", ""),
            r.get("unit", ""),
            r.get("unit_price", ""),
            r.get("invoice_amount", ""),
            r.get("currency", ""),
            r.get("customs", ""),
            r.get("delivery", ""),
            r.get("transaction", ""),
            r.get("total_unit_cost", ""),
            r.get("split_by", ""),
            r.get("parsed_at", ""),
        ])

    response = httpx.post(url, json=payload, timeout=20, follow_redirects=True)
    response.raise_for_status()
    result = response.json()
    if not result.get("success"):
        raise Exception(f"Sheets error: {result.get('error', 'unknown')}")
    return len(rows)
