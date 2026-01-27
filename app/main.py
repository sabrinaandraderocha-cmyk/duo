import os
from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from .db import Base

# =========================
# Schema (compatível com SQLite e Postgres)
# - SQLite NÃO suporta schema; Postgres suporta.
# - Use DB_SCHEMA=duo no ambiente se quiser schema.
# =========================
DB_SCHEMA = os.getenv("DB_SCHEMA", "").strip()

def tn(name: str) -> str:
    """table name fully qualified for ForeignKey"""
    return f"{DB_SCHEMA}.{name}" if DB_SCHEMA else name

def table_args(*args):
    """helper: monta __table_args__ com/sem schema"""
    if DB_SCHEMA:
        return (*args, {"schema": DB_SCHEMA})
    return args


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
# USUÁRIO
# =========================
class User(Base):
    __tablename__ = "users"
    __table_args__ = table_args()

    id = Column(Integer, primary_key=True)

    couple_id = Column(
        Integer,
        ForeignKey(f"{tn('couples')}.id"),
        nullable=True,
    )

    name = Column(String(80), nullable=False)
    email = Column(String(160), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)

    couple = relationship("Couple", back_populates="users")


# =========================
# REGISTRO DIÁRIO
# =========================
class Entry(Base):
    __tablename__ = "entries"
    __table_args__ = table_args(
        UniqueConstraint("couple_id", "day", "author", name="uq_entry_side"),
    )

    id = Column(Integer, primary_key=True)

    couple_id = Column(
        Integer,
        ForeignKey(f"{tn('couples')}.id"),
        nullable=False,
        index=True,
    )

    day = Column(String(10), index=True, nullable=False)   # YYYY-MM-DD
    author = Column(String(8), nullable=False)             # "me" ou "par"

    mood = Column(String(120), default="")
    moment_special = Column(Text, default="")
    love_action = Column(Text, default="")
    character = Column(String(200), default="")
    music = Column(String(200), default="")
    updated_at = Column(String(32), default="")

    # ✅ NOVO: tags do diário (CSV simples)
    tags_csv = Column(Text, default="")

    couple = relationship("Couple", back_populates="entries")


# =========================
# DATAS ESPECIAIS
# =========================
class SpecialDate(Base):
    __tablename__ = "special_dates"
    __table_args__ = table_args(
        UniqueConstraint("couple_id", "type", "date", name="uq_special_date"),
    )

    id = Column(Integer, primary_key=True)

    couple_id = Column(
        Integer,
        ForeignKey(f"{tn('couples')}.id"),
        nullable=False,
        index=True,
    )

    # chave padronizada: primeiro_encontro, primeiro_beijo, primeira_vez, casamento, outro
    type = Column(String(50), nullable=False)

    # label humano para mostrar no app (ex.: "Primeiro beijo")
    label = Column(String(80), nullable=False)

    # data em YYYY-MM-DD
    date = Column(String(10), nullable=False)

    # detalhe opcional
    note = Column(Text, default="")

    couple = relationship("Couple", back_populates="special_dates")


# =========================
# NOTIFICAÇÕES INTERNAS
# =========================
class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = table_args()

    id = Column(Integer, primary_key=True)

    couple_id = Column(
        Integer,
        ForeignKey(f"{tn('couples')}.id"),
        nullable=False,
        index=True,
    )

    created_at = Column(String(20), nullable=False)  # dd/mm/yyyy
    title = Column(String(120), nullable=False)
    body = Column(Text, default="")

    # 0/1 (SQLite não tem boolean nativo tão “puro”)
    is_read = Column(Integer, default=0)

    couple = relationship("Couple", back_populates="notifications")
