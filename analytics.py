"""
analytics.py - Library usage analysis with NumPy, Pandas and Matplotlib.

app.py reads the rows from MySQL and calls generate_all().
This file only analyses the data and draws charts; it never touches the database.

    MySQL rows -> Pandas table -> NumPy calculations -> Matplotlib charts
"""

import base64
import io

import matplotlib
matplotlib.use("Agg")  # draw into memory; a web server has no screen
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import MaxNLocator

# Colours (same navy as the dashboard)
NAVY = "#16213a"
BLUE = "#2f5d8a"
GREEN = "#3b7d5a"
RED = "#b03a22"


# ---------------------------------------------------------------------------
# 1. BUILD ONE BIG TABLE FROM THE MYSQL ROWS
# ---------------------------------------------------------------------------
def build_table(books_rows, borrowers_rows, loans_rows, fine_per_day):
    """Return (books, df). df has one row per loan with book + student details."""
    books = pd.DataFrame(books_rows)
    borrowers = pd.DataFrame(borrowers_rows)
    loans = pd.DataFrame(loans_rows)

    # Turn the date columns into real dates (empty return_date becomes NaT)
    for col in ("issue_date", "due_date", "return_date"):
        loans[col] = pd.to_datetime(loans[col])

    today = pd.Timestamp.today().normalize()
    returned = loans["return_date"].notna()          # True = book came back
    end_date = loans["return_date"].fillna(today)    # not returned yet -> use today

    # Days late = end date - due date, never below 0 (NumPy)
    loans["days_late"] = np.maximum((end_date - loans["due_date"]).dt.days, 0)

    # Same three labels as your dashboard: Returned / Overdue / Issued
    loans["status"] = np.where(
        returned,
        "Returned",
        np.where(loans["days_late"] > 0, "Overdue", "Issued"),
    )

    loans["fine"] = loans["days_late"] * fine_per_day

    # Attach book and student details to every loan (like a SQL JOIN)
    df = loans.merge(
        books[["book_id", "title", "category"]], on="book_id"
    ).merge(
        borrowers[["borrower_id", "borrower_name", "roll_no", "department"]],
        on="borrower_id",
    )
    return books, df


# ---------------------------------------------------------------------------
# 2. SMALL HELPERS
# ---------------------------------------------------------------------------
def to_base64(fig):
    """Turn a Matplotlib figure into a text string the HTML page can show."""
    fig.tight_layout()
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=100)
    plt.close(fig)  # free memory
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def tidy(ax, grid_axis="y"):
    """Remove the top/right border and add a light grid."""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis=grid_axis, alpha=0.25)
    ax.set_axisbelow(True)


def shorten(text, limit=34):
    """Cut very long book titles so the chart labels fit."""
    return text if len(text) <= limit else text[: limit - 3] + "..."


# ---------------------------------------------------------------------------
# 3. CHARTS
# ---------------------------------------------------------------------------
def chart_monthly_trend(df):
    """Books issued and returned in each month."""
    issued = df["issue_date"].dt.to_period("M").value_counts()
    returned = df["return_date"].dropna().dt.to_period("M").value_counts()

    last = issued.index.max()
    if len(returned):
        last = max(last, returned.index.max())

    # Every month between first and last, so empty months show as 0
    months = pd.period_range(issued.index.min(), last, freq="M")
    issued = issued.reindex(months, fill_value=0)
    returned = (returned.reindex(months, fill_value=0)
                if len(returned) else pd.Series(0, index=months))

    labels = list(months.strftime("%b %Y"))
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.plot(labels, issued.values, marker="o", color=BLUE, label="Issued")
    ax.plot(labels, returned.values, marker="o", color=GREEN, label="Returned")
    ax.set_title("Monthly Borrowing Trend", color=NAVY)
    ax.set_ylabel("Number of books")
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.legend(frameon=False)
    plt.setp(ax.get_xticklabels(), rotation=40, ha="right")
    tidy(ax)
    return to_base64(fig)


def chart_top_books(df):
    """Top 10 most borrowed books (borrowing frequency)."""
    top = df["title"].value_counts().head(10).sort_values()  # smallest first
    fig, ax = plt.subplots(figsize=(8, 4.8))
    bars = ax.barh([shorten(t) for t in top.index], top.values, color=BLUE)
    ax.bar_label(bars, padding=3)
    ax.set_title("Top 10 Most Borrowed Books", color=NAVY)
    ax.set_xlabel("Times borrowed")
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    tidy(ax, "x")
    return to_base64(fig)


def chart_category(df):
    """Loans per book category."""
    cat = df["category"].value_counts()
    fig, ax = plt.subplots(figsize=(8, 4.2))
    bars = ax.bar(cat.index, cat.values, color=NAVY)
    ax.bar_label(bars, padding=3)
    ax.set_title("Borrowing by Category", color=NAVY)
    ax.set_ylabel("Number of loans")
    plt.setp(ax.get_xticklabels(), rotation=25, ha="right")
    tidy(ax)
    return to_base64(fig)


def chart_availability(books):
    """Copies on the shelf vs copies currently out, per category."""
    stock = books.assign(issued=books["total_copies"] - books["copies_available"])
    by_cat = stock.groupby("category")[["copies_available", "issued"]].sum()

    fig, ax = plt.subplots(figsize=(8, 4.2))
    by_cat.plot(kind="bar", stacked=True, ax=ax, color=[GREEN, RED])
    ax.set_title("Book Availability by Category", color=NAVY)
    ax.set_xlabel("")
    ax.set_ylabel("Copies")
    ax.legend(["Available on shelf", "Currently issued"], frameon=False)
    plt.setp(ax.get_xticklabels(), rotation=25, ha="right")
    tidy(ax)
    return to_base64(fig)


def chart_dues(df):
    """Students with the highest pending fines (overdue, not yet returned)."""
    overdue = df[df["status"] == "Overdue"]
    per_student = (
        overdue.groupby(["roll_no", "borrower_name"])["fine"]
        .sum()
        .sort_values(ascending=False)
        .head(10)
    )

    fig, ax = plt.subplots(figsize=(8, 4.2))
    if per_student.empty:
        ax.text(0.5, 0.5, "No pending dues", ha="center", va="center", fontsize=14)
        ax.axis("off")
    else:
        names = [name for _, name in per_student.index]
        bars = ax.bar(names, per_student.values, color=RED)
        ax.bar_label(bars, labels=[f"Rs. {v}" for v in per_student.values], padding=3)
        ax.set_ylabel("Pending fine (Rs.)")
        plt.setp(ax.get_xticklabels(), rotation=35, ha="right")
        tidy(ax)
    ax.set_title("Pending Dues by Student (Top 10)", color=NAVY)
    return to_base64(fig)


def chart_department(df):
    """Which departments borrow the most."""
    dept = df["department"].value_counts().sort_values()
    fig, ax = plt.subplots(figsize=(8, 4.2))
    bars = ax.barh(dept.index, dept.values, color=BLUE)
    ax.bar_label(bars, padding=3)
    ax.set_title("Borrowing by Department", color=NAVY)
    ax.set_xlabel("Number of loans")
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    tidy(ax, "x")
    return to_base64(fig)


def chart_status(df):
    """Share of Returned / Issued / Overdue loans."""
    order = ["Returned", "Issued", "Overdue"]
    colours = {"Returned": GREEN, "Issued": BLUE, "Overdue": RED}
    counts = df["status"].value_counts().reindex(order, fill_value=0)
    counts = counts[counts > 0]  # skip empty slices

    fig, ax = plt.subplots(figsize=(5.5, 4.2))
    ax.pie(
        counts.values,
        labels=counts.index,
        colors=[colours[s] for s in counts.index],
        autopct="%1.0f%%",
        startangle=90,
        textprops={"color": NAVY},
    )
    ax.set_title("Loan Status Overview", color=NAVY)
    return to_base64(fig)


# ---------------------------------------------------------------------------
# 4. SUMMARY NUMBERS
# ---------------------------------------------------------------------------
def build_stats(books, df):
    returned = df[df["status"] == "Returned"]
    overdue = df[df["status"] == "Overdue"]
    avg_days = (returned["return_date"] - returned["issue_date"]).dt.days.mean()

    return {
        "total_loans": int(len(df)),
        "borrowed": int((df["status"] != "Returned").sum()),
        "overdue": int(len(overdue)),
        "students_with_dues": int(overdue["borrower_id"].nunique()),
        "pending_fine": int(overdue["fine"].sum()),
        # nan_to_num: if nothing is returned yet the average is NaN -> show 0
        "avg_days": round(float(np.nan_to_num(avg_days)), 1),
        "out_of_stock": int((books["copies_available"] == 0).sum()),
    }


# ---------------------------------------------------------------------------
# 5. MAIN FUNCTION (called from app.py)
# ---------------------------------------------------------------------------
def generate_all(books_rows, borrowers_rows, loans_rows, fine_per_day):
    """Return (stats, charts). charts = [{'title': ..., 'image': base64}, ...]"""
    if not loans_rows:
        return None, []  # nothing to analyse yet

    books, df = build_table(books_rows, borrowers_rows, loans_rows, fine_per_day)

    charts = [
        {"title": "Monthly borrowing trend", "image": chart_monthly_trend(df)},
        {"title": "Most borrowed books", "image": chart_top_books(df)},
        {"title": "Borrowing by category", "image": chart_category(df)},
        {"title": "Availability by category", "image": chart_availability(books)},
        {"title": "Pending dues by student", "image": chart_dues(df)},
        {"title": "Borrowing by department", "image": chart_department(df)},
        {"title": "Loan status", "image": chart_status(df)},
    ]
    return build_stats(books, df), charts
