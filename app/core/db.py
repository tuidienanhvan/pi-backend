"""Database engine + session factory (async SQLAlchemy 2.0)."""

from collections.abc import AsyncGenerator
from urllib.parse import parse_qs, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


def _build_engine_args(url: str) -> tuple[str, dict]:
    """Translate libpq-style URL flags into asyncpg connect_args.

    asyncpg does NOT accept `sslmode=` query param when SQLAlchemy parses
    the URL and passes args through. The robust pattern:
      1. Strip every query param from the URL handed to SQLAlchemy.
      2. Convert SSL/auth hints into `connect_args={"ssl": ...}`.

    Recognised input flags (added by Neon/Supabase/Railway etc.):
      - sslmode=require | verify-ca | verify-full   → ssl=True
      - sslmode=disable                              → ssl=False
      - ssl=true | ssl=require                       → ssl=True
    """
    parts = urlsplit(url)
    params = parse_qs(parts.query)
    connect_args: dict = {}

    sslmode = (params.get("sslmode") or params.get("ssl") or [""])[0].lower()
    if sslmode in {"require", "verify-ca", "verify-full", "true"}:
        connect_args["ssl"] = True
    elif sslmode == "disable":
        connect_args["ssl"] = False
    # Fallback: cloud Postgres hosts always require TLS even without explicit flag
    elif any(host in parts.netloc for host in ("neon.tech", "supabase.co", "railway.app", "cockroachlabs.cloud")):
        connect_args["ssl"] = True

    clean_url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment))
    return clean_url, connect_args


_clean_url, _connect_args = _build_engine_args(settings.database_url)

engine = create_async_engine(
    _clean_url,
    connect_args=_connect_args,
    echo=settings.app_debug and not settings.is_production,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a session, commits/rolls back, closes."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
