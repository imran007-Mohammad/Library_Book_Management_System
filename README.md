# Library Book Management System

A web-based Library Book Management System built using Python, Flask, and MySQL. The project helps librarians manage books and borrowing records while allowing students to browse the catalogue and track their borrowed books.

## Features

### Librarian

* Dashboard to view library information.
* Add and manage book records.
* Issue books to students and record returns.
* View registered members and their borrowing information.
* Track overdue books and applicable fines.

### Student

* Register and log in to a student account.
* Browse the available book catalogue.
* View personal borrowing history.
* Check borrowing status and due dates.
* Rate and review books.

## Technology Stack

* **Frontend:** HTML, CSS, JavaScript
* **Backend:** Python, Flask
* **Database:** MySQL
* **Database Connector:** MySQL Connector/Python
* **Environment Configuration:** Python dotenv

## Project Structure

```text
Library_Book_Management_System/
├── app.py
├── schema.sql
├── requirements.txt
├── README.md
├── static/
│   ├── style.css
│   └── library_nav.css
└── templates/
    ├── index.html
    ├── login.html
    ├── register.html
    ├── dashboard.html
    ├── student_dashboard.html
    ├── books.html
    ├── add_book.html
    ├── issue_return.html
    ├── members.html
    └── _navigation.html
```

## Installation and Setup

### 1. Install the Requirements

Install Python and MySQL on your computer. MySQL Workbench can be used to manage the database.

Clone the repository:

```bash
git clone https://github.com/imran007-Mohammad/Library_Book_Management_System.git
```

Open the project folder:

```bash
cd Library_Book_Management_System
```

### 2. Create a Virtual Environment

```bash
python -m venv .venv
```

Activate it in Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 3. Install Python Packages

```bash
pip install -r requirements.txt
```

### 4. Configure the Database

Open MySQL Workbench and execute `schema.sql` for a new database setup.

**Important:** The schema creates an empty database structure. It does not provide sample users or books. Do not rerun the script against an existing database with tables you need to preserve.

### 5. Configure Environment Variables

Create a `.env` file in the project root directory and add your local configuration:

```env
SECRET_KEY=replace_with_a_random_secret_key
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_NAME=library_db
LOAN_DAYS=14
FINE_PER_DAY=2
MAX_LOANS=3
```

Replace the example values with your own settings. Use a secure secret key and your actual MySQL credentials.

**Security:** Never upload your real database password, secret key, or other private credentials to GitHub.

### 6. Start the Application

Run the following command from the project directory:

```bash
flask --app app run --debug
```

Open your browser and visit:

```text
http://127.0.0.1:5000
```

## Database Tables

The database schema includes the following tables:

* `users` — Student and librarian accounts.
* `borrowers` — Student profile information.
* `books` — Book details and available copies.
* `loans` — Book issue and return records.
* `reviews` — Student ratings and book reviews.

## Purpose

This project aims to simplify library operations by organizing book records, student information, and borrowing activities in one web application.

## Contributors

Developed as a collaborative project to practice web development, Python programming, database management, and application design.
