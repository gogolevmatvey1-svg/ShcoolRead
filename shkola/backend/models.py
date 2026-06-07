from sqlalchemy import Column, Integer, String, Text, Date, DateTime, Boolean, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime, date
import enum

Base = declarative_base()


class UserRole(str, enum.Enum):
    admin = "admin"
    librarian = "librarian"
    teacher = "teacher"
    student = "student"


class LoanStatus(str, enum.Enum):
    active = "active"
    returned = "returned"


class Book(Base):
    __tablename__ = "books"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), nullable=False, index=True)
    author = Column(String(255), nullable=False, index=True)
    year = Column(Integer, nullable=True)
    grade = Column(String(50), nullable=True, index=True)  # e.g. "5-11"
    purpose = Column(String(100), nullable=True, index=True)  # e.g. "учебник", "внеклассное чтение"
    total_copies = Column(Integer, nullable=False, default=1)
    available_copies = Column(Integer, nullable=False, default=1)
    cover_url = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)

    loans = relationship("Loan", back_populates="book")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=True)
    role = Column(String(50), nullable=False, default=UserRole.student.value)
    grade = Column(String(50), nullable=True)  # e.g. "5", "6", "7-11"
    is_active = Column(Boolean, default=True)

    loans = relationship("Loan", back_populates="user")


class Loan(Base):
    __tablename__ = "loans"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    borrower_name = Column(String(255), nullable=False)
    purpose = Column(String(255), nullable=True)
    quantity = Column(Integer, nullable=False, default=1)
    date_borrowed = Column(DateTime, default=datetime.utcnow)
    date_returned = Column(DateTime, nullable=True)
    status = Column(String(50), default=LoanStatus.active.value)

    book = relationship("Book", back_populates="loans")
    user = relationship("User", back_populates="loans")