import os
import sqlite3
import time
from datetime import datetime
from flask import Flask, request, redirect, render_template_string
from google import genai
import markdown

app = Flask(__name__)

# ============================================================
# GEMINI SETUP
# ============================================================

MODEL = "gemini-3.8-flash"

API_KEY = os.environ.get("GEMINI_API_KEY")

if not API_KEY:
    raise ValueError(
        "GEMINI_API_KEY environment variable is missing."
    )

client = genai.Client(api_key=API_KEY)


# ============================================================
# DATABASE
# ============================================================

DB_NAME = "money_detective.db"


def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL NOT NULL,
            description TEXT NOT NULL,
            category TEXT,
            expense_date TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


init_db()


# ============================================================
# CATEGORY DETECTION
# ============================================================

def detect_category(description):

    text = description.lower()

    food_words = [
        "food", "lunch", "dinner", "breakfast",
        "meal", "biryani", "rice", "snack",
        "sandwich", "canteen", "pizza", "burger"
    ]

    drink_words = [
        "coffee", "tea", "juice", "drink",
        "cool drink", "beverage"
    ]

    transport_words = [
        "auto", "uber", "ola", "bus", "metro",
        "cab", "taxi", "petrol", "fuel",
        "transport", "ride"
    ]

    study_words = [
        "book", "books", "xerox", "print",
        "printing", "assignment", "notebook",
        "pen", "college", "course", "study"
    ]

    shopping_words = [
        "shirt", "dress", "clothes", "shoes",
        "slippers", "bag", "shopping",
        "amazon", "flipkart", "makeup"
    ]

    entertainment_words = [
        "movie", "game", "concert", "netflix",
        "subscription", "entertainment"
    ]

    for word in food_words:
        if word in text:
            return "Food"

    for word in drink_words:
        if word in text:
            return "Drinks"

    for word in transport_words:
        if word in text:
            return "Transport"

    for word in study_words:
        if word in text:
            return "Study"

    for word in shopping_words:
        if word in text:
            return "Shopping"

    for word in entertainment_words:
        if word in text:
            return "Entertainment"

    return "Other"


# ============================================================
# GET THIS MONTH'S EXPENSES
# ============================================================

def get_month_expenses():

    current_month = datetime.now().strftime("%Y-%m")

    conn = get_db()

    expenses = conn.execute("""
        SELECT *
        FROM expenses
        WHERE substr(expense_date, 1, 7) = ?
        ORDER BY id DESC
    """, (current_month,)).fetchall()

    conn.close()

    return expenses


# ============================================================
# CALCULATE TOTALS
# ============================================================

def calculate_totals():

    current_date = datetime.now().strftime("%Y-%m-%d")
    current_month = datetime.now().strftime("%Y-%m")

    conn = get_db()

    today_result = conn.execute("""
        SELECT COALESCE(SUM(amount), 0)
        FROM expenses
        WHERE expense_date = ?
    """, (current_date,)).fetchone()

    month_result = conn.execute("""
        SELECT COALESCE(SUM(amount), 0)
        FROM expenses
        WHERE substr(expense_date, 1, 7) = ?
    """, (current_month,)).fetchone()

    conn.close()

    today_total = today_result[0]
    month_total = month_result[0]

    return today_total, month_total


# ============================================================
# CATEGORY TOTALS
# ============================================================

def get_category_totals():

    current_month = datetime.now().strftime("%Y-%m")

    conn = get_db()

    results = conn.execute("""
        SELECT category, SUM(amount) AS total
        FROM expenses
        WHERE substr(expense_date, 1, 7) = ?
        GROUP BY category
        ORDER BY total DESC
    """, (current_month,)).fetchall()

    conn.close()

    return results


# ============================================================
# GEMINI ANALYSIS
# ============================================================

def analyze_spending(expenses):

    if not expenses:
        return "No expenses recorded yet."

    spending_text = ""

    for expense in expenses:
        spending_text += (
            f"- ₹{expense['amount']:.2f} | "
            f"{expense['description']} | "
            f"{expense['category']} | "
            f"{expense['expense_date']}\n"
        )

    prompt = f"""
You are Money Detective, an AI spending-analysis agent.

Analyze ONLY the actual expenses provided below.

EXPENSE HISTORY:
{spending_text}

Your job is to discover useful patterns in the user's spending.

Give a SHORT and specific analysis using exactly these sections:

## 💸 Where I Used Money Unnecessarily
Identify expenses that appear potentially avoidable based ONLY on the data.
Do not claim something is unnecessary if the data does not support it.

## 🔎 My Biggest Money Leak
Identify the category, repeated expense, or pattern that is consuming the most money.

## 💡 How I Can Save Money
Give 2 or 3 practical suggestions directly based on the user's actual expenses.

## 📊 My Spending Pattern
Mention the most noticeable spending pattern using actual amounts/categories.

## 🎯 One Action For Me
Give ONE simple action the user can take.

IMPORTANT RULES:
- Use the actual expenses.
- Do not invent expenses.
- Do not assume the user's income.
- Do not make psychological assumptions.
- Do not tell the user to eliminate necessary expenses.
- Avoid generic financial advice.
- Keep the response concise.
- Use Indian rupee ₹.
"""

    for attempt in range(3):

        try:

            response = client.models.generate_content(
                model=MODEL,
                contents=prompt
            )

            return response.text

        except Exception as e:

            error_text = str(e)

            if (
                "503" in error_text
                or "UNAVAILABLE" in error_text
            ):

                if attempt < 2:
                    time.sleep(5)
                    continue

                return """
## ⚠️ Gemini Temporarily Unavailable

Gemini is currently experiencing high demand.

Your expenses are safely stored in the database.

Please try the **Analyze My Spending** button again in a little while.
"""

            else:
                return f"""
## ⚠️ Analysis Error

Something went wrong while contacting Gemini.

Your expenses are still safely stored.

Error:
{error_text}
"""


# ============================================================
# HTML
# ============================================================

HTML = """

<!DOCTYPE html>

<html>

<head>

    <title>Money Detective</title>

    <meta name="viewport"
          content="width=device-width, initial-scale=1.0">

    <style>

        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            font-family: Arial, sans-serif;
            background: #f5f7fb;
            color: #222;
        }

        .container {
            max-width: 1000px;
            margin: auto;
            padding: 30px 20px;
        }

        .header {
            text-align: center;
            margin-bottom: 30px;
        }

        .header h1 {
            font-size: 38px;
            margin-bottom: 8px;
        }

        .header p {
            color: #666;
            font-size: 16px;
        }

        .cards {
            display: grid;
            grid-template-columns:
                repeat(3, 1fr);
            gap: 15px;
            margin-bottom: 25px;
        }

        .card {
            background: white;
            padding: 22px;
            border-radius: 14px;
            box-shadow:
                0 4px 15px rgba(0,0,0,0.06);
        }

        .card h3 {
            margin: 0 0 8px 0;
            color: #666;
            font-size: 14px;
        }

        .card .value {
            font-size: 27px;
            font-weight: bold;
        }

        .section {
            background: white;
            padding: 25px;
            border-radius: 15px;
            margin-bottom: 20px;

            box-shadow:
                0 4px 15px rgba(0,0,0,0.05);
        }

        .section h2 {
            margin-top: 0;
        }

        form {
            margin: 0;
        }

        .form-grid {
            display: grid;
            grid-template-columns:
                1fr 2fr auto;
            gap: 12px;
        }

        input {
            padding: 13px;
            border: 1px solid #ddd;
            border-radius: 8px;
            font-size: 15px;
        }

        button {
            padding: 13px 18px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 15px;
            font-weight: bold;
        }

        .add-btn {
            background: #222;
            color: white;
        }

        .analyze-btn {
            background: #222;
            color: white;
            width: 100%;
            margin-top: 10px;
        }

        .clear-btn {
            background: #eee;
            color: #222;
            margin-top: 10px;
        }

        .category-list {
            display: grid;
            grid-template-columns:
                repeat(auto-fit, minmax(150px, 1fr));

            gap: 10px;
        }

        .category {
            background: #f7f7f7;
            padding: 15px;
            border-radius: 10px;
        }

        .category-name {
            font-size: 14px;
            color: #666;
        }

        .category-value {
            font-size: 20px;
            font-weight: bold;
            margin-top: 5px;
        }

        .expense {
            display: flex;
            justify-content: space-between;
            align-items: center;

            padding: 14px 0;

            border-bottom: 1px solid #eee;
        }

        .expense:last-child {
            border-bottom: none;
        }

        .expense-description {
            font-weight: bold;
        }

        .expense-meta {
            color: #777;
            font-size: 13px;
            margin-top: 4px;
        }

        .expense-amount {
            font-weight: bold;
            font-size: 17px;
        }

        .analysis {
            background: #f7f8ff;
            border-left: 5px solid #222;
            padding: 20px;
            border-radius: 10px;
            line-height: 1.6;
        }

        .empty {
            text-align: center;
            color: #777;
            padding: 20px;
        }

        @media(max-width: 700px) {

            .cards {
                grid-template-columns: 1fr;
            }

            .form-grid {
                grid-template-columns: 1fr;
            }

            .header h1 {
                font-size: 30px;
            }

        }

    </style>

</head>


<body>

<div class="container">


    <!-- HEADER -->

    <div class="header">

        <h1>💸 Money Detective</h1>

        <p>
            Find where your money goes,
            discover money leaks,
            and find ways to save.
        </p>

    </div>


    <!-- SUMMARY -->

    <div class="cards">

        <div class="card">

            <h3>💰 Spent Today</h3>

            <div class="value">
                ₹{{ "%.2f"|format(today_total) }}
            </div>

        </div>


        <div class="card">

            <h3>📅 Spent This Month</h3>

            <div class="value">
                ₹{{ "%.2f"|format(month_total) }}
            </div>

        </div>


        <div class="card">

            <h3>🧾 Transactions</h3>

            <div class="value">
                {{ expenses|length }}
            </div>

        </div>

    </div>


    <!-- ADD EXPENSE -->

    <div class="section">

        <h2>➕ Add Expense</h2>

        <form method="POST"
              action="/add">

            <div class="form-grid">

                <input
                    type="number"
                    name="amount"
                    step="0.01"
                    placeholder="Amount ₹"
                    required
                >

                <input
                    type="text"
                    name="description"
                    placeholder="What did you spend on?"
                    required
                >

                <button
                    type="submit"
                    class="add-btn">

                    Add Expense

                </button>

            </div>

        </form>

    </div>


    <!-- CATEGORY BREAKDOWN -->

    <div class="section">

        <h2>📊 Spending Breakdown</h2>

        {% if categories %}

            <div class="category-list">

                {% for category in categories %}

                    <div class="category">

                        <div class="category-name">
                            {{ category["category"] }}
                        </div>

                        <div class="category-value">
                            ₹{{ "%.2f"|format(category["total"]) }}
                        </div>

                    </div>

                {% endfor %}

            </div>

        {% else %}

            <div class="empty">
                Add some expenses to see your spending breakdown.
            </div>

        {% endif %}

    </div>


    <!-- AI ANALYSIS -->

    <div class="section">

        <h2>🕵️ Money Detective Analysis</h2>

        <p>
            Let AI analyze your actual spending
            and find patterns you may not have noticed.
        </p>

        <form method="POST"
              action="/analyze">

            <button
                type="submit"
                class="analyze-btn">

                🔎 Analyze My Spending

            </button>

        </form>

        {% if ai_result %}

            <br>

            <div class="analysis">

                {{ ai_result|safe }}

            </div>

        {% endif %}

    </div>


    <!-- EXPENSE HISTORY -->

    <div class="section">

        <h2>🧾 This Month's Expenses</h2>

        {% if expenses %}

            {% for expense in expenses %}

                <div class="expense">

                    <div>

                        <div class="expense-description">
                            {{ expense["description"] }}
                        </div>

                        <div class="expense-meta">

                            {{ expense["category"] }}
                            •
                            {{ expense["expense_date"] }}

                        </div>

                    </div>

                    <div class="expense-amount">

                        ₹{{ "%.2f"|format(expense["amount"]) }}

                    </div>

                </div>

            {% endfor %}

        {% else %}

            <div class="empty">

                No expenses added yet.

            </div>

        {% endif %}

    </div>


    <!-- CLEAR -->

    <div class="section">

        <h2>🗑️ Reset Data</h2>

        <p>
            This will permanently delete all
            saved expenses.
        </p>

        <form method="POST"
              action="/clear"
              onsubmit="return confirm('Delete all expenses?');">

            <button
                type="submit"
                class="clear-btn">

                Clear All Expenses

            </button>

        </form>

    </div>


</div>

</body>

</html>

"""


# ============================================================
# HOME PAGE
# ============================================================

@app.route("/", methods=["GET"])
def home():

    expenses = get_month_expenses()

    today_total, month_total = calculate_totals()

    categories = get_category_totals()

    return render_template_string(
        HTML,
        expenses=expenses,
        today_total=today_total,
        month_total=month_total,
        categories=categories,
        ai_result=None
    )


# ============================================================
# ADD EXPENSE
# ============================================================

@app.route("/add", methods=["POST"])
def add_expense():

    amount = request.form.get("amount")

    description = request.form.get(
        "description",
        ""
    ).strip()

    if amount and description:

        try:

            amount = float(amount)

            if amount > 0:

                category = detect_category(
                    description
                )

                date = datetime.now().strftime(
                    "%Y-%m-%d"
                )

                conn = get_db()

                conn.execute("""
                    INSERT INTO expenses
                    (
                        amount,
                        description,
                        category,
                        expense_date
                    )
                    VALUES (?, ?, ?, ?)
                """, (
                    amount,
                    description,
                    category,
                    date
                ))

                conn.commit()
                conn.close()

        except ValueError:

            pass

    return redirect("/")


# ============================================================
# ANALYZE EXPENSES
# ============================================================

@app.route("/analyze", methods=["POST"])
def analyze():

    expenses = get_month_expenses()

    today_total, month_total = calculate_totals()

    categories = get_category_totals()

    raw_result = analyze_spending(
        expenses
    )

    ai_result = markdown.markdown(
        raw_result,
        extensions=[
            "extra",
            "sane_lists"
        ]
    )

    return render_template_string(
        HTML,
        expenses=expenses,
        today_total=today_total,
        month_total=month_total,
        categories=categories,
        ai_result=ai_result
    )


# ============================================================
# CLEAR ALL EXPENSES
# ============================================================

@app.route("/clear", methods=["POST"])
def clear():

    conn = get_db()

    conn.execute(
        "DELETE FROM expenses"
    )

    conn.commit()
    conn.close()

    return redirect("/")


# ============================================================
# RUN APP
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )