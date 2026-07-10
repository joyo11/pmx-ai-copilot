"""Database layer: SQLAlchemy 2 models, engine, session factory.

Import :data:`Base` from :mod:`pmx_api.db.models` and every aggregate root
module so ``Base.metadata`` is populated before Alembic autogenerate runs.
"""

from pmx_api.db.models import Base  # re-export

__all__ = ["Base"]
