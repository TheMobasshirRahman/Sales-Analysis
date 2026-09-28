#!/usr/bin/env python
# coding: utf-8

# # Sales Performance Analysis — BCA Data Analytics Test Project
# 
# **Dataset:** `BCA_Data_Analytics_Test_Project.xlsx` (3 sheets: Orders, Customers, Products) — calendar year 2025
# 
# **Objective:** Clean the raw sales data, validate it, and analyse sales, profitability, customers, products,
# salespeople and receivables to give management actionable recommendations.
# 
# **Workflow**
# 1. Load data
# 2. Data understanding
# 3. Data quality checks
# 4. Data cleaning & feature engineering
# 5. Export cleaned dataset (CSV / Excel / SQLite for SQL queries)
# 6. Exploratory analysis & KPIs
# 7. Key insights & recommendations

# In[1]:


import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from IPython.display import display

pd.set_option("display.float_format", lambda v: f"{v:,.2f}")
pd.set_option("display.width", 140)

DATA_DIR = Path("data")
CHART_DIR = Path("charts")
CHART_DIR.mkdir(exist_ok=True)
RAW_FILE = DATA_DIR / "BCA_Data_Analytics_Test_Project.xlsx"

# Consistent chart style
PRIMARY, ACCENT, MUTED, NEG = "#1F4E79", "#E07A1F", "#9DB4CC", "#C0392B"
plt.rcParams.update({
    "figure.figsize": (9, 4.5), "figure.dpi": 110, "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "grid.alpha": 0.25,
    "axes.titleweight": "bold", "axes.titlesize": 12, "font.size": 10,
})
lakh = mtick.FuncFormatter(lambda v, _: f"₹{v/1e5:,.1f}L")

def save(fig, name):
    fig.tight_layout()
    fig.savefig(CHART_DIR / f"{name}.png", dpi=150, bbox_inches="tight")
    plt.show()


# ## 1. Load data

# In[2]:


sheets = pd.read_excel(RAW_FILE, sheet_name=None)
orders_raw = sheets["Orders"].copy()
customers = sheets["Customers"].copy()
products = sheets["Products"].copy()

for name, df in [("Orders", orders_raw), ("Customers", customers), ("Products", products)]:
    print(f"{name:<10} rows={df.shape[0]:>5}  cols={df.shape[1]}")


# ## 2. Data understanding

# In[3]:


orders_raw.head()


# In[4]:


orders_raw.info()


# In[5]:


orders_raw.describe().T


# In[6]:


for col in ["payment_status", "salesperson"]:
    print(col, "->", orders_raw[col].value_counts().to_dict())
print("customer_type ->", customers["customer_type"].value_counts().to_dict())
print("city ->", customers["city"].value_counts().to_dict())
print("category ->", products["category"].value_counts().to_dict())
print("Order date range:", orders_raw["order_date"].min().date(), "to", orders_raw["order_date"].max().date())


# ## 3. Data quality checks
# Each check below looks for a specific type of problem. The summary table at the end lists every issue found.

# In[7]:


o = orders_raw
checks = {}

# 3.1 Missing values
checks["Missing values (any column)"] = o[o.isna().any(axis=1)]["order_id"].tolist()

# 3.2 Duplicates
checks["Duplicate order_id"] = o[o["order_id"].duplicated()]["order_id"].tolist()
checks["Fully duplicated rows"] = o[o.duplicated()]["order_id"].tolist()

# 3.3 Inconsistent text categories
valid_status = {"Paid", "Pending", "Overdue"}
checks["Invalid payment_status spelling/case"] = o[~o["payment_status"].isin(valid_status)]["order_id"].tolist()

# 3.4 Invalid / outlier numeric values
checks["Quantity <= 0"] = o[o["quantity"] <= 0]["order_id"].tolist()
q1, q3 = o["discount_pct"].quantile([0.25, 0.75])
upper = q3 + 1.5 * (q3 - q1)
checks[f"Discount outlier (> {upper:.0f}% IQR fence)"] = o[o["discount_pct"] > upper]["order_id"].tolist()

# 3.5 Referential integrity (foreign keys)
checks["customer_id not in Customers"] = o[~o["customer_id"].isin(customers["customer_id"])]["order_id"].tolist()
checks["product_id not in Products"] = o[~o["product_id"].isin(products["product_id"])]["order_id"].tolist()

# 3.6 Calculation consistency (should all be empty)
tol = 0.01
checks["gross_sales != qty x price"] = o[(o["quantity"] * o["selling_price"] - o["gross_sales"]).abs() > tol]["order_id"].tolist()
checks["net_sales != gross - discount"] = o[(o["gross_sales"] - o["discount_amount"] - o["net_sales"]).abs() > tol]["order_id"].tolist()
checks["profit != net - cost"] = o[(o["net_sales"] - o["cost"] - o["profit"]).abs() > tol]["order_id"].tolist()

# 3.7 Dates
checks["Order date outside 2025"] = o[o["order_date"].dt.year != 2025]["order_id"].tolist()

dq = pd.DataFrame(
    [(k, len(v), ", ".join(v) if v else "-") for k, v in checks.items()],
    columns=["Check", "Rows affected", "Order IDs"],
)
dq


# In[8]:


issue_ids = sorted({i for v in checks.values() for i in v})
orders_raw[orders_raw["order_id"].isin(issue_ids)]


# ## 4. Data cleaning
# 
# | # | Issue | Order | Decision | Reason |
# |---|---|---|---|---|
# | 1 | `payment_status` = `pending` (lower-case) | O00076 | Standardise to Title case (`Pending`) | Same category written differently would split counts |
# | 2 | `product_id` = `P999` not in Products, all price/sales/profit fields blank | O00056 | **Remove** | No product, price or revenue exists, so it cannot be analysed or reliably imputed |
# | 3 | `quantity` = -3 (negative sales & profit) | O00011 | **Remove** | Physically invalid quantity; likely a data-entry error or unrecorded return |
# | 4 | `customer_id` = `C999` not in Customers | O00041 | **Keep**, customer fields set to `Unknown` | Sales and profit values are valid, so removing it would understate revenue |
# | 5 | `discount_pct` = 35% (all others 0–20%) | O00026 | **Keep**, flag as `discount_outlier` | A real transaction that made a loss; it is a business issue to report, not a data error |
# 
# All numeric calculations (gross, net, cost, profit) were verified above and are consistent, so no values were recalculated.

# In[9]:


df = orders_raw.copy()
log = []

# 1. Standardise text columns
df["payment_status"] = df["payment_status"].str.strip().str.title()
df["salesperson"] = df["salesperson"].str.strip().str.title()
log.append(("Standardised payment_status / salesperson text", 0))

# 2. Remove order with unknown product and missing financials
mask = ~df["product_id"].isin(products["product_id"])
log.append(("Removed orders with unknown product_id (missing financials)", int(mask.sum())))
df = df[~mask]

# 3. Remove invalid quantity
mask = df["quantity"] <= 0
log.append(("Removed orders with quantity <= 0", int(mask.sum())))
df = df[~mask]

# 4 & 5. Flags
df["unknown_customer"] = ~df["customer_id"].isin(customers["customer_id"])
df["discount_outlier"] = df["discount_pct"] > 20

pd.DataFrame(log, columns=["Step", "Rows removed"])


# ### 4.1 Feature engineering & merge with master tables

# In[10]:


df = (
    df.merge(customers[["customer_id", "customer_name", "city", "customer_type"]], on="customer_id", how="left")
      .merge(products[["product_id", "product_name", "category"]], on="product_id", how="left")
)
for c in ["customer_name", "city", "customer_type"]:
    df[c] = df[c].fillna("Unknown")

df["order_month_num"] = df["order_date"].dt.month
df["order_month"] = df["order_date"].dt.strftime("%b")
df["year_month"] = df["order_date"].dt.strftime("%Y-%m")
df["quarter"] = "Q" + df["order_date"].dt.quarter.astype(str)
df["profit_margin_pct"] = (df["profit"] / df["net_sales"] * 100).round(2)
df["is_loss"] = df["profit"] < 0
df["discount_band"] = pd.cut(df["discount_pct"], bins=[-1, 0, 5, 10, 100],
                             labels=["0%", "1-5%", "6-10%", ">10%"]).astype(str)

money = ["unit_cost", "selling_price", "gross_sales", "discount_amount", "net_sales", "cost", "profit"]
df[money] = df[money].round(2)

cols = ["order_id", "order_date", "year_month", "order_month_num", "order_month", "quarter",
        "customer_id", "customer_name", "city", "customer_type",
        "product_id", "product_name", "category", "salesperson", "payment_status",
        "quantity", "unit_cost", "selling_price", "discount_pct", "discount_band",
        "gross_sales", "discount_amount", "net_sales", "cost", "profit", "profit_margin_pct",
        "is_loss", "unknown_customer", "discount_outlier"]
clean = df[cols].sort_values("order_id").reset_index(drop=True)
print("Cleaned shape:", clean.shape)
clean.head()


# ### 4.2 Validate the cleaned data

# In[11]:


assert clean["order_id"].is_unique
assert clean[money].notna().all().all()
assert (clean["quantity"] > 0).all()
assert set(clean["payment_status"]) == {"Paid", "Pending", "Overdue"}
assert clean["product_id"].isin(products["product_id"]).all()
print(f"All validation checks passed. Rows: raw={len(orders_raw)} -> clean={len(clean)} "
      f"({len(orders_raw) - len(clean)} removed)")


# ## 5. Export cleaned dataset

# In[12]:


clean.to_csv(DATA_DIR / "cleaned_data.csv", index=False)

with pd.ExcelWriter(DATA_DIR / "cleaned_data.xlsx") as xw:
    clean.to_excel(xw, sheet_name="Orders_Clean", index=False)
    customers.to_excel(xw, sheet_name="Customers", index=False)
    products.to_excel(xw, sheet_name="Products", index=False)
    dq.to_excel(xw, sheet_name="Data_Quality_Log", index=False)

# SQLite database used by queries.sql
db_path = DATA_DIR / "sales.db"
db_path.unlink(missing_ok=True)
with sqlite3.connect(db_path) as con:
    raw_sql = orders_raw.assign(order_date=orders_raw["order_date"].dt.strftime("%Y-%m-%d"))
    raw_sql.to_sql("orders_raw", con, index=False)
    clean_orders = clean[["order_id", "order_date", "customer_id", "product_id", "quantity", "discount_pct",
                          "payment_status", "salesperson", "unit_cost", "selling_price", "gross_sales",
                          "discount_amount", "net_sales", "cost", "profit"]]
    clean_orders.assign(order_date=clean_orders["order_date"].dt.strftime("%Y-%m-%d")).to_sql("orders", con, index=False)
    customers.assign(join_date=customers["join_date"].dt.strftime("%Y-%m-%d")).to_sql("customers", con, index=False)
    products.to_sql("products", con, index=False)

print("Saved: data/cleaned_data.csv, data/cleaned_data.xlsx, data/sales.db")


# ## 6. Exploratory analysis

# ### 6.1 Headline KPIs

# In[13]:


kpi = {
    "Total orders": len(clean),
    "Units sold": clean["quantity"].sum(),
    "Gross sales (₹)": clean["gross_sales"].sum(),
    "Discount given (₹)": clean["discount_amount"].sum(),
    "Net sales (₹)": clean["net_sales"].sum(),
    "Total cost (₹)": clean["cost"].sum(),
    "Profit (₹)": clean["profit"].sum(),
    "Profit margin (%)": clean["profit"].sum() / clean["net_sales"].sum() * 100,
    "Avg order value (₹)": clean["net_sales"].mean(),
    "Active customers": clean["customer_id"].nunique(),
    "Loss-making orders": int(clean["is_loss"].sum()),
}
pd.Series(kpi).to_frame("Value")


# ### 6.2 Monthly sales & profit trend

# In[14]:


monthly = (clean.groupby(["order_month_num", "order_month"])
                .agg(orders=("order_id", "count"), net_sales=("net_sales", "sum"), profit=("profit", "sum"))
                .reset_index())
monthly["margin_pct"] = monthly["profit"] / monthly["net_sales"] * 100
monthly["mom_growth_pct"] = monthly["net_sales"].pct_change() * 100

fig, ax = plt.subplots()
ax.plot(monthly["order_month"], monthly["net_sales"], marker="o", color=PRIMARY, lw=2, label="Net sales")
ax.bar(monthly["order_month"], monthly["profit"], color=ACCENT, alpha=0.8, label="Profit")
ax.yaxis.set_major_formatter(lakh)
ax.set_title("Monthly Net Sales and Profit — 2025")
ax.legend(frameon=False)
save(fig, "01_monthly_trend")
monthly


# ### 6.3 Category performance

# In[15]:


category = (clean.groupby("category")
                 .agg(orders=("order_id", "count"), units=("quantity", "sum"),
                      net_sales=("net_sales", "sum"), profit=("profit", "sum"))
                 .sort_values("net_sales", ascending=False))
category["margin_pct"] = category["profit"] / category["net_sales"] * 100
category["sales_share_pct"] = category["net_sales"] / category["net_sales"].sum() * 100

fig, ax = plt.subplots()
ax.barh(category.index[::-1], category["net_sales"][::-1], color=PRIMARY, label="Net sales")
ax.barh(category.index[::-1], category["profit"][::-1], color=ACCENT, label="Profit")
for y, (s, m) in enumerate(zip(category["net_sales"][::-1], category["margin_pct"][::-1])):
    ax.text(s, y, f"  margin {m:.1f}%", va="center", fontsize=9)
ax.xaxis.set_major_formatter(lakh)
ax.set_title("Net Sales and Profit by Category")
ax.legend(frameon=False, loc="lower right")
save(fig, "02_category")
category


# ### 6.4 Top & bottom products

# In[16]:


product = (clean.groupby(["product_id", "product_name", "category"])
                .agg(units=("quantity", "sum"), net_sales=("net_sales", "sum"), profit=("profit", "sum"))
                .reset_index())
product["margin_pct"] = product["profit"] / product["net_sales"] * 100
top10 = product.nlargest(10, "net_sales")

fig, ax = plt.subplots()
ax.barh(top10["product_name"][::-1], top10["net_sales"][::-1], color=PRIMARY)
ax.xaxis.set_major_formatter(lakh)
ax.set_title("Top 10 Products by Net Sales")
save(fig, "03_top_products")

print("Top 10 by net sales"); display(top10)
print("Lowest 5 by profit margin"); display(product.nsmallest(5, "margin_pct"))


# ### 6.5 City & customer type

# In[17]:


city = (clean.groupby("city")
             .agg(customers=("customer_id", "nunique"), orders=("order_id", "count"),
                  net_sales=("net_sales", "sum"), profit=("profit", "sum"))
             .sort_values("net_sales", ascending=False))
city["margin_pct"] = city["profit"] / city["net_sales"] * 100

ctype = (clean.groupby("customer_type")
              .agg(customers=("customer_id", "nunique"), orders=("order_id", "count"),
                   net_sales=("net_sales", "sum"), profit=("profit", "sum"),
                   avg_order_value=("net_sales", "mean"))
              .sort_values("net_sales", ascending=False))
ctype["margin_pct"] = ctype["profit"] / ctype["net_sales"] * 100

fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
axes[0].bar(city.index, city["net_sales"], color=PRIMARY)
axes[0].yaxis.set_major_formatter(lakh); axes[0].set_title("Net Sales by City")
axes[0].tick_params(axis="x", rotation=35)
axes[1].bar(ctype.index, ctype["net_sales"], color=[PRIMARY, ACCENT, MUTED][:len(ctype)])
axes[1].yaxis.set_major_formatter(lakh); axes[1].set_title("Net Sales by Customer Type")
save(fig, "04_city_customer_type")
display(city); display(ctype)


# ### 6.6 Top customers

# In[18]:


cust = (clean.groupby(["customer_id", "customer_name", "city", "customer_type"])
             .agg(orders=("order_id", "count"), net_sales=("net_sales", "sum"), profit=("profit", "sum"))
             .reset_index().sort_values("net_sales", ascending=False))
cust["cum_share_pct"] = cust["net_sales"].cumsum() / cust["net_sales"].sum() * 100
top20pct = int(np.ceil(len(cust) * 0.2))
print(f"Top 20% of customers ({top20pct}) generate {cust['cum_share_pct'].iloc[top20pct - 1]:.1f}% of net sales")
cust.head(10)


# ### 6.7 Salesperson performance

# In[19]:


sp = (clean.groupby("salesperson")
           .agg(orders=("order_id", "count"), net_sales=("net_sales", "sum"), profit=("profit", "sum"),
                avg_discount_pct=("discount_pct", "mean"), loss_orders=("is_loss", "sum"),
                overdue_orders=("payment_status", lambda s: (s == "Overdue").sum()))
           .sort_values("net_sales", ascending=False))
sp["margin_pct"] = sp["profit"] / sp["net_sales"] * 100

fig, ax = plt.subplots()
x = np.arange(len(sp))
ax.bar(x - 0.2, sp["net_sales"], 0.4, color=PRIMARY, label="Net sales")
ax.bar(x + 0.2, sp["profit"], 0.4, color=ACCENT, label="Profit")
ax.set_xticks(x, sp.index)
ax.yaxis.set_major_formatter(lakh)
ax.set_title("Salesperson Performance")
ax.legend(frameon=False)
save(fig, "05_salesperson")
sp


# ### 6.8 Payment status & receivables risk

# In[20]:


pay = (clean.groupby("payment_status")
            .agg(orders=("order_id", "count"), net_sales=("net_sales", "sum"))
            .reindex(["Paid", "Pending", "Overdue"]))
pay["share_pct"] = pay["net_sales"] / pay["net_sales"].sum() * 100

fig, ax = plt.subplots(figsize=(5.5, 4.5))
ax.pie(pay["net_sales"], labels=pay.index, autopct="%1.1f%%", startangle=90,
       colors=[PRIMARY, MUTED, NEG], wedgeprops=dict(width=0.45, edgecolor="white"))
ax.set_title("Net Sales by Payment Status")
save(fig, "06_payment_status")
display(pay)

overdue_cust = (clean[clean["payment_status"] == "Overdue"]
                .groupby(["customer_id", "customer_name", "city"])
                .agg(overdue_orders=("order_id", "count"), overdue_amount=("net_sales", "sum"))
                .sort_values("overdue_amount", ascending=False).head(10))
print("Top 10 customers by overdue amount"); overdue_cust


# ### 6.9 Discount impact on profitability

# In[21]:


band_order = ["0%", "1-5%", "6-10%", ">10%"]
disc = (clean.groupby("discount_band")
             .agg(orders=("order_id", "count"), net_sales=("net_sales", "sum"), profit=("profit", "sum"),
                  loss_orders=("is_loss", "sum"))
             .reindex(band_order))
disc["margin_pct"] = disc["profit"] / disc["net_sales"] * 100

fig, ax = plt.subplots()
bars = ax.bar(disc.index, disc["margin_pct"], color=[PRIMARY, PRIMARY, ACCENT, NEG])
ax.bar_label(bars, fmt="%.1f%%")
ax.set_ylabel("Profit margin %"); ax.set_xlabel("Discount band")
ax.set_title("Higher Discounts Erode Profit Margin")
save(fig, "07_discount_margin")
print("Correlation (discount % vs margin %):", round(clean["discount_pct"].corr(clean["profit_margin_pct"]), 3))
disc


# ### 6.10 Loss-making orders

# In[22]:


loss = clean[clean["is_loss"]]
print(f"{len(loss)} loss-making orders, total loss ₹{-loss['profit'].sum():,.0f}")
print("Average discount on loss orders: {:.1f}% vs {:.1f}% overall".format(
      loss["discount_pct"].mean(), clean["discount_pct"].mean()))
loss.groupby(["category"]).agg(orders=("order_id", "count"), loss=("profit", "sum")).sort_values("loss")


# ### 6.11 Quarterly summary

# In[23]:


qtr = clean.groupby("quarter").agg(orders=("order_id", "count"), net_sales=("net_sales", "sum"), profit=("profit", "sum"))
qtr["margin_pct"] = qtr["profit"] / qtr["net_sales"] * 100
qtr


# ## 7. Key insights & recommendations
# 
# ### Key insights
# 1. **Overall performance:** 1,198 valid orders generated **₹2.31 Cr net sales** and **₹37.9 L profit** (16.4% margin) in 2025. ₹15.5 L (6.3% of gross sales) was given away as discounts.
# 2. **Stable but flat sales:** Monthly net sales range between ₹15.3 L and ₹22.1 L with no clear growth trend. **May** was the best month and **July** the weakest (-25% vs June). Q2 and Q4 were the strongest quarters.
# 3. **Hardware leads revenue, Plumbing leads margin:** Hardware is 36.6% of sales. Plumbing (19.8%) and Electrical (18.9%) have the best margins. **Safety has only a 9.5% margin**, and Paint (14.6%) is below average.
# 4. **Discounts drive losses:** Margin falls from **22.2% at 0% discount to 7.6% at >10% discount** (correlation -0.53). **All 23 loss-making orders had discounts above 10%**, averaging 15.9% compared with 6.2% overall.
# 5. **Weak products:** Product 4 (Hardware) is the 5th-largest product by sales but earns only a 5.6% margin. Products 1, 2 and 18 are also below 8%.
# 6. **Receivables risk:** **31% of net sales (₹71.8 L) is not yet collected**: ₹48.3 L Pending and **₹23.5 L Overdue**. Overdue amounts are spread across many customers; the top 10 together account for about ₹9 L.
# 7. **Salespeople:** Amit leads on both sales (₹52.5 L) and margin (16.7%). Neha has the most overdue orders (29), and Imran has the lowest margin (16.0%).
# 8. **Diversified customer base:** The top 20% of customers contribute only 29% of sales, so there is low dependence on any single customer. Retailers bring in 51% of sales. Varanasi is the top city (₹41.2 L).
# 
# ### Recommendations
# 1. **Cap discounts at 10%** without manager approval. Every loss in 2025 came from discounts above that level.
# 2. **Review pricing of low-margin products** (Product 4, 1, 2 and 18) and of the Safety category, or push higher-margin Plumbing and Electrical products instead.
# 3. **Run a collections drive** on the ₹23.5 L overdue amount, starting with the top 10 overdue customers. Link part of salesperson incentives to collections.
# 4. **Fix data capture:** make product and customer IDs mandatory dropdowns (to stop entries like P999 and C999), block quantity ≤ 0, and use a fixed list for payment status.
# 5. **Plan promotions for slow months** (Feb–Mar, Jul, Sep) to smooth out the sales dips.
