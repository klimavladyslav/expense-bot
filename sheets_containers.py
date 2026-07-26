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

    # Apps Script requires following redirects manually to preserve POST body
    with httpx.Client(timeout=30) as client:
        # First request — get redirect location
        response = client.post(
            url,
            json=payload,
            follow_redirects=False
        )

        # If redirected, follow manually with GET (Apps Script pattern)
        if response.status_code in (301, 302, 303, 307, 308):
            redirect_url = response.headers.get("location")
            if redirect_url:
                response = client.post(
                    redirect_url,
                    json=payload,
                    follow_redirects=False
                )

        # Parse response
        text = response.text.strip()
        if not text:
            raise Exception("Empty response from Apps Script — check deployment authorization")

        import json
        result = json.loads(text)
        if not result.get("success"):
            raise Exception(f"Sheets error: {result.get('error', 'unknown')}")

    return len(rows)
