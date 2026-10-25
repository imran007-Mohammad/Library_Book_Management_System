drop database if exists library_db;
create database library_db;
use library_db;

create table books (
    book_id int auto_increment primary key,
    isbn varchar(20) unique,
    title varchar(150) not null,
    author varchar(100) not null,
    category varchar(50) not null,
    copies_available int not null,
    check (copies_available >= 0)
);

create table borrowers (
    borrower_id int auto_increment primary key,
    borrower_name varchar(100) not null,
    roll_no varchar(30) not null unique
);

create table loans (
    loan_id int auto_increment primary key,
    book_id int not null,
    borrower_id int not null,
    issue_date date not null,
    due_date date not null,
    return_date date,
    foreign key (book_id) references books(book_id),
    foreign key (borrower_id) references borrowers(borrower_id),
    check (due_date >= issue_date),
    check (return_date is null or return_date >= issue_date)
);

insert into books (isbn, title, author, category, copies_available) values
('9780132350884', 'Clean Code', 'Robert C. Martin', 'Programming', 2),
('9780262033848', 'Introduction to Algorithms', 'Thomas H. Cormen', 'Computer Science', 2),
('9781593279288', 'Python Crash Course', 'Eric Matthes', 'Programming', 1),
('9780073523323', 'Database System Concepts', 'Abraham Silberschatz', 'Computer Science', 2),
('9780451524935', '1984', 'George Orwell', 'Fiction', 3),
('9780061120084', 'To Kill a Mockingbird', 'Harper Lee', 'Fiction', 1),
('9780062316097', 'Sapiens', 'Yuval Noah Harari', 'History', 2),
('9788173711466', 'Wings of Fire', 'A.P.J. Abdul Kalam', 'Biography', 2),
('9780553380163', 'A Brief History of Time', 'Stephen Hawking', 'Science', 0),
('9780743273565', 'The Great Gatsby', 'F. Scott Fitzgerald', 'Fiction', 2);

insert into borrowers (borrower_name, roll_no) values
('Aarav Sharma', 'CS2023001'),
('Ananya Reddy', 'CS2023002'),
('Rohan Mehta', 'CS2023003'),
('Priya Nair', 'EC2023004'),
('Karthik Iyer', 'EC2023005'),
('Sneha Patel', 'ME2023006');

insert into loans (book_id, borrower_id, issue_date, due_date, return_date) values
(1, 1, '2026-05-05', '2026-05-19', '2026-05-17'),
(2, 2, '2026-05-12', '2026-05-26', '2026-05-25'),
(5, 3, '2026-05-20', '2026-06-03', '2026-06-01'),
(1, 4, '2026-06-02', '2026-06-16', '2026-06-15'),
(3, 5, '2026-06-10', '2026-06-24', '2026-06-26'),
(5, 6, '2026-06-18', '2026-07-02', '2026-07-01'),
(1, 2, '2026-07-03', '2026-07-17', '2026-07-16'),
(4, 1, '2026-07-08', '2026-07-22', '2026-07-20'),
(7, 3, '2026-07-15', '2026-07-29', '2026-07-28'),
(5, 4, '2026-08-04', '2026-08-18', '2026-08-17'),
(2, 5, '2026-08-10', '2026-08-24', '2026-08-27'),
(10, 6, '2026-08-17', '2026-08-31', '2026-08-30'),
(1, 3, '2026-09-02', '2026-09-16', '2026-09-15'),
(6, 1, '2026-09-08', '2026-09-22', '2026-09-20'),
(5, 2, '2026-09-12', '2026-09-26', '2026-09-24'),
(8, 4, '2026-09-15', '2026-09-29', '2026-09-28'),
(4, 6, '2026-10-02', '2026-10-16', '2026-10-14'),
(7, 5, '2026-10-05', '2026-10-19', '2026-10-18'),
(3, 4, '2026-09-25', '2026-10-09', null),
(9, 3, '2026-09-28', '2026-10-12', null),
(4, 5, '2026-10-01', '2026-10-15', null),
(6, 6, '2026-10-18', '2026-11-01', null),
(1, 2, '2026-10-20', '2026-11-03', null),
(8, 1, '2026-10-22', '2026-11-05', null);

delimiter $$

create trigger before_issue
before insert on loans
for each row
begin
    declare copies int;
    if new.return_date is null then
        select copies_available into copies from books where book_id = new.book_id;
        if copies <= 0 then
            signal sqlstate '45000' set message_text = 'No copies available for this book';
        end if;
    end if;
end$$

create trigger after_issue
after insert on loans
for each row
begin
    if new.return_date is null then
        update books set copies_available = copies_available - 1
        where book_id = new.book_id;
    end if;
end$$

create trigger before_return
before update on loans
for each row
begin
    if old.return_date is not null then
        signal sqlstate '45000' set message_text = 'This book is already returned';
    end if;
    if new.return_date < old.issue_date then
        signal sqlstate '45000' set message_text = 'Return date cannot be before issue date';
    end if;
end$$

create trigger after_return
after update on loans
for each row
begin
    if old.return_date is null and new.return_date is not null then
        update books set copies_available = copies_available + 1
        where book_id = new.book_id;
    end if;
end$$

delimiter ;

set @loan_days = 14;

select l.loan_id, b.title, br.borrower_name, l.issue_date, l.due_date, l.return_date,
    case
        when l.return_date is not null then 'Returned'
        when l.due_date < curdate() then 'Overdue'
        else 'Active'
    end as loan_status
from loans l
join books b on l.book_id = b.book_id
join borrowers br on l.borrower_id = br.borrower_id
order by l.loan_id;

select count(*) as active_loans,
    sum(case when due_date < curdate() then 1 else 0 end) as overdue_loans
from loans
where return_date is null;

select b.title, b.author, count(l.loan_id) as times_borrowed
from books b
join loans l on b.book_id = l.book_id
group by b.book_id, b.title, b.author
order by times_borrowed desc
limit 5;

select l.loan_id, b.title, br.borrower_name, br.roll_no, l.due_date,
    datediff(curdate(), l.due_date) as days_overdue
from loans l
join books b on l.book_id = b.book_id
join borrowers br on l.borrower_id = br.borrower_id
where l.return_date is null and l.due_date < curdate()
order by days_overdue desc;

select date_format(issue_date, '%Y-%m') as month, count(*) as books_issued
from loans
group by date_format(issue_date, '%Y-%m')
order by month;

select b.category, count(l.loan_id) as total_loans
from books b
join loans l on b.book_id = l.book_id
group by b.category
order by total_loans desc;