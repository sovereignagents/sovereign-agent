"""Chapter 1: one explicit model request, with an offline response fixture."""

import argparse
import copy
import hashlib
import json
from urllib.request import Request, urlopen

SHOP = {
    "customer": "Lucy",
    "currency": "GBP",
    "products": [
        {"sku": "SKU-VANILLA", "name": "Vanilla", "on_hand": 2, "reorder_point": 8},
        {"sku": "SKU-CHOCOLATE", "name": "Chocolate", "on_hand": 12, "reorder_point": 6},
        {"sku": "SKU-STRAWBERRY", "name": "Strawberry", "on_hand": 1, "reorder_point": 5},
    ],
}


def messages(shop):
    return [
        {
            "role": "system",
            "content": "Write a short morning stock brief for Lucy. "
            "Use only the supplied stock facts. Name products below their reorder points. "
            "Do not purchase anything or claim that an order exists.",
        },
        {"role": "user", "content": json.dumps(shop, sort_keys=True)},
    ]


def payload(shop, model="qwen3"):
    return {
        "model": model,
        "messages": messages(shop),
        "stream": False,
        "temperature": 0,
        "max_tokens": 256,
        "reasoning_effort": "none",
    }


def read_brief(document):
    if not isinstance(document, dict):
        raise ValueError("completion envelope must be an object")
    choices = document.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise ValueError("one completion required")
    choice = choices[0]
    if not isinstance(choice, dict) or choice.get("finish_reason") != "stop":
        raise ValueError("completion did not finish normally")
    message = choice.get("message", {})
    if not isinstance(message, dict) or message.get("tool_calls") or message.get("refusal"):
        raise ValueError("a plain completed brief was expected")
    text = message.get("content")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("nonempty brief required")
    return text


def stock_facts(shop):
    return [
        (p["sku"], p["on_hand"], max(0, p["reorder_point"] - p["on_hand"]))
        for p in sorted(shop["products"], key=lambda p: p["sku"])
    ]


def check_brief(text, shop):
    lower = text.lower()
    problems = [
        "omits low product " + p["name"]
        for p in shop["products"]
        if p["on_hand"] < p["reorder_point"] and p["name"].lower() not in lower
    ]
    for phrase in ("placed the supplier order", "placed an order", "purchased"):
        if phrase in lower:
            problems.append("possible unsupported action: " + phrase)
    return problems


def snapshot_id(shop):
    return hashlib.sha256(json.dumps(shop, sort_keys=True).encode()).hexdigest()


def build(shop):
    snapshot = copy.deepcopy(shop)
    return {"snapshot": snapshot_id(snapshot), "body": payload(snapshot)}


def review_brief(built, document, current_shop):
    if built["snapshot"] != snapshot_id(current_shop):
        raise ValueError("shop changed since the request was built; request a fresh brief")
    text = read_brief(document)
    return {
        "status": "NEEDS_FACTUAL_REVIEW",
        "draft": text,
        "flags": check_brief(text, current_shop),
        "stock_facts": stock_facts(current_shop),
    }


def live_call(body):
    # A socket-operation timeout, not a total wall-clock guarantee. Chapter 3
    # introduces the killable transport used by the cumulative agent.
    request = Request(
        "http://localhost:11434/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=30) as response:
        raw = response.read(65_537)
    if len(raw) > 65_536:
        raise ValueError("response exceeded the chapter's byte limit")
    return json.loads(raw)


OFFLINE_RESPONSE = {
    "choices": [
        {
            "finish_reason": "stop",
            "message": {
                "role": "assistant",
                "content": "Vanilla has 2 tubs and strawberry has 1: "
                "both are below their reorder points. "
                "Chocolate has 12 tubs, above its reorder point. No orders have been placed.",
            },
        }
    ]
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--model", default="qwen3")
    args = parser.parse_args()
    built = build(SHOP)
    body = built["body"]
    body["model"] = args.model
    try:
        document = live_call(body) if args.live else OFFLINE_RESPONSE
        review = review_brief(built, document, SHOP)
    except OSError, ValueError:
        parser.exit(
            1,
            "Model call failed. Start Ollama and pull the selected model; "
            "check the Chapter 1 setup, then retry. No order was sent.\n",
        )
    print("LIVE MODEL RESPONSE" if args.live else "OFFLINE RESPONSE FIXTURE")
    print(review["draft"])
    if review["flags"]:
        print("Warning flags; factual review required:", review["flags"])


if __name__ == "__main__":
    main()
