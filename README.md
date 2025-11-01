# 🏦 Bank Reconciliation & Financial Controls — Automation Project

> **End-to-end automated bank reconciliation system** that matches 10K+ transactions between a bank statement and the internal General Ledger using a 3-pass matching waterfall, categorizes exceptions, performs aging analysis, and applies banking-grade financial controls (maker-checker, high-value escalation, duplicate detection, audit trail).

**Tech stack:** Python (pure stdlib — runs anywhere) · SQL (MySQL/PostgreSQL) · Excel/Power BI-ready outputs · HTML dashboard

---

## 📌 Business Problem

Banks and corporates reconcile their **internal books (General Ledger)** against the **bank statement** daily. Differences ("breaks") arise from:
- ⏱ **Timing differences** — bank clears a payment T+1 to T+3 days late
- 💸 **Amount mismatches** — bank fees deducted, posting errors
- 🏦 **Missing in Bank** — deposits in transit, unpresented cheques
- 📕 **Missing in GL** — bank charges/interest never booked in books
- ⚠️ **Duplicate postings** — control failures in the ERP

Unresolved breaks = misstated cash balance = regulatory & audit risk. This project automates the entire process the way Reconciliation/Financial Control teams at **Barclays, JPMC, Citi, Amex, Deutsche Bank** do it.

---

## 🔧 How It Works

### 1️⃣ Data Generation (`scripts/01_generate_data.py`)
Creates realistic simulated data:
- **9,851 GL transactions** & **9,876 bank statement lines** (Jun–Aug 2025)
- NEFT/RTGS/IMPS/UPI/Cheque modes, 20 counterparties, ₹500 – ₹50L amounts
- Injects controlled breaks: timing lags, fee deductions, in-transit items, unbooked bank charges, 40 duplicate postings

### 2️⃣ Reconciliation Engine (`scripts/02_reconciliation_engine.py`)
**3-pass matching waterfall** (industry-standard approach):

| Pass | Logic | Matched |
|---|---|---|
| **P1 — Exact** | ref + date + amount + DR/CR | 9,004 |
| **P2 — Timing** | ref + amount, date within T+3 | 344 |
| **P3 — Amount Tolerance** | ref + date window, diff ≤ ₹600 (fees) | 219 |

**Result: 97.12% auto-match rate** — remaining 593 items flow to the exception queue.

### 3️⃣ Exception Management
Every unmatched item is **categorized** and **aged**:

| Break Category | Items | Value |
|---|---|---|
| Missing in Bank (in-transit) | 244 | ₹12.14 Cr |
| Missing in GL (unbooked) | 189 | ₹10.71 Cr |
| Duplicate Posting (control failure) | 40 | ₹1.59 Cr |
| Bank Charges not booked | 120 | ₹15.1 L |

Aging buckets: 0-30 / 31-60 / 61-90 / 90+ days with SLA breach flags.

### 4️⃣ Financial Controls Layer 🛡
- **High-value escalation:** breaks ≥ ₹1,00,000 auto-routed to L2 queue (203 items)
- **Maker-Checker:** every exception carries maker/checker columns — segregation of duties
- **Duplicate detection:** same base reference posted twice → flagged for reversal + RCA
- **Audit trail:** every match & exception logged with timestamp (`output/audit_trail.csv`)

### 5️⃣ Reporting
- `output/matched_transactions.csv` — full match register with pass & lag details
- `output/exceptions_report.csv` — prioritized break queue (value × age sorted)
- `output/aging_analysis.csv` — aging summary for MI reporting
- `output/recon_summary.txt` — daily sign-off summary
- `dashboard/recon_dashboard.html` — management dashboard (open in any browser)
- `sql/reconciliation_queries.sql` — same logic in SQL (9 production-style queries)

---

## ▶️ How to Run

```bash
cd scripts
python 01_generate_data.py        # generates data/
python 02_reconciliation_engine.py # writes output/ + prints summary
```
No external libraries needed (pure Python stdlib). Load the CSVs into MySQL/PostgreSQL to run the SQL versions, or into Power BI/Excel for visuals.

---

## 📄 Resume Bullets (copy-paste ready)

> - Built an automated bank reconciliation engine in **Python & SQL** processing **10K+ transactions**, achieving a **97% auto-match rate** through a 3-pass matching waterfall (exact, T+3 timing, fee-tolerance).
> - Designed an **exception management workflow** categorizing breaks into 4 standard types with **aging analysis** and SLA breach tracking across ₹24Cr+ of open exposure.
> - Implemented **banking-grade financial controls** — maker-checker segregation, ₹1L+ high-value escalation queue, duplicate-posting detection, and full audit trail.
> - Delivered a **management dashboard** (match-rate KPIs, break trends, aging buckets, escalation queue) used for daily sign-off reporting.

---

## 🎤 Interview Q&A Prep

**Q: What is a reconciliation "break"?**
A: Any transaction that appears in one source (GL or bank statement) but can't be matched to the other within tolerances. Breaks must be investigated, categorized, and cleared within SLA.

**Q: Why a 3-pass waterfall instead of one query?**
A: You match on the strictest criteria first (exact) so high-confidence pairs are locked in, then progressively relax rules (timing, then amount tolerance). This minimizes false matches — a fuzzy rule applied first could wrongly pair transactions.

**Q: What is maker-checker and why does it matter?**
A: Segregation of duties — the analyst (maker) who investigates a break cannot also approve its resolution; a supervisor (checker) signs off. Prevents fraud and errors; it's a core SOX/RBI control.

**Q: What would you do with a 90-day-old high-value break?**
A: Escalate per matrix, investigate root cause (contact bank/counterparty, check for booking errors), raise adjusting JV if needed with checker approval, and document in the audit trail. Persistent aged breaks may indicate process or control failure needing RCA.

**Q: How would you improve this system?**
A: ML-based fuzzy matching on narration text, real-time recon via bank APIs instead of EOD batch, auto-JV creation for known bank charges, and Nostro/multi-account netting support.

---

## 📁 Project Structure
```
Repo-5/
├── data/
│   ├── general_ledger.csv        (9,851 rows)
│   └── bank_statement.csv        (9,876 rows)
├── scripts/
│   ├── 01_generate_data.py
│   └── 02_reconciliation_engine.py
├── sql/
│   └── reconciliation_queries.sql
├── output/
│   ├── matched_transactions.csv
│   ├── exceptions_report.csv
│   ├── aging_analysis.csv
│   ├── audit_trail.csv
│   ├── summary_kpis.csv
│   └── recon_summary.txt
├── dashboard/
│   └── recon_dashboard.html
└── README.md
```

*All data is fully simulated.*

## Author

Adveidh Krishna

Financial Analyst

[LinkedIn](https://www.linkedin.com/in/akthotarath)
