import os
import json
import logging
import httpx

logger = logging.getLogger(__name__)


def append_rows_to_containers(rows: list[dict]) -> int:
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

    with httpx.Client(timeout=30) as client:
        response = client.post(url, json=payload, follow_redirects=True)

    logger.info(f"[Containers] Status: {response.status_code}")
    logger.info(f"[Containers] Body: {repr(response.text[:300])}")

    if response.status_code >= 400:
        raise Exception(f"HTTP error {response.status_code} from Apps Script")

    # Apps Script sometimes returns HTML redirect instead of JSON
    # but the write already succeeded — only parse if it looks like JSON
    text = response.text.strip()
    if text.startswith("{"):
        result = json.loads(text)
        if not result.get("success"):
            logger.error(f"[Containers] Apps Script error: {result.get('error')}")
            raise Exception(f"Sheets error: {result.get('error', 'unknown')}")
    else:
        logger.info(f"[Containers] Non-JSON response (likely redirect) — treating as success")

    return len(rows)
