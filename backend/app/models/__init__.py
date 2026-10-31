"""Model registry.

Importing this package registers every mapper (and therefore every relationship
string) exactly once. Repositories, migrations and tests import from here.
"""

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now
from app.models.credit_ledger import CreditLedger
from app.models.enums import GenerationStatus, ProjectStatus
from app.models.generation_job import GenerationJob
from app.models.project import Project, enum_column
from app.models.user import User

__all__ = [
    "Base",
    "CreditLedger",
    "GenerationJob",
    "GenerationStatus",
    "Project",
    "ProjectStatus",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "User",
    "enum_column",
    "utc_now",
]
