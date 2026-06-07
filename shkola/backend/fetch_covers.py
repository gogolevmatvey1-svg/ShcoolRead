"""
Скрипт для поиска и обновления обложек книг через OpenLibrary API.
Запускать: python fetch_covers.py
"""
import asyncio
import aiohttp
import sys
import os

# Добавляем путь к backend в sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from models import Book, Base
from config import DATABASE_URL


async def search_openlibrary(session: aiohttp.ClientSession, title: str, author: str) -> str | None:
    """Search for a book cover on OpenLibrary."""
    # Clean up query
    query = f"{title} {author}"
    # Remove special chars and limit
    query = query.replace("(комплект из 4 томов)", "").replace("(комплект)", "")
    query = query.replace("  ", " ").strip()
    
    url = "https://openlibrary.org/search.json"
    params = {
        "q": query,
        "limit": 5,
        "lang": "ru",
    }
    
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
            if response.status != 200:
                return None
            data = await response.json()
            
            if not data.get("docs"):
                return None
            
            for doc in data["docs"]:
                cover_i = doc.get("cover_i")
                if cover_i:
                    # Verify by checking if cover actually exists
                    cover_url = f"https://covers.openlibrary.org/b/id/{cover_i}-L.jpg"
                    async with session.head(cover_url, timeout=aiohttp.ClientTimeout(total=5)) as cover_resp:
                        if cover_resp.status == 200:
                            return cover_url
            return None
    except Exception:
        return None


async def search_google_books(session: aiohttp.ClientSession, title: str, author: str) -> str | None:
    """Fallback: Search for a book cover on Google Books."""
    query = f"intitle:{title}+inauthor:{author}"
    url = "https://www.googleapis.com/books/v1/volumes"
    params = {
        "q": query,
        "langRestrict": "ru",
        "maxResults": 3,
    }
    
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
            if response.status != 200:
                return None
            data = await response.json()
            
            if not data.get("items"):
                return None
            
            for item in data["items"]:
                info = item.get("volumeInfo", {})
                image_links = info.get("imageLinks", {})
                # Try large thumbnail first
                for key in ["large", "extraLarge", "thumbnail"]:
                    img_url = image_links.get(key)
                    if img_url:
                        # Remove http:// and https:// protocols issue
                        img_url = img_url.replace("http://", "https://")
                        return img_url
            return None
    except Exception:
        return None


async def main():
    # Create engine
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session_gen = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session_gen() as db_session:
        result = await db_session.execute(select(Book))
        books = result.scalars().all()
        
        print(f"Найдено книг: {len(books)}")
        
        async with aiohttp.ClientSession() as session:
            updated = 0
            failed = 0
            skipped = 0
            
            for i, book in enumerate(books, 1):
                print(f"\n[{i}/{len(books)}] {book.title} — {book.author}")
                
                # Try OpenLibrary first
                cover_url = await search_openlibrary(session, book.title, book.author)
                
                # If failed, try Google Books
                if not cover_url:
                    cover_url = await search_google_books(session, book.title, book.author)
                
                if cover_url:
                    book.cover_url = cover_url
                    updated += 1
                    print(f"  + Найдена: {cover_url[:80]}...")
                else:
                    failed += 1
                    print(f"  - Не найдена")
                
                # Save every 10 books
                if i % 10 == 0:
                    await db_session.commit()
                    print(f"  --- Сохранено {i} книг ---")
            
            # Final save
            await db_session.commit()
            
            print(f"\n\n{'='*50}")
            print("Готово!")
            print(f"+ Обновлено обложек: {updated}")
            print(f"- Не найдено: {failed}")
            print(f"Пропущено: {skipped}")
            print(f"{'='*50}")
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())