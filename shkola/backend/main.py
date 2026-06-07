import os
import sys
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, date
from pydantic import BaseModel, ConfigDict
from typing import Optional, List
import hashlib
import uuid
from contextlib import asynccontextmanager

from config import ADMIN_EMAIL, ADMIN_PASSWORD
from models import Book, User, Loan, LoanStatus
from database import init_db, get_session
from redis_client import (
    get_cached_catalog, set_cached_catalog, invalidate_catalog_cache,
    acquire_book_lock, release_book_lock, create_temp_reservation,
    delete_temp_reservation, increment_view, get_top_books,
    create_admin_session, check_admin_session, delete_admin_session
)

# Get absolute path to frontend directory
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    from redis_client import close_redis
    await close_redis()


app = FastAPI(title="Школьная библиотека - Первомайская СОШ", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Pydantic Models ---

class BookOut(BaseModel):
    id: int
    title: str
    author: str
    year: Optional[int] = None
    grade: Optional[str] = None
    purpose: Optional[str] = None
    total_copies: int
    available_copies: int
    cover_url: Optional[str] = None
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class BookCreate(BaseModel):
    title: str
    author: str
    year: Optional[int] = None
    grade: Optional[str] = None
    purpose: Optional[str] = None
    total_copies: int = 1
    available_copies: Optional[int] = None
    cover_url: Optional[str] = None


class BookUpdate(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    year: Optional[int] = None
    grade: Optional[str] = None
    purpose: Optional[str] = None
    total_copies: Optional[int] = None
    available_copies: Optional[int] = None
    cover_url: Optional[str] = None


class LoanCreate(BaseModel):
    book_id: int
    borrower_name: str
    purpose: str
    quantity: int = 1


class LoanOut(BaseModel):
    id: int
    book_id: int
    book_title: Optional[str] = None
    borrower_name: str
    purpose: Optional[str] = None
    quantity: int
    date_borrowed: datetime
    date_returned: Optional[datetime] = None
    status: str

    model_config = ConfigDict(from_attributes=True)


class RegisterRequest(BaseModel):
    name: str
    grade: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class StudentLoginRequest(BaseModel):
    name: str
    password: str


class AuthResponse(BaseModel):
    success: bool
    user: dict
    message: str


# --- Helper ---

def book_to_dict(book: Book) -> dict:
    return {
        "id": book.id,
        "title": book.title,
        "author": book.author,
        "year": book.year,
        "grade": book.grade,
        "purpose": book.purpose,
        "total_copies": book.total_copies,
        "available_copies": book.available_copies,
        "cover_url": book.cover_url,
        "description": book.description,
    }


# --- Serve Frontend ---
app.mount("/static", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")


@app.get("/")
async def serve_frontend():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"error": "Frontend not found"}


# --- Auth Routes ---

@app.post("/api/register")
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(User).where(User.name == data.name))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Пользователь с таким именем уже существует")

    user = User(
        name=data.name,
        grade=data.grade,
        password_hash=hashlib.sha256(data.password.encode()).hexdigest(),
        role="student",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return AuthResponse(
        success=True,
        user={"id": user.id, "name": user.name, "grade": user.grade, "role": user.role},
        message="Регистрация успешна"
    )


@app.post("/api/login")
async def login_student(data: StudentLoginRequest, db: AsyncSession = Depends(get_session)):
    password_hash = hashlib.sha256(data.password.encode()).hexdigest()
    result = await db.execute(
        select(User).where(
            User.name == data.name,
            User.password_hash == password_hash,
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Неверное имя или пароль")

    return AuthResponse(
        success=True,
        user={"id": user.id, "name": user.name, "grade": user.grade, "role": user.role},
        message="Вход выполнен"
    )


# --- API Routes ---

@app.get("/api/books")
async def get_books(
    author: Optional[str] = None,
    grade: Optional[str] = None,
    purpose: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_session),
):
    # Try cache first
    if not author and not grade and not purpose and not search:
        cached = await get_cached_catalog()
        if cached is not None:
            return cached

    # Build query
    query = select(Book)
    if author:
        query = query.where(Book.author.ilike(f"%{author}%"))
    if grade:
        query = query.where(Book.grade == grade)
    if purpose:
        query = query.where(Book.purpose == purpose)
    if search:
        query = query.where(
            or_(
                Book.title.ilike(f"%{search}%"),
                Book.author.ilike(f"%{search}%"),
            )
        )

    result = await db.execute(query)
    books = result.scalars().all()
    books_data = [book_to_dict(b) for b in books]

    # Cache only full catalog
    if not author and not grade and not purpose and not search:
        await set_cached_catalog(books_data)

    return books_data


@app.get("/api/books/{book_id}")
async def get_book(book_id: int, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(Book).where(Book.id == book_id))
    book = result.scalar_one_or_none()
    if not book:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    # Increment view counter in Redis
    await increment_view(book_id)

    return book_to_dict(book)


@app.get("/api/filters")
async def get_filters(db: AsyncSession = Depends(get_session)):
    """Get available filter options."""
    # Authors
    authors_result = await db.execute(
        select(Book.author).distinct().order_by(Book.author)
    )
    authors = [row[0] for row in authors_result.fetchall()]

    # Grades
    grades_result = await db.execute(
        select(Book.grade).distinct().order_by(Book.grade)
    )
    grades = sorted(
        [row[0] for row in grades_result.fetchall() if row[0]],
        key=lambda x: int(x.split("-")[0]) if x and x[0].isdigit() else 99,
    )

    # Purposes
    purposes_result = await db.execute(
        select(Book.purpose).distinct().order_by(Book.purpose)
    )
    purposes = [row[0] for row in purposes_result.fetchall() if row[0]]

    return {"authors": authors, "grades": grades, "purposes": purposes}


@app.post("/api/loans", status_code=201)
async def create_loan(loan_data: LoanCreate, db: AsyncSession = Depends(get_session)):
    # 1. Check book exists and has available copies
    result = await db.execute(select(Book).where(Book.id == loan_data.book_id))
    book = result.scalar_one_or_none()
    if not book:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    if book.available_copies < loan_data.quantity:
        raise HTTPException(
            status_code=400,
            detail=f"Недостаточно доступных экземпляров. Доступно: {book.available_copies}",
        )

    # 2. Try to acquire lock in Redis
    lock_key = f"{loan_data.borrower_name}:{loan_data.book_id}"
    locked = await acquire_book_lock(loan_data.book_id, lock_key)
    if not locked:
        raise HTTPException(
            status_code=409,
            detail="Книга временно заблокирована другим пользователем. Попробуйте позже.",
        )

    try:
        # 3. Update PostgreSQL
        book.available_copies -= loan_data.quantity

        # Find or create user
        user_result = await db.execute(
            select(User).where(User.name == loan_data.borrower_name).limit(1)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            user = User(
                name=loan_data.borrower_name,
                role="student",
                is_active=True,
            )
            db.add(user)
            await db.flush()

        # Create loan
        loan = Loan(
            book_id=loan_data.book_id,
            user_id=user.id,
            borrower_name=loan_data.borrower_name,
            purpose=loan_data.purpose,
            quantity=loan_data.quantity,
            status=LoanStatus.active.value,
        )
        db.add(loan)
        await db.commit()

        # 4. Cleanup Redis cache
        await invalidate_catalog_cache()

        return {"success": True, "loan_id": loan.id, "message": "Книга успешно забронирована"}

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await release_book_lock(loan_data.book_id)


# --- Admin Routes ---

@app.post("/api/admin/login")
async def admin_login(login_data: LoginRequest):
    if login_data.email != ADMIN_EMAIL or login_data.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Неверный email или пароль")

    session_id = str(uuid.uuid4())
    await create_admin_session(session_id)
    return {"session_id": session_id}


@app.post("/api/admin/logout")
async def admin_logout(request: Request):
    session_id = request.headers.get("X-Session-Id")
    if session_id:
        await delete_admin_session(session_id)
    return {"success": True}


async def verify_admin(request: Request):
    session_id = request.headers.get("X-Session-Id")
    if not session_id:
        raise HTTPException(status_code=401, detail="Не авторизован")
    valid = await check_admin_session(session_id)
    if not valid:
        raise HTTPException(status_code=401, detail="Сессия истекла")


# Books CRUD (admin)
@app.post("/api/admin/books", dependencies=[Depends(verify_admin)])
async def create_book(book: BookCreate, db: AsyncSession = Depends(get_session)):
    new_book = Book(
        title=book.title,
        author=book.author,
        year=book.year,
        grade=book.grade,
        purpose=book.purpose,
        total_copies=book.total_copies,
        available_copies=book.available_copies or book.total_copies,
        cover_url=book.cover_url,
    )
    db.add(new_book)
    await db.commit()
    await db.refresh(new_book)
    await invalidate_catalog_cache()
    return book_to_dict(new_book)


@app.put("/api/admin/books/{book_id}", dependencies=[Depends(verify_admin)])
async def update_book(
    book_id: int,
    book_data: BookUpdate,
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(select(Book).where(Book.id == book_id))
    book = result.scalar_one_or_none()
    if not book:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    update_data = book_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(book, key, value)

    await db.commit()
    await db.refresh(book)
    await invalidate_catalog_cache()
    return book_to_dict(book)


@app.delete("/api/admin/books/{book_id}", dependencies=[Depends(verify_admin)])
async def delete_book(book_id: int, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(Book).where(Book.id == book_id))
    book = result.scalar_one_or_none()
    if not book:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    # Check if book has active loans
    loans_result = await db.execute(
        select(Loan).where(
            Loan.book_id == book_id,
            Loan.status == LoanStatus.active.value,
        )
    )
    active_loans = loans_result.scalars().all()
    if active_loans:
        raise HTTPException(
            status_code=400,
            detail="Нельзя удалить книгу с активными бронированиями",
        )

    await db.delete(book)
    await db.commit()
    await invalidate_catalog_cache()
    return {"success": True, "message": "Книга удалена"}


# Loans management (admin)
@app.get("/api/admin/loans", dependencies=[Depends(verify_admin)])
async def get_all_loans(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_session),
):
    query = select(Loan)
    if status:
        query = query.where(Loan.status == status)
    query = query.order_by(Loan.date_borrowed.desc())

    result = await db.execute(query)
    loans = result.scalars().all()

    # Fetch book titles
    loans_data = []
    for loan in loans:
        book_result = await db.execute(select(Book).where(Book.id == loan.book_id))
        book = book_result.scalar_one_or_none()
        loans_data.append({
            "id": loan.id,
            "book_id": loan.book_id,
            "book_title": book.title if book else "Неизвестно",
            "borrower_name": loan.borrower_name,
            "purpose": loan.purpose,
            "quantity": loan.quantity,
            "date_borrowed": loan.date_borrowed.isoformat() if loan.date_borrowed else None,
            "date_returned": loan.date_returned.isoformat() if loan.date_returned else None,
            "status": loan.status,
        })

    return loans_data


@app.post("/api/admin/loans/{loan_id}/return", dependencies=[Depends(verify_admin)])
async def return_book(loan_id: int, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(Loan).where(Loan.id == loan_id))
    loan = result.scalar_one_or_none()

    if not loan:
        raise HTTPException(status_code=404, detail="Бронирование не найдено")

    if loan.status == LoanStatus.returned.value:
        raise HTTPException(status_code=400, detail="Книга уже возвращена")

    # Update loan
    loan.status = LoanStatus.returned.value
    loan.date_returned = datetime.utcnow()

    # Restore available copies
    book_result = await db.execute(select(Book).where(Book.id == loan.book_id))
    book = book_result.scalar_one_or_none()
    if book:
        book.available_copies += loan.quantity

    await db.commit()
    await invalidate_catalog_cache()

    return {"success": True, "message": "Книга отмечена как возвращённая"}


# Statistics (admin)
@app.get("/api/admin/stats", dependencies=[Depends(verify_admin)])
async def get_stats(db: AsyncSession = Depends(get_session)):
    # Total books
    books_result = await db.execute(select(func.count(Book.id)))
    total_books = books_result.scalar()

    # Total active loans
    loans_result = await db.execute(
        select(func.count(Loan.id)).where(Loan.status == LoanStatus.active.value)
    )
    active_loans = loans_result.scalar()

    # Total returned today
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    returned_result = await db.execute(
        select(func.count(Loan.id)).where(
            Loan.status == LoanStatus.returned.value,
            Loan.date_returned >= today_start,
        )
    )
    returned_today = returned_result.scalar()

    # Top books from Redis
    top_books = await get_top_books(10)

    return {
        "total_books": total_books,
        "active_loans": active_loans,
        "returned_today": returned_today,
        "top_books": top_books,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)