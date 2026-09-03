"""
AI Finance Controller — closes two finance-ops loops in one pass over a merchant's
transaction batch:

  1. RECONCILIATION  (deterministic): does every merchant-ledger entry have a
     matching bank/settlement record? Same amount, same date, same reference?
  2. GST CLASSIFICATION (AI-assisted): does the GST rate applied on each sale
     actually match what that item/service attracts?

Design choice (this is the "AI Judgment" story):
  - Matching transactions to each other is a deterministic problem -> plain rules,
    no AI, no hallucination risk on numbers.
  - Reading a messy free-text item description and deciding its correct tax
    category is a language problem -> that's the one place an LLM is used.
  - The GST *rate* always comes from a fixed lookup table, never from the model,
    so the model can't invent a rate that doesn't exist.

Usage:
    python3 main.py
    (set ANTHROPIC_API_KEY to use real AI classification; otherwise runs in
    offline keyword-fallback mode so it's demoable without a key)
"""
import os
import csv
from datetime import datetime

GST_CATEGORIES = {
    "Packaged food grains": 5,
    "Fresh produce": 0,
    "Packaged drinking water": 18,
    "Fresh milk": 0,
    "Essential medicines": 5,
    "IT/repair services": 18,
    "Mobile handsets": 18,
    "Apparel under 1000": 5,
    "Footwear above 1000": 18,
    "Restaurant services": 5,
    "Stationery/paper products": 12,
    "Consumer electronics": 18,
    "Software services": 18,
    "Logistics services": 18,
    "Insurance services": 18,
    "Jewellery": 3,
    "Furniture": 18,
    "Fitness services": 18,
    "Personal grooming services": 18,
    "Telecom services": 18,
    "Printed books": 0,
    "Printing services": 12,
    "Safety gear": 18,
    "Electrical goods": 12,
    "Eco/handicraft goods": 5,
}

# Offline fallback: crude keyword -> category map, used only when there's no API key.
# This is intentionally the "dumb" path -- it exists so the tool still runs and is
# demoable without setup, but the real submission should run with an API key so the
# AI is actually doing the classification work.
_KEYWORD_FALLBACK = [
    (["rice", "grain"], "Packaged food grains"),
    (["vegetable"], "Fresh produce"),
    (["water"], "Packaged drinking water"),
    (["milk"], "Fresh milk"),
    (["paracetamol", "medicine", "tablet"], "Essential medicines"),
    (["laptop repair", "repair service"], "IT/repair services"),
    (["mobile phone", "handset"], "Mobile handsets"),
    (["kurta", "apparel", "shirt"], "Apparel under 1000"),
    (["shoes", "footwear"], "Footwear above 1000"),
    (["restaurant", "dine"], "Restaurant services"),
    (["notebook", "stationery"], "Stationery/paper products"),
    (["earphone", "electronics"], "Consumer electronics"),
    (["software", "subscription"], "Software services"),
    (["courier", "freight", "logistics"], "Logistics services"),
    (["insurance"], "Insurance services"),
    (["gold", "jewellery"], "Jewellery"),
    (["table", "furniture"], "Furniture"),
    (["gym"], "Fitness services"),
    (["salon", "haircut", "grooming"], "Personal grooming services"),
    (["recharge", "telecom"], "Telecom services"),
    (["textbook", "book"], "Printed books"),
    (["printing"], "Printing services"),
    (["helmet", "safety"], "Safety gear"),
    (["bulb", "electrical"], "Electrical goods"),
    (["jute", "handicraft"], "Eco/handicraft goods"),
]


def classify_offline(description: str) -> str:
    d = description.lower()
    for keywords, category in _KEYWORD_FALLBACK:
        if any(k in d for k in keywords):
            return category
    return "Uncategorised"


def classify_with_ai(description: str, client) -> str:
    categories_list = "\n".join(f"- {c}" for c in GST_CATEGORIES)
    prompt = (
        "You are classifying an Indian retail/service transaction into exactly one "
        "GST category from this fixed list. Reply with ONLY the category name, "
        f"exactly as written, nothing else.\n\nCategories:\n{categories_list}\n\n"
        f'Transaction description: "{description}"'
    )
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=30,
        messages=[{"role": "user", "content": prompt}],
    )
    answer = resp.content[0].text.strip()
    return answer if answer in GST_CATEGORIES else classify_offline(description)


def load_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def run_reconciliation(bank_rows, ledger_rows):
    bank_by_ref = {r["reference"]: r for r in bank_rows}
    results = []
    for l in ledger_rows:
        ref = l["reference"]
        b = bank_by_ref.get(ref)
        if b is None:
            results.append({"reference": ref, "reconciled": False,
                             "reco_reason": "Missing on bank/settlement side"})
            continue
        amt_diff = round(float(l["amount"]) - float(b["amount"]), 2)
        date_l = datetime.strptime(l["date"], "%Y-%m-%d")
        date_b = datetime.strptime(b["date"], "%Y-%m-%d")
        day_diff = abs((date_l - date_b).days)

        if abs(amt_diff) > 1:
            results.append({"reference": ref, "reconciled": False,
                             "reco_reason": f"Amount mismatch of Rs {abs(amt_diff):.2f}"})
        elif day_diff > 0:
            results.append({"reference": ref, "reconciled": False,
                             "reco_reason": f"Date mismatch of {day_diff} day(s), likely settlement lag"})
        else:
            results.append({"reference": ref, "reconciled": True, "reco_reason": ""})
    return {r["reference"]: r for r in results}


def run_gst_check(ledger_rows, client):
    results = {}
    for l in ledger_rows:
        if client:
            category = classify_with_ai(l["item_description"], client)
        else:
            category = classify_offline(l["item_description"])
        correct_rate = GST_CATEGORIES.get(category)
        applied_rate = int(l["applied_gst_rate"])
        matches = (correct_rate == applied_rate)
        results[l["reference"]] = {
            "predicted_category": category,
            "correct_rate": correct_rate,
            "applied_rate": applied_rate,
            "gst_ok": matches,
        }
    return results


def main():
    bank_rows = load_csv("bank_statement.csv")
    ledger_rows = load_csv("merchant_ledger.csv")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    client = None
    if api_key:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        print("Running GST classification with live AI (Claude) ...\n")
    else:
        print("No ANTHROPIC_API_KEY set -> running GST classification in OFFLINE "
              "keyword-fallback mode. Set the key for real AI classification.\n")

    reco = run_reconciliation(bank_rows, ledger_rows)
    gst = run_gst_check(ledger_rows, client)

    rows_out = []
    reco_exceptions = 0
    gst_exceptions = 0
    money_at_risk = 0.0

    for l in ledger_rows:
        ref = l["reference"]
        r = reco[ref]
        g = gst[ref]
        amount = float(l["amount"])

        if not r["reconciled"]:
            reco_exceptions += 1
            if "Amount mismatch" in r["reco_reason"]:
                money_at_risk += float(r["reco_reason"].split("Rs ")[1])
        if not g["gst_ok"]:
            gst_exceptions += 1
            if g["correct_rate"] is not None:
                rate_gap = abs(g["correct_rate"] - g["applied_rate"]) / 100
                money_at_risk += amount * rate_gap

        rows_out.append({
            "order_id": l["order_id"],
            "reference": ref,
            "amount": amount,
            "item_description": l["item_description"],
            "reconciled": r["reconciled"],
            "reco_reason": r["reco_reason"],
            "predicted_gst_category": g["predicted_category"],
            "applied_gst_rate": g["applied_rate"],
            "correct_gst_rate": g["correct_rate"],
            "gst_ok": g["gst_ok"],
        })

    with open("exception_report.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
        w.writeheader()
        w.writerows(rows_out)

    total = len(ledger_rows)
    print(f"Checked {total} transactions")
    print(f"Reconciliation exceptions: {reco_exceptions} ({reco_exceptions/total:.0%})")
    print(f"GST classification exceptions: {gst_exceptions} ({gst_exceptions/total:.0%})")
    print(f"Estimated money at risk: Rs {money_at_risk:,.2f}")
    print(f"Full row-by-row report written to exception_report.csv")


if __name__ == "__main__":
    main()
