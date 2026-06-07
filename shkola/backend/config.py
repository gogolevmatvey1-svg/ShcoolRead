import os

# PostgreSQL (production)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/school_library")

# Redis (uses in-memory fallback if Redis is unavailable)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Admin credentials
ADMIN_EMAIL = "admin@school.ru"
ADMIN_PASSWORD = "admin123"

# Cache TTL (seconds)
CATALOG_CACHE_TTL = 300  # 5 minutes
BOOK_LOCK_TTL = 30       # 30 seconds