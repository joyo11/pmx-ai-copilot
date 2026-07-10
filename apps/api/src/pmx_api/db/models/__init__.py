"""SQLAlchemy models — importing this package registers every table on ``Base.metadata``.

The order of imports below matters only for readability; SQLAlchemy resolves FKs
lazily. Each aggregate root lives in its own module.
"""

from pmx_api.db.models.base import Base
from pmx_api.db.models.chat import ChatMessage, ChatSession
from pmx_api.db.models.document import Document, DocumentChunk
from pmx_api.db.models.event import Event
from pmx_api.db.models.health import HealthSnapshot
from pmx_api.db.models.notification import Notification
from pmx_api.db.models.organization import Organization
from pmx_api.db.models.project import Project, ProjectMember
from pmx_api.db.models.report import Report
from pmx_api.db.models.risk import Risk
from pmx_api.db.models.structured import BudgetLine, ChangeOrder, Meeting, Rfi, ScheduleTask
from pmx_api.db.models.user import User

__all__ = [
    "Base",
    "BudgetLine",
    "ChangeOrder",
    "ChatMessage",
    "ChatSession",
    "Document",
    "DocumentChunk",
    "Event",
    "HealthSnapshot",
    "Meeting",
    "Notification",
    "Organization",
    "Project",
    "ProjectMember",
    "Report",
    "Rfi",
    "Risk",
    "ScheduleTask",
    "User",
]
