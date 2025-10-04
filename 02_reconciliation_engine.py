"""
02_reconciliation_engine.py
---------------------------
Automated Bank Reconciliation & Financial Controls engine.

3-pass matching waterfall (industry standard approach):
  Pass 1 : Exact match      -> ref + amount + date + direction
  Pass 2 : Timing match     -> ref + amount + direction, date within tolerance (T+3)
  Pass 3 : Amount tolerance -> ref + direction + date window, small amount diff (fees/errors)

Unmatched items are categorized into standard break types, aged,
and passed through a financial-controls layer:
  - High-value escalation (>= INR 1,00,000)
  - Duplicate posting detection (control failure flag)
  - Maker-Checker workflow columns
  - Full audit trail

Run:  python 02_reconciliation_engine.py
Reads : ../data/*.csv
Writes: ../output/*.csv + recon summary
"""

import csv
from collections import defaultdict
from datetime import datetime, date
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA, OUT = BASE / "data", BASE / "output"
OUT.mkdir(exist_ok=True)

AS_OF = date(2025, 8, 20)          # reconciliation "as of" date
DATE_TOLERANCE_DAYS = 3            # T+3 clearing window
AMOUNT_TOLERANCE = 600.0           # max fee/posting-error tolerance (INR)
HIGH_VALUE_THRESHOLD = 100_000.0   # escalation threshold (INR)


def load(path, ref_col, date_col):
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            r["_ref"] = r[ref_col].strip()
            r["_base_ref"] = r["_ref"].split("-")[0]       # TXN0000001-D -> TXN0000001
            r["_date"] = datetime.strptime(r[date_col], "%Y-%m-%d").date()
            r["_amt"] = float(r["amount"])
            r["_matched"] = False
            rows.append(r)
    return rows


def aging_bucket(txn_date):
    days = (AS_OF - txn_date).days
    if days <= 30:
        return "0-30 days"
    if days <= 60:
        return "31-60 days"
    if days <= 90:
        return "61-90 days"
    return "90+ days"


def main():
    gl = load(DATA / "general_ledger.csv", "gl_ref", "posting_date")
    bank = load(DATA / "bank_statement.csv", "bank_ref", "value_date")

    # ---------- index bank rows by base ref for O(1) lookups ----------
    bank_idx = defaultdict(list)
    for b in bank:
        bank_idx[b["_base_ref"]].append(b)

    matched, audit = [], []

    def record_match(g, b, pass_name, note=""):
        g["_matched"] = b["_matched"] = True
        diff = round(g["_amt"] - b["_amt"], 2)
        matched.append({
            "gl_ref": g["_ref"], "bank_ref": b["_ref"],
            "gl_date": g["_date"], "bank_date": b["_date"],
            "gl_amount": g["_amt"], "bank_amount": b["_amt"],
            "amount_diff": diff, "date_lag_days": (b["_date"] - g["_date"]).days,
            "drcr": g["drcr"], "counterparty": g["counterparty"],
            "match_pass": pass_name, "note": note,
        })
        audit.append([datetime.now().isoformat(timespec="seconds"), "MATCH",
                      g["_ref"], b["_ref"], pass_name, note])

    # =============== PASS 1 : EXACT ===============
    for g in gl:
        if g["_matched"]:
            continue
        for b in bank_idx.get(g["_base_ref"], []):
            if (not b["_matched"] and b["_amt"] == g["_amt"]
                    and b["_date"] == g["_date"] and b["drcr"] == g["drcr"]):
                record_match(g, b, "P1-EXACT")
                break

    # =============== PASS 2 : TIMING (T+3) ===============
    for g in gl:
        if g["_matched"]:
            continue
        for b in bank_idx.get(g["_base_ref"], []):
            if (not b["_matched"] and b["_amt"] == g["_amt"] and b["drcr"] == g["drcr"]
                    and 0 < (b["_date"] - g["_date"]).days <= DATE_TOLERANCE_DAYS):
                record_match(g, b, "P2-TIMING", f"bank cleared T+{(b['_date'] - g['_date']).days}")
                break

    # =============== PASS 3 : AMOUNT TOLERANCE ===============
    for g in gl:
        if g["_matched"]:
            continue
        for b in bank_idx.get(g["_base_ref"], []):
            if (not b["_matched"] and b["drcr"] == g["drcr"]
                    and abs((b["_date"] - g["_date"]).days) <= DATE_TOLERANCE_DAYS
                    and 0 < abs(b["_amt"] - g["_amt"]) <= AMOUNT_TOLERANCE):
                record_match(g, b, "P3-AMOUNT-TOL",
                             f"amount diff {round(g['_amt'] - b['_amt'], 2)} (probable bank fee/posting error)")
                break

    # =============== EXCEPTIONS & CATEGORIZATION ===============
    # duplicate detection: same base ref appearing more than once in GL
    ref_count = defaultdict(int)
    for g in gl:
        ref_count[g["_base_ref"]] += 1

    exceptions = []

    def add_exception(row, source, category, detail):
        high_value = row["_amt"] >= HIGH_VALUE_THRESHOLD
        exceptions.append({
            "ref": row["_ref"], "source": source, "txn_date": row["_date"],
            "counterparty": row["counterparty"], "drcr": row["drcr"], "amount": row["_amt"],
            "break_category": category, "detail": detail,
            "aging_bucket": aging_bucket(row["_date"]),
            "days_open": (AS_OF - row["_date"]).days,
            "high_value_flag": "YES" if high_value else "NO",
            "escalation": "ESCALATE-L2" if high_value else "STANDARD-QUEUE",
            "maker": "recon.analyst01", "maker_status": "REVIEWED",
            "checker": "recon.supervisor" if high_value else "auto.checker",
            "checker_status": "PENDING-APPROVAL",
        })
        audit.append([datetime.now().isoformat(timespec="seconds"), "EXCEPTION",
                      row["_ref"], "", category, detail])

    for g in gl:
        if g["_matched"]:
            continue
        if g["_ref"].endswith("-D") or ref_count[g["_base_ref"]] > 1 and g["_ref"].endswith("-D"):
            add_exception(g, "GL", "DUPLICATE POSTING",
                          "Same reference posted twice in GL - control failure, reverse duplicate")
        elif g["_base_ref"] in bank_idx:
            add_exception(g, "GL", "UNRESOLVED MISMATCH",
                          "Ref exists in bank but outside matching tolerances - manual review")
        else:
            add_exception(g, "GL", "MISSING IN BANK",
                          "Deposit in transit / unpresented cheque - follow up with bank")

    for b in bank:
        if b["_matched"]:
            continue
        if b["_ref"].startswith("BNK") or b["mode"] == "SYS":
            add_exception(b, "BANK", "MISSING IN GL - BANK CHARGES",
                          "Bank charge/interest not booked - raise JV to book in GL")
        else:
            add_exception(b, "BANK", "MISSING IN GL",
                          "Bank txn not recorded in books - investigate & book entry")

    # =============== WRITE OUTPUTS ===============
    with open(OUT / "matched_transactions.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(matched[0].keys()))
        w.writeheader()
        w.writerows(matched)

    exceptions.sort(key=lambda x: (-float(x["amount"]), x["days_open"]), reverse=False)
    with open(OUT / "exceptions_report.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(exceptions[0].keys()))
        w.writeheader()
        w.writerows(exceptions)

    with open(OUT / "audit_trail.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "action", "primary_ref", "secondary_ref", "category", "detail"])
        w.writerows(audit)

    # aging summary
    aging = defaultdict(lambda: [0, 0.0])
    for e in exceptions:
        aging[e["aging_bucket"]][0] += 1
        aging[e["aging_bucket"]][1] += float(e["amount"])
    with open(OUT / "aging_analysis.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["aging_bucket", "open_items", "total_value_inr"])
        for bucket in ["0-30 days", "31-60 days", "61-90 days", "90+ days"]:
            w.writerow([bucket, aging[bucket][0], round(aging[bucket][1], 2)])

    # =============== SUMMARY ===============
    total_gl = len(gl)
    total_bank = len(bank)
    match_rate = len(matched) / total_gl * 100
    by_pass = defaultdict(int)
    for m in matched:
        by_pass[m["match_pass"]] += 1
    by_cat = defaultdict(lambda: [0, 0.0])
    for e in exceptions:
        by_cat[e["break_category"]][0] += 1
        by_cat[e["break_category"]][1] += float(e["amount"])
    high_val = sum(1 for e in exceptions if e["high_value_flag"] == "YES")

    lines = [
        "=" * 62,
        "        BANK RECONCILIATION SUMMARY  |  As of 2025-08-20",
        "=" * 62,
        f"GL transactions            : {total_gl:>10,}",
        f"Bank statement lines       : {total_bank:>10,}",
        f"Matched pairs              : {len(matched):>10,}",
        f"AUTO-MATCH RATE            : {match_rate:>9.2f} %",
        "-" * 62,
        "Match waterfall:",
        *[f"  {p:<18}: {c:,}" for p, c in sorted(by_pass.items())],
        "-" * 62,
        "Open exceptions by category:",
        *[f"  {cat:<32}: {c[0]:>5,} items | INR {c[1]:>15,.2f}"
          for cat, c in sorted(by_cat.items(), key=lambda x: -x[1][1])],
        "-" * 62,
        f"High-value exceptions (>= INR 1L) escalated to L2: {high_val}",
        f"Total open exceptions      : {len(exceptions):,}",
        "=" * 62,
    ]
    summary = "\n".join(lines)
    (OUT / "recon_summary.txt").write_text(summary)
    print(summary)

    # machine-readable summary for the dashboard
    with open(OUT / "summary_kpis.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["kpi", "value"])
        w.writerow(["gl_count", total_gl])
        w.writerow(["bank_count", total_bank])
        w.writerow(["matched", len(matched)])
        w.writerow(["match_rate_pct", round(match_rate, 2)])
        w.writerow(["open_exceptions", len(exceptions)])
        w.writerow(["high_value_escalations", high_val])
        for p, c in by_pass.items():
            w.writerow([f"pass_{p}", c])
        for cat, c in by_cat.items():
            w.writerow([f"cat_{cat}", c[0]])
            w.writerow([f"catval_{cat}", round(c[1], 2)])


if __name__ == "__main__":
    main()
