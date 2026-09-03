"""
Generates two synthetic datasets for the AI Finance Controller demo:
  bank_statement.csv   -> what the bank/Razorpay settlement records show
  merchant_ledger.csv  -> what the merchant's own books show, incl. GST rate applied

Deliberately injects:
  - reconciliation errors (missing entries, amount mismatches, date mismatches)
  - GST classification errors (wrong rate applied vs. what the item actually attracts)
so the checker script has real things to catch.
"""
import csv
import random

random.seed(42)

# (item description, correct GST category, correct GST rate %)
CATALOG = [
    ("Basmati rice 5kg pack", "Packaged food grains", 5),
    ("Fresh vegetables crate", "Fresh produce", 0),
    ("Bottled mineral water 1L", "Packaged drinking water", 18),
    ("Toned milk 1L pouch", "Fresh milk", 0),
    ("Paracetamol strip 10 tabs", "Essential medicines", 5),
    ("Laptop repair service", "IT/repair services", 18),
    ("Mobile phone 128GB", "Mobile handsets", 18),
    ("Cotton kurta", "Apparel under 1000", 5),
    ("Leather formal shoes", "Footwear above 1000", 18),
    ("Restaurant dine-in bill", "Restaurant services", 5),
    ("Notebook pack of 5", "Stationery/paper products", 12),
    ("Bluetooth earphones", "Consumer electronics", 18),
    ("Software subscription 1yr", "Software services", 18),
    ("Courier/freight charges", "Logistics services", 18),
    ("Health insurance premium", "Insurance services", 18),
    ("Gold chain 10g", "Jewellery", 3),
    ("Wooden dining table", "Furniture", 18),
    ("Gym membership monthly", "Fitness services", 18),
    ("Salon haircut service", "Personal grooming services", 18),
    ("Mobile recharge 599 plan", "Telecom services", 18),
    ("Printed textbook", "Printed books", 0),
    ("A4 printing 100 pages", "Printing services", 12),
    ("Two-wheeler helmet", "Safety gear", 18),
    ("LED bulb 9W", "Electrical goods", 12),
    ("Handmade jute bag", "Eco/handicraft goods", 5),
]

N = 58
bank_rows = []
ledger_rows = []

for i in range(1, N + 1):
    ref = f"REF{1000 + i}"
    item, category, correct_rate = random.choice(CATALOG)
    amount = round(random.uniform(150, 8500), 2)
    day = random.randint(1, 28)
    date = f"2026-08-{day:02d}"

    # Decide what "applied" GST rate the merchant used -- usually correct,
    # sometimes wrong (this is what the tax checker should catch)
    if random.random() < 0.24:
        # apply a plausible but wrong rate
        wrong_pool = [r for r in [0, 5, 12, 18, 28] if r != correct_rate]
        applied_rate = random.choice(wrong_pool)
    else:
        applied_rate = correct_rate

    ledger_rows.append({
        "order_id": f"ORD{2000 + i}",
        "reference": ref,
        "date": date,
        "amount": amount,
        "item_description": item,
        "applied_gst_rate": applied_rate,
    })

    # Decide what happens on the bank side (this is what reconciliation should catch)
    roll = random.random()
    if roll < 0.09:
        # missing entirely on bank side (e.g. settlement failed/delayed)
        continue
    elif roll < 0.16:
        # amount mismatch (partial refund / short settlement)
        bank_amount = round(amount - random.uniform(20, 300), 2)
        bank_date = date
    elif roll < 0.22:
        # date mismatch (settlement lag)
        bank_amount = amount
        d = int(date.split("-")[2]) 
        new_day = min(28, d + random.randint(2, 5))
        bank_date = f"2026-08-{new_day:02d}"
    else:
        bank_amount = amount
        bank_date = date

    bank_rows.append({
        "transaction_id": f"TXN{3000 + i}",
        "reference": ref,
        "date": bank_date,
        "amount": bank_amount,
    })

with open("bank_statement.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["transaction_id", "reference", "date", "amount"])
    w.writeheader()
    w.writerows(bank_rows)

with open("merchant_ledger.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["order_id", "reference", "date", "amount", "item_description", "applied_gst_rate"])
    w.writeheader()
    w.writerows(ledger_rows)

print(f"merchant_ledger.csv: {len(ledger_rows)} rows")
print(f"bank_statement.csv: {len(bank_rows)} rows ({len(ledger_rows) - len(bank_rows)} missing on bank side)")
