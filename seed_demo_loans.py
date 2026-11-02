import os
import random
import sys
from datetime import date, timedelta

import mysql.connector
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()
random.seed(11)

PREFIX = "99999d"
LOAN_DAYS = int(os.getenv("LOAN_DAYS", 30))
MAX_LOANS = int(os.getenv("MAX_LOANS", 3))
TOTAL_LOANS = 350

DEPARTMENTS = ["CSE", "AIML", "ECE", "EEE", "MECH", "CIVIL"]

# How popular each category is (categories not listed get weight 1)
CATEGORY_WEIGHT = {
    "Programming": 6, "Engineering": 4, "Mathematics": 3, "Physics": 2,
    "Business": 2, "Chemistry": 1.5, "Biology": 1, "Literature": 1,
    "History": 0.7, "Self-Help": 1.2,
}

NAMES = [
    "Aarav Reddy", "Bhavya Sri", "Charan Teja", "Divya Rani", "Eshwar Rao",
    "Farhan Ali", "Gayathri Devi", "Harsha Vardhan", "Ishita Jain", "Jaswanth Kumar",
    "Keerthi Priya", "Lokesh Babu", "Meghana Rao", "Naveen Kumar", "Pranavi Sai",
    "Rahul Naidu", "Sandhya Rani", "Tarun Sai", "Uday Kiran", "Varshini Reddy",
    "Wasim Akram", "Yashwanth Raju", "Zoya Khan", "Akhil Varma", "Bindu Madhavi",
    "Chaitanya Sri", "Deepak Chowdary", "Elina Joseph", "Gopi Krishna", "Hema Latha",
]


def connect():
    """Same connection settings as get_db() in app.py."""
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.getenv("DB_NAME", "library_db"),
    )


def clear(db):
    cur = db.cursor()
    like = PREFIX + "%"

    # Give back the copies that demo students are still holding
    cur.execute(
        """
        UPDATE books bk
        JOIN (
            SELECT l.book_id, COUNT(*) AS n
            FROM loans l
            JOIN borrowers b ON b.borrower_id = l.borrower_id
            WHERE b.roll_no LIKE %s AND l.return_date IS NULL
            GROUP BY l.book_id
        ) x ON x.book_id = bk.book_id
        SET bk.copies_available = LEAST(bk.copies_available + x.n, bk.total_copies)
        """,
        (like,),
    )
    cur.execute(
        """
        DELETE l FROM loans l
        JOIN borrowers b ON b.borrower_id = l.borrower_id
        WHERE b.roll_no LIKE %s
        """,
        (like,),
    )
    # Deleting the users also deletes their borrower rows (ON DELETE CASCADE)
    cur.execute("DELETE FROM users WHERE roll_no LIKE %s", (like,))
    db.commit()
    print("Demo data removed.")


def seed(db):
    cur = db.cursor()
    today = date.today()

    cur.execute("SELECT COUNT(*) FROM users WHERE roll_no LIKE %s", (PREFIX + "%",))
    if cur.fetchone()[0]:
        print("Demo data already exists. Run with --clear first.")
        return

    cur.execute("SELECT book_id, category, copies_available FROM books")
    book_rows = cur.fetchall()
    if not book_rows:
        print("No books found. Load schema.sql first.")
        return
    book_ids = [row[0] for row in book_rows]
    start_available = {row[0]: row[2] for row in book_rows}
    available = dict(start_available)

    # A book's popularity = its category weight x a random "hotness".
    # About 1 book in 12 is "hot" and gets borrowed far more often.
    weights = []
    for _, category, _ in book_rows:
        hotness = 12 if random.random() < 1 / 12 else random.choice([0.3, 0.6, 1, 1, 1.5])
        weights.append(CATEGORY_WEIGHT.get(category, 1) * hotness)

    # --- demo students: a users row, then a borrowers row linked by user_id ---
    password_hash = generate_password_hash("DemoPass123")
    borrower_ids = []
    for i, name in enumerate(NAMES, start=1):
        roll = f"{PREFIX}{i:06d}"
        email = f"{roll}@mbu.asia"
        cur.execute(
            """
            INSERT INTO users (full_name, roll_no, email, password_hash, role)
            VALUES (%s, %s, %s, %s, 'student')
            """,
            (name, roll, email, password_hash),
        )
        user_id = cur.lastrowid
        cur.execute(
            """
            INSERT INTO borrowers (user_id, borrower_name, roll_no, department, email)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_id, name, roll, DEPARTMENTS[i % len(DEPARTMENTS)], email),
        )
        borrower_ids.append(cur.lastrowid)

    # Some students borrow much more than others
    student_weights = [random.choice([1, 1, 2, 3, 6]) for _ in borrower_ids]

    holding = {b: set() for b in borrower_ids}  # books each student has right now
    added = 0

    for _ in range(TOTAL_LOANS):
        book_id = random.choices(book_ids, weights=weights)[0]
        borrower_id = random.choices(borrower_ids, weights=student_weights)[0]

        if random.random() < 0.82:
            # Returned loan. Issue dates lean towards recent months.
            days_ago = int(random.triangular(3, 180, 15))
            issue = today - timedelta(days=days_ago)
            if random.random() < 0.25:
                kept = random.randint(LOAN_DAYS + 1, LOAN_DAYS + 20)  # returned late
            else:
                kept = random.randint(5, LOAN_DAYS)
            return_date = min(issue + timedelta(days=kept), today)
        else:
            # Book still with the student (same rules as /issue in app.py)
            if (len(holding[borrower_id]) >= MAX_LOANS
                    or book_id in holding[borrower_id]
                    or available[book_id] <= 0):
                continue
            issue = today - timedelta(days=random.randint(1, 75))
            return_date = None
            holding[borrower_id].add(book_id)
            available[book_id] -= 1

        cur.execute(
            """
            INSERT INTO loans (book_id, borrower_id, issue_date, due_date, return_date)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (book_id, borrower_id, issue, issue + timedelta(days=LOAN_DAYS), return_date),
        )
        added += 1

    # Keep copies_available correct for the books that are now out
    for book_id, left in available.items():
        if left != start_available[book_id]:
            cur.execute(
                "UPDATE books SET copies_available = %s WHERE book_id = %s",
                (left, book_id),
            )

    db.commit()
    print(f"Added {len(NAMES)} demo students and {added} loans.")


if __name__ == "__main__":
    connection = connect()
    try:
        if "--clear" in sys.argv:
            clear(connection)
        else:
            seed(connection)
    finally:
        connection.close()
