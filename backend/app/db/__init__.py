"""Database subsystem: schema, connection, lazy init, and seeding."""

from .database import Database, get_db

__all__ = ["Database", "get_db"]
