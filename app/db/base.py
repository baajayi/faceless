import uuid

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def new_uuid() -> str:
    """Generate a new UUID4 string — used as default PK factory."""
    return str(uuid.uuid4())
