import os
from datetime import date, timedelta
from functools import wraps

import mysql.connector
from dotenv import load_dotenv
from flask import (Flask, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]

LOAN_DAYS = int(os.getenv("LOAN_DAYS", 30))       
FINE_PER_DAY = int(os.getenv("FINE_PER_DAY", 30))  
MAX_LOANS = int(os.getenv("MAX_LOANS", 3))        


def get_db():
    if "db" not in g:
        g.db = mysql.connector.connect(
            host=os.getenv("DB_HOST", "localhost"),
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            database=os.getenv("DB_NAME", "library_db"),
        )
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, args=None, one=False):
    cur = get_db().cursor(dictionary=True)
    cur.execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=None):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(sql, args)
        db.commit()
        return cur.lastrowid
    except mysql.connector.Error:
        db.rollback()
        raise
    finally:
        cur.close()


def login_required(view):
    @wraps(view)
    def wrapper(*a, **kw):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*a, **kw)
    return wrapper


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapper(*a, **kw):
        if session.get("role") != "admin":
            flash("Only librarians can open that page.")
            return redirect(url_for("books"))
        return view(*a, **kw)
    return wrapper


@app.route("/")
@app.route("/index.html")
def home():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
@app.route("/register.html", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form
        roll_no, name, pw = f["student_id"].strip(), f["name"].strip(), f["password"]
        if len(pw) < 8:
            flash("Password must be at least 8 characters.")
        elif query("SELECT 1 FROM users WHERE roll_no=%s", (roll_no,), one=True):
            flash("That student ID already has an account.")
        else:
            if not query("SELECT 1 FROM borrowers WHERE roll_no=%s", (roll_no,), one=True):
                execute("INSERT INTO borrowers (borrower_name, roll_no, department, email, phone) "
                        "VALUES (%s,%s,%s,%s,%s)",
                        (name, roll_no, f.get("dept"), f.get("email"), f.get("phone")))
            first = query("SELECT COUNT(*) AS n FROM users", one=True)["n"] == 0
            execute("INSERT INTO users (roll_no, password_hash, role) VALUES (%s,%s,%s)",
                    (roll_no, generate_password_hash(pw), "admin" if first else "member"))
            flash("Account created. Please log in.")
            return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
@app.route("/login.html", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = query("SELECT * FROM users WHERE roll_no=%s",
                     (request.form["student_id"].strip(),), one=True)
        if user and check_password_hash(user["password_hash"], request.form["password"]):
            session.clear()
            session.update(user_id=user["user_id"], roll_no=user["roll_no"], role=user["role"])
            return redirect(url_for("dashboard" if user["role"] == "admin" else "books"))
        flash("Wrong student ID or password.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/dashboard")
@app.route("/dashboard.html")
@admin_required
def dashboard():
    stats = query("""
        SELECT (SELECT COUNT(*) FROM books)                                   AS titles,
               (SELECT COALESCE(SUM(total_copies),0) FROM books)              AS total_books,
               (SELECT COUNT(*) FROM loans WHERE return_date IS NULL)         AS borrowed,
               (SELECT COUNT(*) FROM loans
                 WHERE return_date IS NULL AND due_date < CURDATE())          AS overdue,
               (SELECT COUNT(*) FROM borrowers)                               AS members
    """, one=True)
    recent = query("""
        SELECT b.borrower_name, bk.title, l.issue_date, l.due_date, l.return_date,
               CASE WHEN l.return_date IS NOT NULL THEN 'Returned'
                    WHEN l.due_date < CURDATE()    THEN 'Overdue'
                    ELSE 'Issued' END AS status
        FROM loans l
        JOIN borrowers b ON b.borrower_id = l.borrower_id
        JOIN books bk    ON bk.book_id    = l.book_id
        ORDER BY l.loan_id DESC LIMIT 10
    """)
    return render_template("dashboard.html", stats=stats, recent=recent)


@app.route("/books")
@app.route("/books.html")
@login_required
def books():
    q, category = request.args.get("q", "").strip(), request.args.get("category", "")
    sql, args = "SELECT * FROM books WHERE 1=1", []
    if q:
        sql += " AND (title LIKE %s OR author LIKE %s OR isbn LIKE %s)"
        args += [f"%{q}%"] * 3
    if category:
        sql += " AND category = %s"
        args.append(category)
    rows = query(sql + " ORDER BY title", args)
    categories = [r["category"] for r in query("SELECT DISTINCT category FROM books ORDER BY category")]
    return render_template("books.html", books=rows, categories=categories, q=q, category=category)


@app.route("/add_book", methods=["GET", "POST"])
@app.route("/add_book.html", methods=["GET", "POST"])
@admin_required
def add_book():
    if request.method == "POST":
        f = request.form
        try:
            copies = int(f["copies"])
            if copies < 1:
                raise ValueError
            execute("INSERT INTO books (isbn, title, author, category, total_copies, copies_available) "
                    "VALUES (%s,%s,%s,%s,%s,%s)",
                    (f["isbn"].strip(), f["title"].strip(), f["author"].strip(), f["category"], copies, copies))
            flash("Book added.")
            return redirect(url_for("books"))
        except ValueError:
            flash("Copies must be a whole number of 1 or more.")
        except mysql.connector.IntegrityError:
            flash("A book with that ISBN already exists.")
    return render_template("add_book.html")


@app.route("/members")
@app.route("/members.html")
@admin_required
def members():
    rows = query("""
        SELECT b.roll_no, b.borrower_name, b.department,
               COUNT(CASE WHEN l.return_date IS NULL THEN 1 END) AS books_held,
               COALESCE(SUM(CASE WHEN l.return_date IS NULL
                                 THEN GREATEST(DATEDIFF(CURDATE(), l.due_date), 0)
                                 ELSE 0 END), 0) * %s AS fine_due
        FROM borrowers b
        LEFT JOIN loans l ON l.borrower_id = b.borrower_id
        GROUP BY b.borrower_id ORDER BY b.borrower_name
    """, (FINE_PER_DAY,))
    return render_template("members.html", members=rows)


@app.route("/issue_return")
@app.route("/issue_return.html")
@admin_required
def issue_return():
    return render_template("issue_return.html")


@app.post("/issue")
@admin_required
def issue():
    roll_no, isbn = request.form["student_id"].strip(), request.form["isbn"].strip()
    try:
        due = date.fromisoformat(request.form.get("due") or "") if request.form.get("due") \
            else date.today() + timedelta(days=LOAN_DAYS)
    except ValueError:
        flash("Enter a valid due date.")
        return redirect(url_for("issue_return"))

    borrower = query("SELECT borrower_id, borrower_name FROM borrowers WHERE roll_no=%s", (roll_no,), one=True)
    book = query("SELECT book_id, title FROM books WHERE isbn=%s", (isbn,), one=True)
    if not borrower or not book:
        flash("Student ID or ISBN not found.")
    elif due < date.today():
        flash("Due date cannot be in the past.")
    elif query("SELECT 1 FROM loans WHERE borrower_id=%s AND book_id=%s AND return_date IS NULL",
               (borrower["borrower_id"], book["book_id"]), one=True):
        flash("This member already has that book.")
    elif query("SELECT COUNT(*) AS n FROM loans WHERE borrower_id=%s AND return_date IS NULL",
               (borrower["borrower_id"],), one=True)["n"] >= MAX_LOANS:
        flash(f"Limit reached: a member can hold {MAX_LOANS} books at a time.")
    else:
        db = get_db()
        cur = db.cursor()
        try:
            
            cur.execute("UPDATE books SET copies_available = copies_available - 1 "
                        "WHERE book_id=%s AND copies_available > 0", (book["book_id"],))
            if cur.rowcount == 0:
                db.rollback()
                flash(f"No copies of '{book['title']}' are available.")
            else:
                cur.execute("INSERT INTO loans (book_id, borrower_id, issue_date, due_date) "
                            "VALUES (%s,%s,CURDATE(),%s)", (book["book_id"], borrower["borrower_id"], due))
                db.commit()
                flash(f"Issued '{book['title']}' to {borrower['borrower_name']}. Due {due:%d %b %Y}.")
        except mysql.connector.Error:
            db.rollback()
            flash("Database error. Nothing was changed.")
        finally:
            cur.close()
    return redirect(url_for("issue_return"))


@app.post("/return")
@admin_required
def return_book():
    roll_no, isbn = request.form["student_id"].strip(), request.form["isbn"].strip()
    try:
        returned = date.fromisoformat(request.form["returned"]) if request.form.get("returned") else date.today()
    except ValueError:
        flash("Enter a valid return date.")
        return redirect(url_for("issue_return"))

    loan = query("""
        SELECT l.loan_id, l.book_id, l.issue_date, l.due_date, bk.title
        FROM loans l
        JOIN borrowers b ON b.borrower_id = l.borrower_id
        JOIN books bk    ON bk.book_id    = l.book_id
        WHERE b.roll_no=%s AND bk.isbn=%s AND l.return_date IS NULL
    """, (roll_no, isbn), one=True)
    if not loan:
        flash("No active loan found for that student and book. Nothing was changed.")
    elif returned < loan["issue_date"]:
        flash("Return date cannot be before the issue date.")
    else:
        db = get_db()
        cur = db.cursor()
        try:
            cur.execute("UPDATE loans SET return_date=%s WHERE loan_id=%s AND return_date IS NULL",
                        (returned, loan["loan_id"]))
            if cur.rowcount == 1:
                cur.execute("UPDATE books SET copies_available = copies_available + 1 WHERE book_id=%s",
                            (loan["book_id"],))
            db.commit()
            fine = max((returned - loan["due_date"]).days, 0) * FINE_PER_DAY
            flash(f"Returned '{loan['title']}'." + (f" Fine due: ₹{fine}." if fine else ""))
        except mysql.connector.Error:
            db.rollback()
            flash("Database error. Nothing was changed.")
        finally:
            cur.close()
    return redirect(url_for("issue_return"))


@app.route("/api/analytics")
@admin_required
def analytics():
    return jsonify(
        most_borrowed=query("""SELECT bk.title, COUNT(*) AS times_borrowed
                               FROM loans l JOIN books bk ON bk.book_id = l.book_id
                               GROUP BY bk.book_id ORDER BY times_borrowed DESC LIMIT 10"""),
        monthly_trend=query("""SELECT DATE_FORMAT(issue_date, '%Y-%m') AS month, COUNT(*) AS loans
                               FROM loans GROUP BY month ORDER BY month"""),
        category_summary=query("""SELECT bk.category, COUNT(*) AS loans
                                  FROM loans l JOIN books bk ON bk.book_id = l.book_id
                                  GROUP BY bk.category ORDER BY loans DESC"""),
        overdue=query("""SELECT b.borrower_name, bk.title, l.due_date,
                                DATEDIFF(CURDATE(), l.due_date) AS days_late
                         FROM loans l
                         JOIN borrowers b ON b.borrower_id = l.borrower_id
                         JOIN books bk    ON bk.book_id    = l.book_id
                         WHERE l.return_date IS NULL AND l.due_date < CURDATE()
                         ORDER BY days_late DESC"""),
    )


if __name__ == "__main__":
    app.run(debug=True)   
