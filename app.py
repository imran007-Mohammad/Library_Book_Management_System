import os
import re
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request

from datetime import date, datetime, timedelta
from functools import wraps

import mysql.connector
from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
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
    try:
        cur.execute(sql, args)
        rows = cur.fetchall()
        return (rows[0] if rows else None) if one else rows
    finally:
        cur.close()


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


# ============================================================
# AUTHENTICATION AND ROLE PROTECTION
# ============================================================

def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.")
            return redirect(url_for("home"))
        return view(*args, **kwargs)
    return wrapper


def librarian_required(view):
    @wraps(view)
    @login_required
    def wrapper(*args, **kwargs):
        if session.get("role") != "librarian":
            flash("Only librarians can access this page.")
            if session.get("role") == "student":
                return redirect(url_for("books"))
            return redirect(url_for("home"))
        return view(*args, **kwargs)
    return wrapper


def student_required(view):
    @wraps(view)
    @login_required
    def wrapper(*args, **kwargs):
        if session.get("role") != "student":
            flash("This page is available to students only.")
            if session.get("role") == "librarian":
                return redirect(url_for("dashboard"))
            return redirect(url_for("home"))
        return view(*args, **kwargs)
    return wrapper


def get_selected_role():
    """Read the account type selected on the homepage or submitted by a form."""
    role = (
        request.form.get("role")
        or request.args.get("role")
        or ""
    ).strip().lower()
    return role if role in ("student", "librarian") else None


# ============================================================
# HOME
# ============================================================

@app.route("/")
@app.route("/index.html")
def home():
    return render_template("index.html")


# ============================================================
# STUDENT AND LIBRARIAN REGISTRATION
# ============================================================

@app.route("/register", methods=["GET", "POST"])
@app.route("/register.html", methods=["GET", "POST"])
def register():
    role = get_selected_role()

    if role is None:
        flash("Please choose Student or Librarian.")
        return redirect(url_for("home"))

    if request.method == "GET":
        return render_template("register.html", selected_role=role)

    form = request.form
    name = form.get("name", "").strip()
    roll_no = form.get("student_id", "").strip()
    email = form.get("email", "").strip().lower()
    department = form.get("dept", "").strip()
    password = form.get("password", "")
    confirm_password = form.get("confirm_password", "")
    phone = form.get("phone", "").strip()

    if role == "student":
        roll_no = roll_no.lower()
    else:
        roll_no = roll_no.upper()

    if not all([name, roll_no, email, password, confirm_password]):
        flash("Please complete all required fields.")
        return render_template("register.html", selected_role=role)

    if not email.endswith("@mbu.asia"):
        flash("Use your college email ending in @mbu.asia.")
        return render_template("register.html", selected_role=role)

    if role == "student":
        if not re.fullmatch(r"\d{5}[a-z]\d{6}", roll_no):
            flash("Enter a valid student roll number, such as 25102a010074.")
            return render_template("register.html", selected_role=role)

        if email != f"{roll_no}@mbu.asia":
            flash("Your email must match your roll number followed by @mbu.asia.")
            return render_template("register.html", selected_role=role)

        if not department:
            flash("Please select your branch.")
            return render_template("register.html", selected_role=role)

    else:
        # Librarians use an ID in the format MBU123456.
        # No additional registration code is required.
        if not re.fullmatch(r"MBU\d{6}", roll_no):
            flash("Enter a librarian ID such as MBU123456.")
            return render_template("register.html", selected_role=role)
        department = ""

    if len(password) < 8:
        flash("Password must contain at least 8 characters.")
        return render_template("register.html", selected_role=role)

    if password != confirm_password:
        flash("Passwords do not match.")
        return render_template("register.html", selected_role=role)

    db = get_db()
    cur = db.cursor()

    try:
        cur.execute(
            """
            SELECT user_id
            FROM users
            WHERE LOWER(roll_no) = LOWER(%s)
               OR LOWER(email) = LOWER(%s)
            """,
            (roll_no, email),
        )

        if cur.fetchone():
            db.rollback()
            flash("An account already exists with this ID or email.")
            return render_template("register.html", selected_role=role)

        if role == "student":
            cur.execute(
                """
                SELECT borrower_id
                FROM borrowers
                WHERE LOWER(roll_no) = LOWER(%s)
                """,
                (roll_no,),
            )

            if cur.fetchone():
                db.rollback()
                flash("A student record already exists for this roll number.")
                return render_template("register.html", selected_role=role)

        cur.execute(
            """
            INSERT INTO users (
                full_name, roll_no, email, password_hash, role
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                name,
                roll_no,
                email,
                generate_password_hash(password),
                role,
            ),
        )

        user_id = cur.lastrowid

        # Only students need borrower records for issuing and My Borrows.
        if role == "student":
            cur.execute(
                """
                INSERT INTO borrowers (
                    user_id, borrower_name, roll_no,
                    department, email, phone
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    name,
                    roll_no,
                    department,
                    email,
                    phone or None,
                ),
            )

        db.commit()
        flash("Registration successful! You can now log in.")
        return redirect(url_for("login", role=role))

    except mysql.connector.Error:
        db.rollback()
        app.logger.exception("Registration failed.")
        flash("Registration failed because of a database error.")
        return render_template("register.html", selected_role=role)

    finally:
        cur.close()


# ============================================================
# STUDENT AND LIBRARIAN LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
@app.route("/login.html", methods=["GET", "POST"])
def login():
    role = get_selected_role()

    if role is None:
        flash("Please choose Student or Librarian.")
        return redirect(url_for("home"))

    if request.method == "POST":
        login_id = request.form.get("student_id", "").strip()
        password = request.form.get("password", "")

        if role == "student":
            login_id = login_id.lower()
            if not re.fullmatch(r"\d{5}[a-z]\d{6}", login_id):
                flash("Enter a valid student roll number.")
                return render_template("login.html", selected_role=role)
        else:
            login_id = login_id.upper()
            if not re.fullmatch(r"MBU\d{6}", login_id):
                flash("Enter a librarian ID such as MBU123456.")
                return render_template("login.html", selected_role=role)

        user = query(
            """
            SELECT user_id, full_name, roll_no, email, password_hash, role
            FROM users
            WHERE LOWER(roll_no) = LOWER(%s)
              AND role = %s
            """,
            (login_id, role),
            one=True,
        )

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session.update(
                user_id=user["user_id"],
                full_name=user["full_name"],
                roll_no=user["roll_no"],
                email=user["email"],
                role=user["role"],
            )

            if role == "librarian":
                return redirect(url_for("dashboard"))
            return redirect(url_for("student_dashboard"))

        flash("Incorrect ID or password.")

    return render_template("login.html", selected_role=role)


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("home"))


# ============================================================
# LIBRARIAN DASHBOARD
# ============================================================

@app.route("/dashboard")
@app.route("/dashboard.html")
@librarian_required
def dashboard():
    stats = query(
        """
        SELECT
            (SELECT COUNT(*) FROM books) AS titles,
            (SELECT COALESCE(SUM(total_copies), 0) FROM books) AS total_books,
            (SELECT COUNT(*) FROM loans WHERE return_date IS NULL) AS borrowed,
            (SELECT COUNT(*) FROM loans
             WHERE return_date IS NULL AND due_date < CURDATE()) AS overdue,
            (SELECT COUNT(*) FROM borrowers) AS members
        """,
        one=True,
    )

    recent = query(
        """
        SELECT
            b.borrower_name, b.roll_no, bk.title,
            l.issue_date, l.due_date, l.return_date,
            CASE
                WHEN l.return_date IS NOT NULL THEN 'Returned'
                WHEN l.due_date < CURDATE() THEN 'Overdue'
                ELSE 'Issued'
            END AS status
        FROM loans l
        JOIN borrowers b ON b.borrower_id = l.borrower_id
        JOIN books bk ON bk.book_id = l.book_id
        ORDER BY l.loan_id DESC
        LIMIT 10
        """
    )
    return render_template("dashboard.html", stats=stats, recent=recent)


# ============================================================
# STUDENT DASHBOARD: MY BORROWS
# ============================================================

@app.route("/student_dashboard")
@app.route("/student_dashboard.html")
@app.route("/my-borrows")
@student_required
def student_dashboard():
    borrower = query(
        """
        SELECT borrower_id, borrower_name, roll_no, department, email
        FROM borrowers
        WHERE user_id = %s
        """,
        (session["user_id"],),
        one=True,
    )

    if not borrower:
        flash("Your student profile could not be found.")
        session.clear()
        return redirect(url_for("home"))

    loans = query(
        """
        SELECT
            l.loan_id, bk.title, bk.author, bk.isbn, bk.category,
            bk.floor, bk.rack_number, bk.series_code,
            l.issue_date, l.due_date, l.return_date,
            CASE
                WHEN l.return_date IS NOT NULL THEN 'Returned'
                WHEN l.due_date < CURDATE() THEN 'Overdue'
                ELSE 'Borrowed'
            END AS status,
            CASE
                WHEN l.return_date IS NULL AND l.due_date < CURDATE()
                THEN DATEDIFF(CURDATE(), l.due_date)
                ELSE 0
            END AS days_overdue
        FROM loans l
        JOIN books bk ON bk.book_id = l.book_id
        WHERE l.borrower_id = %s
        ORDER BY
            CASE WHEN l.return_date IS NULL THEN 0 ELSE 1 END,
            l.issue_date DESC
        """,
        (borrower["borrower_id"],),
    )

    stats = query(
        """
        SELECT
            COUNT(*) AS total_borrowings,
            COALESCE(
                SUM(CASE WHEN return_date IS NULL THEN 1 ELSE 0 END), 0
            ) AS currently_borrowed,
            COALESCE(
                SUM(
                    CASE
                        WHEN return_date IS NULL AND due_date < CURDATE()
                        THEN 1 ELSE 0
                    END
                ), 0
            ) AS overdue
        FROM loans
        WHERE borrower_id = %s
        """,
        (borrower["borrower_id"],),
        one=True,
    )

    return render_template(
        "student_dashboard.html",
        student=borrower,
        loans=loans,
        stats=stats,
    )


# ============================================================
# BOOK CATALOGUE AND SEARCH
# ============================================================

# ============================================================
# BOOK CATALOGUE AND SEARCH
# ============================================================

@app.route("/books")
@app.route("/books.html")
@login_required
def books():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()

    sql = """
        SELECT
            bk.*,
            COALESCE(rv.average_rating, 0) AS average_rating,
            COALESCE(rv.review_count, 0) AS review_count
        FROM books AS bk
        LEFT JOIN (
            SELECT
                book_id,
                AVG(rating) AS average_rating,
                COUNT(*) AS review_count
            FROM reviews
            GROUP BY book_id
        ) AS rv ON rv.book_id = bk.book_id
        WHERE 1 = 1
    """

    args = []

    # Search by book details and location.
    if q:
        sql += """
            AND (
                bk.title LIKE %s
                OR bk.author LIKE %s
                OR bk.isbn LIKE %s
                OR bk.category LIKE %s
                OR bk.floor LIKE %s
                OR bk.rack_number LIKE %s
                OR bk.series_code LIKE %s
            )
        """

        search_term = f"%{q}%"
        args.extend([search_term] * 7)

    # Filter by selected category.
    if category:
        sql += " AND bk.category = %s"
        args.append(category)

    sql += " ORDER BY bk.title"

    rows = query(sql, args)

    categories = [
        row["category"]
        for row in query(
            "SELECT DISTINCT category FROM books ORDER BY category"
        )
    ]

    return render_template(
        "books.html",
        books=rows,
        categories=categories,
        q=q,
        category=category,
    )

# ============================================================
# ADD BOOK
# ============================================================

@app.route("/add_book", methods=["GET", "POST"])
@app.route("/add_book.html", methods=["GET", "POST"])
@librarian_required
def add_book():
    if request.method == "POST":
        form = request.form
        isbn = form.get("isbn", "").strip()
        title = form.get("title", "").strip()
        author = form.get("author", "").strip()
        category = form.get("category", "").strip() or "General"
        floor = form.get("floor", "").strip() or None
        rack_number = form.get("rack_number", "").strip() or None
        series_code = form.get("series_code", "").strip() or None

        try:
            copies = int(form.get("copies", "1"))
            if copies < 1:
                raise ValueError
        except ValueError:
            flash("Copies must be a whole number greater than zero.")
            return render_template("add_book.html")

        if not all([isbn, title, author]):
            flash("ISBN, title and author are required.")
            return render_template("add_book.html")

        try:
            execute(
                """
                INSERT INTO books (
                    isbn, title, author, category,
                    total_copies, copies_available,
                    floor, rack_number, series_code
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    isbn, title, author, category,
                    copies, copies, floor, rack_number, series_code,
                ),
            )
            flash("Book added successfully.")
            return redirect(url_for("books"))
        except mysql.connector.IntegrityError:
            flash("A book with that ISBN already exists.")
        except mysql.connector.Error:
            app.logger.exception("Adding a book failed.")
            flash("Could not add the book because of a database error.")

    return render_template("add_book.html")


# ============================================================
# MEMBERS
# ============================================================

@app.route("/members")
@app.route("/members.html")
@librarian_required
def members():
    rows = query(
        """
        SELECT
            b.roll_no, b.borrower_name, b.department, b.email,
            COUNT(CASE WHEN l.return_date IS NULL THEN 1 END) AS books_held,
            COALESCE(
                SUM(
                    CASE
                        WHEN l.return_date IS NULL
                        THEN GREATEST(DATEDIFF(CURDATE(), l.due_date), 0)
                        ELSE 0
                    END
                ), 0
            ) * %s AS fine_due
        FROM borrowers b
        LEFT JOIN loans l ON l.borrower_id = b.borrower_id
        GROUP BY
            b.borrower_id, b.roll_no, b.borrower_name,
            b.department, b.email
        ORDER BY b.borrower_name
        """,
        (FINE_PER_DAY,),
    )
    return render_template("members.html", members=rows)


@app.route("/issue_return")
@app.route("/issue_return.html")
@librarian_required
def issue_return():
    return render_template("issue_return.html")


@app.post("/issue")
@librarian_required
def issue():
    roll_no = request.form.get("student_id", "").strip().lower()
    isbn = request.form.get("isbn", "").strip()

    try:
        due = (
            date.fromisoformat(request.form.get("due", ""))
            if request.form.get("due")
            else date.today() + timedelta(days=LOAN_DAYS)
        )
    except ValueError:
        flash("Enter a valid due date.")
        return redirect(url_for("issue_return"))

    borrower = query(
        """
        SELECT borrower_id, borrower_name
        FROM borrowers
        WHERE LOWER(roll_no) = %s
        """,
        (roll_no,),
        one=True,
    )
    book = query(
        "SELECT book_id, title FROM books WHERE isbn = %s",
        (isbn,),
        one=True,
    )

    if not borrower or not book:
        flash("Student roll number or ISBN was not found.")
    elif due < date.today():
        flash("Due date cannot be in the past.")
    elif query(
        """
        SELECT 1 FROM loans
        WHERE borrower_id = %s AND book_id = %s AND return_date IS NULL
        """,
        (borrower["borrower_id"], book["book_id"]),
        one=True,
    ):
        flash("This student already has this book.")
    elif query(
        """
        SELECT COUNT(*) AS n FROM loans
        WHERE borrower_id = %s AND return_date IS NULL
        """,
        (borrower["borrower_id"],),
        one=True,
    )["n"] >= MAX_LOANS:
        flash(f"A student can hold at most {MAX_LOANS} books at a time.")
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
                cur.execute(
                    """
                    INSERT INTO loans (book_id, borrower_id, issue_date, due_date)
                    VALUES (%s, %s, CURDATE(), %s)
                    """,
                    (book["book_id"], borrower["borrower_id"], due),
                )
                db.commit()
                flash(
                    f"Issued '{book['title']}' to {borrower['borrower_name']}. "
                    f"Due {due:%d %b %Y}."
                )
        except mysql.connector.Error:
            db.rollback()
            app.logger.exception("Book issue failed.")
            flash("Could not issue the book. Nothing was changed.")
        finally:
            cur.close()

    return redirect(url_for("issue_return"))


@app.post("/return")
@librarian_required
def return_book():
    roll_no = request.form.get("student_id", "").strip().lower()
    isbn = request.form.get("isbn", "").strip()

    try:
        returned = (
            date.fromisoformat(request.form.get("returned", ""))
            if request.form.get("returned")
            else date.today()
        )
    except ValueError:
        flash("Enter a valid return date.")
        return redirect(url_for("issue_return"))

    loan = query(
        """
        SELECT l.loan_id, l.book_id, l.issue_date, l.due_date, bk.title
        FROM loans l
        JOIN borrowers b ON b.borrower_id = l.borrower_id
        JOIN books bk ON bk.book_id = l.book_id
        WHERE LOWER(b.roll_no) = %s
          AND bk.isbn = %s
          AND l.return_date IS NULL
        ORDER BY l.loan_id DESC
        LIMIT 1
        """,
        (roll_no, isbn),
        one=True,
    )

    if not loan:
        flash("No active loan was found for that student and book.")
    elif returned < loan["issue_date"]:
        flash("Return date cannot be before the issue date.")
    else:
        db = get_db()
        cur = db.cursor()
        try:
            cur.execute(
                """
                UPDATE loans
                SET return_date = %s
                WHERE loan_id = %s AND return_date IS NULL
                """,
                (returned, loan["loan_id"]),
            )

            if cur.rowcount == 1:
                cur.execute(
                    """
                    UPDATE books
                    SET copies_available = LEAST(copies_available + 1, total_copies)
                    WHERE book_id = %s
                    """,
                    (loan["book_id"],),
                )
                db.commit()
                fine = max((returned - loan["due_date"]).days, 0) * FINE_PER_DAY
                message = f"Returned '{loan['title']}'."
                if fine:
                    message += f" Fine due: ₹{fine}."
                flash(message)
            else:
                db.rollback()
                flash("The loan has already been returned.")
        except mysql.connector.Error:
            db.rollback()
            app.logger.exception("Book return failed.")
            flash("Could not return the book. Nothing was changed.")
        finally:
            cur.close()

    return redirect(url_for("issue_return"))


@app.route("/api/analytics")
@librarian_required
def analytics():
    return jsonify(
        most_borrowed=query(
            """
            SELECT bk.title, COUNT(*) AS times_borrowed
            FROM loans l
            JOIN books bk ON bk.book_id = l.book_id
            GROUP BY bk.book_id, bk.title
            ORDER BY times_borrowed DESC
            LIMIT 10
            """
        ),
        monthly_trend=query(
            """
            SELECT DATE_FORMAT(issue_date, '%Y-%m') AS month,
                   COUNT(*) AS loans
            FROM loans
            GROUP BY month
            ORDER BY month
            """
        ),
        category_summary=query(
            """
            SELECT bk.category, COUNT(*) AS loans
            FROM loans l
            JOIN books bk ON bk.book_id = l.book_id
            GROUP BY bk.category
            ORDER BY loans DESC
            """
        ),
        overdue=query(
            """
            SELECT b.borrower_name, b.roll_no, bk.title, l.due_date,
                   DATEDIFF(CURDATE(), l.due_date) AS days_late
            FROM loans l
            JOIN borrowers b ON b.borrower_id = l.borrower_id
            JOIN books bk ON bk.book_id = l.book_id
            WHERE l.return_date IS NULL AND l.due_date < CURDATE()
            ORDER BY days_late DESC
            """
        ),
    )


# ============================================================
# START APPLICATION
# ============================================================

if __name__ == "__main__":
    app.run(debug=True)   
