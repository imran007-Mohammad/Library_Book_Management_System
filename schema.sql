-- Run once:  mysql -u root -p < schema.sql
CREATE DATABASE IF NOT EXISTS library_db CHARACTER SET utf8mb4;
USE library_db;

CREATE TABLE IF NOT EXISTS users (
  user_id       INT AUTO_INCREMENT PRIMARY KEY,
  roll_no       VARCHAR(30)  NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role          ENUM('admin','member') NOT NULL DEFAULT 'member'
);

CREATE TABLE IF NOT EXISTS borrowers (
  borrower_id   INT AUTO_INCREMENT PRIMARY KEY,
  borrower_name VARCHAR(100) NOT NULL,
  roll_no       VARCHAR(30)  NOT NULL UNIQUE,
  department    VARCHAR(50),
  email         VARCHAR(120),
  phone         VARCHAR(15)
);

CREATE TABLE IF NOT EXISTS books (
  book_id          INT AUTO_INCREMENT PRIMARY KEY,
  isbn             VARCHAR(20)  NOT NULL UNIQUE,
  title            VARCHAR(200) NOT NULL,
  author           VARCHAR(120) NOT NULL,
  category         VARCHAR(60)  NOT NULL,
  total_copies     INT NOT NULL,
  copies_available INT NOT NULL,
  CHECK (total_copies > 0),
  CHECK (copies_available BETWEEN 0 AND total_copies)
);

CREATE TABLE IF NOT EXISTS loans (
  loan_id     INT AUTO_INCREMENT PRIMARY KEY,
  book_id     INT  NOT NULL,
  borrower_id INT  NOT NULL,
  issue_date  DATE NOT NULL,
  due_date    DATE NOT NULL,
  return_date DATE NULL,
  FOREIGN KEY (book_id)     REFERENCES books(book_id),
  FOREIGN KEY (borrower_id) REFERENCES borrowers(borrower_id),
  CHECK (due_date >= issue_date),
  CHECK (return_date IS NULL OR return_date >= issue_date),
  INDEX idx_active (borrower_id, book_id, return_date)
);

-- Sample data (fake)
INSERT IGNORE INTO books (isbn, title, author, category, total_copies, copies_available) VALUES
('9781593279288','Python Crash Course','Eric Matthes','Computer Science',3,3),
('9780262046305','Introduction to Algorithms','Thomas H. Cormen','Computer Science',2,2),
('9780078022159','Database System Concepts','Abraham Silberschatz','Computer Science',2,2),
('9788174091956','Higher Engineering Mathematics','B. S. Grewal','Mathematics',5,5),
('9788173711466','Wings of Fire','A. P. J. Abdul Kalam','Literature',4,4);

INSERT IGNORE INTO borrowers (borrower_name, roll_no, department) VALUES
('Anita R.','MBU002','CSE'),('Kiran P.','MBU003','ECE');