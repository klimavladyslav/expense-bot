def calculate_rows(invoice: dict, customs: float, delivery: float, transfer_pct: float) -> list[dict]:
    """
    Calculate total unit cost for each product line.
    Allocates shared costs by CBM if available, otherwise by qty.
    Returns list of row dicts ready for Google Sheets.
    """
    products = invoice["products"]
    invoice_amount = invoice["invoice_amount_total"]
    transaction = round(transfer_pct / 100 * invoice_amount, 2)
    total_fixed = customs + delivery + transaction

    has_cbm = all(p.get("cbm") is not None for p in products)

    if has_cbm:
        total_split = sum(p["cbm"] for p in products)
        split_by = "CBM"
    else:
        total_split = sum(p["qty"] for p in products)
        split_by = "Qty"

    rows = []
    from datetime import datetime
    from zoneinfo import ZoneInfo
    parsed_at = datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%d/%m/%Y %H:%M:%S")

    for p in products:
        split_value = p["cbm"] if has_cbm else p["qty"]
        share = split_value / total_split if total_split > 0 else 0

        customs_share = round(customs * share, 2)
        delivery_share = round(delivery * share, 2)
        transaction_share = round(transaction * share, 2)
        allocated_per_unit = (customs_share + delivery_share + transaction_share) / p["qty"] if p["qty"] > 0 else 0
        total_unit_cost = round(p["unit_price"] + allocated_per_unit, 4)

        rows.append({
            "invoice_no": invoice["invoice_no"],
            "invoice_date": _format_date(invoice.get("invoice_date")),
            "supplier": invoice.get("supplier", ""),
            "category": p.get("category", ""),
            "product": p["product"],
            "qty": p["qty"],
            "cbm": p.get("cbm", ""),
            "unit": p.get("unit", "pcs"),
            "unit_price": p["unit_price"],
            "invoice_amount": invoice_amount,
            "currency": invoice.get("currency", "USD"),
            "customs": customs,
            "delivery": delivery,
            "transaction": transaction,
            "total_unit_cost": total_unit_cost,
            "split_by": split_by,
            "parsed_at": parsed_at,
        })

    return rows


def _format_date(date_str: str | None) -> str:
    if not date_str:
        return ""
    try:
        from datetime import datetime
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return date_str or ""


def group_products_by_similarity(products: list[dict]) -> list[list[dict]]:
    """
    Group products that are likely the same category
    (same base name, different sizes).
    Returns list of groups, each group is a list of product dicts.
    """
    import re

    def base_name(name: str) -> str:
        # Strip size patterns like 200x230, 50*70, SIZE:xxx
        name = re.sub(r'\b\d+[xX*×]\d+\b', '', name)
        name = re.sub(r'\bSIZE[:\s]*\S+', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\b\d+\s*[Cc][Mm]\b', '', name)
        name = name.strip().rstrip('.,- ')
        # Take first 3 meaningful words
        words = name.split()[:3]
        return " ".join(words).lower()

    groups = {}
    for p in products:
        key = base_name(p["product"])
        if key not in groups:
            groups[key] = []
        groups[key].append(p)

    return list(groups.values())
