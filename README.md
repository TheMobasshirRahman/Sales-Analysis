# BCA Data Analytics Test Project — Submission

| # | Deliverable | File |
|---|---|---|
| 1 | Python analysis (cleaning + EDA) | `analysis.ipynb` (also `analysis.py`) |
| 2 | SQL queries (20 queries, SQLite) | `queries.sql` (run against `data/sales.db`) |
| 3 | Cleaned dataset | `data/cleaned_data.csv` (also `data/cleaned_data.xlsx` with master sheets + DQ log) |
| 4 | Dashboard | `Excel_Dashboard.xlsx` (interactive: Salesperson and Category filters) |
| 5 | One-page management report | `Management_Report.pdf` |

Other folders: `charts/` (PNG charts from the notebook), `data/BCA_Data_Analytics_Test_Project.xlsx` (raw input), `report_src/` (HTML source of the report).

## How to run
```bash
pip install pandas openpyxl matplotlib jupyter
jupyter notebook analysis.ipynb        # Run All: regenerates data/cleaned_data.*, data/sales.db, charts/
sqlite3 data/sales.db < queries.sql    # or open sales.db in DB Browser for SQLite
```

## Cleaning summary
Raw 1,200 orders → 1,198 clean orders.
- Removed **O00056** (product P999 does not exist, and sales values are blank) and **O00011** (quantity −3).
- Kept **O00041** (customer C999 not in master) with customer fields set to `Unknown`.
- Kept and flagged **O00026** (35% discount outlier).
- Standardised **O00076** payment status from `pending` to `Pending`.
