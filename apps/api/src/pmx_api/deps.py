"""FastAPI request-scoped dependencies.

Kept intentionally small. Auth deps land here in M0.4.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pmx_api.db.session import get_async_session


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped :class:`AsyncSession`."""
    async for session in get_async_session():
        yield session


DBSession = Annotated[AsyncSession, Depends(get_db)]
"""Type alias for injecting an async DB session into a route handler."""
