"""
01_generate_data.py
-------------------
Generates realistic Bank Statement + General Ledger (GL) datasets
for the Bank Reconciliation & Financial Controls project.

Simulates real-world reconciliation breaks:
  - Timing differences (bank clears 1-3 days late)
  - Amount mismatches (bank fees deducted / posting errors)
  - Missing in Bank (deposits in transit / unpresented cheques)
  - Missing in GL  (bank charges, interest not yet booked)
  - Duplicate postings (control failure scenario)

Run:  python 01_generate_data.py
Output: ../data/bank_statement.csv , ../data/general_ledger.csv
"""

import csv
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(42)  # reproducible

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

START = date(2025, 6, 1)
END = date(2025, 8, 20)
N_BASE = 10000  # base transactions in the GL

COUNTERPARTIES = [
    "INFOSYS LTD", "TATA STEEL", "RELIANCE RETAIL", "AMAZON SELLER SVCS",
    "FLIPKART INTERNET", "HDFC LIFE PREMIUM", "LIC OF INDIA", "VENDOR-ACME SUPPLIES",
    "VENDOR-BRIGHT TOOLS", "VENDOR-CRESCENT LOGISTICS", "PAYROLL BATCH", "GST PAYMENT",
    "TDS REMITTANCE", "ELECTRICITY BOARD", "OFFICE RENT-DLF", "AWS CLOUD SERVICES",
    "GOOGLE ADS", "CLIENT-NORTHSTAR INC", "CLIENT-ORCHID GLOBAL", "CLIENT-PINNACLE CORP",
]

TXN_TYPES = ["NEFT", "RTGS", "IMPS", "UPI", "CHEQUE", "ACH"]


def rand_date():
    delta = (END - START).days
    return START + timedelta(days=random.randint(0, delta))


def rand_amount():
    # mix of small, medium and large transactions
    bucket = random.random()
    if bucket < 0.55:
        return round(random.uniform(500, 50_000), 2)
    elif bucket < 0.85:
        return round(random.uniform(50_000, 500_000), 2)
    else:
        return round(random.uniform(500_000, 5_000_000), 2)


def main():
    gl_rows = []      # internal books (General Ledger)
    bank_rows = []    # bank statement

    for i in range(1, N_BASE + 1):
        ref = f"TXN{i:07d}"
        txn_date = rand_date()
        amount = rand_amount()
        drcr = random.choice(["DR", "CR"])
        party = random.choice(COUNTERPARTIES)
        mode = random.choice(TXN_TYPES)
        desc = f"{mode} {'PAYMENT TO' if drcr == 'DR' else 'RECEIPT FROM'} {party}"

        roll = random.random()

        # ---------- 90% clean: appears identically in both ----------
        if roll < 0.90:
            gl_rows.append([ref, txn_date, desc, party, mode, drcr, amount])
            bank_rows.append([ref, txn_date, desc, party, mode, drcr, amount])

        # ---------- 3.5% timing difference: bank clears late ----------
        elif roll < 0.935:
            lag = random.randint(1, 3)
            gl_rows.append([ref, txn_date, desc, party, mode, drcr, amount])
            bank_rows.append([ref, txn_date + timedelta(days=lag), desc, party, mode, drcr, amount])

        # ---------- 2% amount mismatch: fee deducted / posting error ----------
        elif roll < 0.955:
            gl_rows.append([ref, txn_date, desc, party, mode, drcr, amount])
            if random.random() < 0.6:
                bank_amt = round(amount - random.choice([59, 118, 236, 295, 590]), 2)  # bank fee
            else:
                bank_amt = round(amount + random.uniform(-500, 500), 2)                # posting error
            bank_rows.append([ref, txn_date, desc, party, mode, drcr, bank_amt])

        # ---------- 2.5% missing in bank: deposit in transit / unpresented cheque ----------
        elif roll < 0.98:
            gl_rows.append([ref, txn_date, desc, party, mode, drcr, amount])
            # not in bank statement

        # ---------- 2% missing in GL: bank-only items ----------
        else:
            bank_rows.append([ref, txn_date, desc, party, mode, drcr, amount])
            # not in GL

    # ---------- bank-side system items never booked in GL ----------
    bank_only_items = [
        ("BANK CHARGES", "DR", (59, 5900)),
        ("SMS ALERT FEE", "DR", (12, 250)),
        ("INTEREST CREDIT", "CR", (500, 95000)),
        ("CHEQUE BOOK FEE", "DR", (100, 600)),
        ("ATM FEE REVERSAL", "CR", (20, 200)),
    ]
    for k in range(120):
        label, drcr, (lo, hi) = random.choice(bank_only_items)
        ref = f"BNK{k + 1:05d}"
        bank_rows.append([ref, rand_date(), label, "BANK", "SYS", drcr, round(random.uniform(lo, hi), 2)])

    # ---------- duplicate postings (control failure) ----------
    dup_candidates = random.sample([r for r in gl_rows if r[6] > 10000], 40)
    for r in dup_candidates:
        dup = list(r)
        dup[0] = r[0] + "-D"   # duplicate gets suffixed ref (common in real ERP re-posts)
        gl_rows.append(dup)

    # ---------- write files ----------
    with open(DATA_DIR / "general_ledger.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["gl_ref", "posting_date", "description", "counterparty", "mode", "drcr", "amount"])
        for r in sorted(gl_rows, key=lambda x: x[1]):
            w.writerow(r)

    with open(DATA_DIR / "bank_statement.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["bank_ref", "value_date", "narration", "counterparty", "mode", "drcr", "amount"])
        for r in sorted(bank_rows, key=lambda x: x[1]):
            w.writerow(r)

    print(f"General Ledger rows : {len(gl_rows):,}")
    print(f"Bank Statement rows : {len(bank_rows):,}")
    print(f"Files written to    : {DATA_DIR}")


if __name__ == "__main__":
    main()
