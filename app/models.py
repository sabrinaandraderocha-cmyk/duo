import os
from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    Text,
    Index,
)
from sqlalchemy.orm import relationship
from .db import Base

# ======================================================
# Schema dinâmico
# ======================================================
DB_SCHEMA = os.getenv("DB_SCHEMA", "").strip()

def fk(table: str) -> str:
    return f"{DB_SCHEMA}.{table}.id" if DB_SCHEMA else f"{table}.id"

def table_args(*constraints):
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

    users = relationship("User", back_populates="couple", cascade="all, delete-orphan")
    entries = relationship("Entry", back_populates="couple", cascade="all, delete-orphan")
    special_dates = relationship("SpecialDate", back_populates="couple", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="couple", cascade="all, delete-orphan")


# =========================
# USUÁRIO (COM RECOVERY KEY)
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
    
    # NOVO CAMPO: Palavra de segurança
    recovery_key = Column(String(100), nullable=False, default="") 

    couple = relationship("Couple", back_populates="users")


# =========================
# REGISTRO DIÁRIO
# =========================
class Entry(Base):
    __tablename__ = "diary_entries" 
    
    __table_args__ = table_args(
        Index("ix_entries_couple_day", "couple_id", "day"),
    )

    id = Column(Integer, primary_key=True)
    couple_id = Column(Integer, ForeignKey(fk("couples"), ondelete="CASCADE"), nullable=False)

    day = Column(String(10), nullable=False)      # YYYY-MM-DD
    author = Column(String(8), nullable=False)    # "me" | "par"

    mood = Column(String(120), default="")
    moment_special = Column(Text, default="")
    love_action = Column(Text, default="")
    character = Column(String(200), default="")
    music = Column(String(200), default="")
    updated_at = Column(String(32), default="")
    tags_csv = Column(Text, default="")

    couple = relationship("Couple", back_populates="entries")


# =========================
# DATAS ESPECIAIS
# =========================
class SpecialDate(Base):
    __tablename__ = "special_dates"
    __table_args__ = table_args(Index("ix_special_dates_couple_id", "couple_id"))

    id = Column(Integer, primary_key=True)
    couple_id = Column(Integer, ForeignKey(fk("couples"), ondelete="CASCADE"), nullable=False)

    type = Column(String(50), nullable=False)
    label = Column(String(80), nullable=False)
    date = Column(String(10), nullable=False)
    note = Column(Text, default="")

    couple = relationship("Couple", back_populates="special_dates")


# =========================
# NOTIFICAÇÕES
# =========================
class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = table_args(Index("ix_notifications_couple_id", "couple_id"))

    id = Column(Integer, primary_key=True)
    couple_id = Column(Integer, ForeignKey(fk("couples"), ondelete="CASCADE"), nullable=False)

    created_at = Column(String(20), nullable=False)
    title = Column(String(120), nullable=False)
    body = Column(Text, default="")
    is_read = Column(Integer, default=0)

    couple = relationship("Couple", back_populates="notifications")
