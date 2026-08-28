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
    Group products that are likely the same category.
    Only groups products with identical first 4 words after stripping sizes/specs.
    Returns list of groups, each group is a list of product dicts.
    """
    import re

    def base_name(name: str) -> str:
        # Strip size patterns like 200x230cm, 50*70, SIZE:xxx
        name = re.sub(r'\b\d+[xX*×]\d+(?:[Cc][Mm])?\b', '', name)
        name = re.sub(r'\bSIZE[:\s]*\S+', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\b\d+\s*[Cc][Mm]\b', '', name)
        # Strip common size descriptors that distinguish variants
        name = re.sub(r'\b(double|single|family|king|queen|euro|standard)\s*size\b', '', name, flags=re.IGNORECASE)
        name = name.strip().rstrip('.,- ')
        # Take first 4 meaningful words for stricter matching
        words = [w for w in name.split() if len(w) > 1][:4]
        return " ".join(words).lower()

    # First pass: group by base name
    groups = {}
    for p in products:
        key = base_name(p["product"])
        if key not in groups:
            groups[key] = []
        groups[key].append(p)

    # Second pass: if a group has products with different sizes/specs mentioned
    # in original name after stripping → keep as separate items
    final_groups = []
    for key, group in groups.items():
        if len(group) == 1:
            final_groups.append(group)
            continue
        # Check if products differ only by size — if so, group them
        # If they have distinctly different descriptions beyond size, split them
        names = [p["product"].lower() for p in group]
        size_keywords = ["double", "single", "family", "king", "queen", "euro", "standard",
                         "160", "180", "200", "220", "240", "50x70", "70x70"]
        has_size_variants = any(
            any(sk in n for sk in size_keywords) for n in names
        )
        if has_size_variants:
            # Keep as one group — same product, different sizes = same category
            final_groups.append(group)
        else:
            # Might be genuinely different products — split into individual items
            for p in group:
                final_groups.append([p])

    return final_groups
