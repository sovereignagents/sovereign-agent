def repair_fragment():
    return 'receipt = supplier.order(identifier, json.loads(row["proposal"]))'


def normalize_discovery(raw):
    if raw is None:
        return None
    statuses = {"accepted": "ACCEPTED", "declined": "REJECTED"}
    try:
        status = statuses[raw["decision"]]
        operation = raw["order_ref"]
        proposal = raw["payload"]
    except KeyError, TypeError:
        raise ValueError("invalid partner discovery result") from None
    return {"operation": operation, "proposal": proposal, "status": status}
