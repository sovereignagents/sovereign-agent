"""Instructor solution for Chapter 1 Unit B. Excluded from the student release."""

# ruff: noqa: F821 - injected after the notebook's needed_by_sku definition


def validate_draft(proposal, shop, prices, estimate_limit=3000):
    if not isinstance(proposal, dict) or set(proposal) != {"action", "drafts", "explanation"}:
        raise ValueError("exact proposal fields required")
    if proposal["action"] != "draft_order":
        raise ValueError("draft action required")
    if not isinstance(proposal["explanation"], str):
        raise ValueError("string explanation required")
    drafts = proposal["drafts"]
    if not isinstance(drafts, list):
        raise ValueError("drafts must be a list")

    needs = needed_by_sku(shop)
    required = {sku for sku, quantity in needs.items() if quantity > 0}
    seen = set()
    normalized = []
    for row in drafts:
        if not isinstance(row, dict) or set(row) != {"sku", "quantity"}:
            raise ValueError("exact draft fields required")
        sku = row["sku"]
        quantity = row["quantity"]
        if not isinstance(sku, str) or sku not in needs or sku not in prices:
            raise ValueError("known priced SKU required")
        if sku in seen:
            raise ValueError("duplicate SKU")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("positive integer quantity required")
        if needs[sku] != quantity:
            raise ValueError("quantity must equal current need")
        seen.add(sku)
        normalized.append({"sku": sku, "quantity": quantity})
    if seen != required:
        raise ValueError("every current shortage required exactly once")

    total = sum(prices[row["sku"]] * row["quantity"] for row in normalized)
    if total > estimate_limit:
        raise ValueError("estimate limit exceeded")
    return {
        "drafts": sorted(normalized, key=lambda row: row["sku"]),
        "estimated_pence": total,
        "currency": shop["currency"],
        "model_explanation_unverified": proposal["explanation"],
    }
