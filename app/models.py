import os
from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship
from .db import Base

# ======================================================
# Schema dinâmico
# - Postgres (Neon): usa schema (ex: duo)
# - SQLite/local: ignora schema
# ======================================================
DB_SCHEMA = os.getenv("DB_SCHEMA", "").strip()

def fk(table: str) -> str:
    """Helper para ForeignKey com ou sem schema"""
    return f"{DB_SCHEMA}.{table}.id" if DB_SCHEMA else f"{table}.id"

def table_args(*constraints):
    """Monta __table_args__ corretamente"""
    if DB_SCHEMA:
        return (*constraints, {"schema": DB_SCHEMA})
    return constraints


# =========================
# CASAL
# =========================
class Couple(Base):
    __tablename__ = "couples"
    __table_args__ = table_args()

    id = Column(Integer, primary_key=True)
    code = Column(String(16), unique=True, index=True, nullable=False)

    users = relationship(
        "User",
        back_populates="couple",
        cascade="all, delete-orphan",
    )
    entries = relationship(
        "Entry",
        back_populates="couple",
        cascade="all, delete-orphan",
    )
    special_dates = relationship(
        "SpecialDate",
        back_populates="couple",
        cascade="all, delete-orphan",
    )
    notifications = relationship(
        "Notification",
        back_populates="couple",
        cascade="all, delete-orphan",
    )


# =========================
# USUÁRIO
# =========================
class User(Base):
    __tablename__ = "users"
    __table_args__ = table_args(
        Index("ix_users_email", "email", unique=True),
        Index("ix_users_couple_id", "couple_id"),
    )

    id = Column(Integer, primary_key=True)

    couple_id = Column(
        Integer,
        ForeignKey(fk("couples"), ondelete="SET NULL"),
        nullable=True,
    )

    name = Column(String(80), nullable=False)
    email = Column(String(160), nullable=False)
    password_hash = Column(String(255), nullable=False)

    couple = relationship("Couple", back_populates="users")


# =========================
# REGISTRO DIÁRIO
# =========================
class Entry(Base):
    __tablename__ = "entries"
    __table_args__ = table_args(
        UniqueConstraint("couple_id", "day", "author", name="uq_entry_side"),
        Index("ix_entries_couple_day", "couple_id", "day"),
    )

    id = Column(Integer, primary_key=True)

    couple_id = Column(
        Integer,
        ForeignKey(fk("couples"), ondelete="CASCADE"),
        nullable=False,
    )

    day = Column(String(10), nullable=False)      # YYYY-MM-DD
    author = Column(String(8), nullable=False)    # "me" | "par"

    mood = Column(String(120), default="")
    moment_special = Column(Text, default="")
    love_action = Column(Text, default="")
    character = Column(String(200), default="")
    music = Column(String(200), default="")
    updated_at = Column(String(32), default="")

    # Tags do diário (CSV simples)
    tags_csv = Column(Text, default="")

    couple = relationship("Couple", back_populates="entries")


# =========================
# DATAS ESPECIAIS
# =========================
class SpecialDate(Base):
    __tablename__ = "special_dates"
    __table_args__ = table_args(
        UniqueConstraint("couple_id", "type", "date", name="uq_special_date"),
        Index("ix_special_dates_couple_id", "couple_id"),
    )

    id = Column(Integer, primary_key=True)

    couple_id = Column(
        Integer,
        ForeignKey(fk("couples"), ondelete="CASCADE"),
        nullable=False,
    )

    # ex: primeiro_encontro, primeiro_beijo, casamento
    type = Column(String(50), nullable=False)

    # ex: "Primeiro encontro"
    label = Column(String(80), nullable=False)

    # YYYY-MM-DD
    date = Column(String(10), nullable=False)

    note = Column(Text, default="")

    couple = relationship("Couple", back_populates="special_dates")


# =========================
# NOTIFICAÇÕES
# =========================
class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = table_args(
        Index("ix_notifications_couple_id", "couple_id"),
    )

    id = Column(Integer, primary_key=True)

    couple_id = Column(
        Integer,
        ForeignKey(fk("couples"), ondelete="CASCADE"),
        nullable=False,
    )

    created_at = Column(String(20), nullable=False)  # dd/mm/yyyy
    title = Column(String(120), nullable=False)
    body = Column(Text, default="")
    is_read = Column(Integer, default=0)  # 0 = não lida, 1 = lida

    couple = relationship("Couple", back_populates="notifications")
