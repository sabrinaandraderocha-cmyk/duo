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
# CASAL (Renomeado para forçar reset)
# =========================
class Couple(Base):
    __tablename__ = "app_couples"  # <--- MUDANÇA AQUI
    __table_args__ = table_args()

    id = Column(Integer, primary_key=True)
    code = Column(String(16), unique=True, index=True, nullable=False)

    users = relationship("User", back_populates="couple", cascade="all, delete-orphan")
    entries = relationship("Entry", back_populates="couple", cascade="all, delete-orphan")
    special_dates = relationship("SpecialDate", back_populates="couple", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="couple", cascade="all, delete-orphan")


# =========================
# USUÁRIO (Renomeado para forçar reset)
# =========================
class User(Base):
    __tablename__ = "app_users"  # <--- MUDANÇA AQUI
    __table_args__ = table_args(
        Index("ix_app_users_email", "email", unique=True),
        Index("ix_app_users_couple_id", "couple_id"),
    )

    id = Column(Integer, primary_key=True)

    couple_id = Column(
        Integer,
        ForeignKey(fk("app_couples"), ondelete="SET NULL"), # Atualizado para nova tabela
        nullable=True,
    )

    name = Column(String(80), nullable=False)
    email = Column(String(160), nullable=False)
    password_hash = Column(String(255), nullable=False)
    
    # Agora a nova tabela nascerá com este campo!
    recovery_key = Column(String(100), nullable=False, default="") 

    couple = relationship("Couple", back_populates="users")


# =========================
# REGISTRO DIÁRIO
# =========================
class Entry(Base):
    __tablename__ = "diary_entries_v2" # <--- MUDANÇA AQUI (Só pra garantir)
    
    __table_args__ = table_args(
        Index("ix_entries_v2_couple_day", "couple_id", "day"),
    )

    id = Column(Integer, primary_key=True)
    couple_id = Column(Integer, ForeignKey(fk("app_couples"), ondelete="CASCADE"), nullable=False)

    day = Column(String(10), nullable=False)      
    author = Column(String(8), nullable=False)    

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
    __tablename__ = "app_special_dates" # <--- MUDANÇA AQUI
    __table_args__ = table_args(Index("ix_special_dates_v2_couple", "couple_id"))

    id = Column(Integer, primary_key=True)
    couple_id = Column(Integer, ForeignKey(fk("app_couples"), ondelete="CASCADE"), nullable=False)

    type = Column(String(50), nullable=False)
    label = Column(String(80), nullable=False)
    date = Column(String(10), nullable=False)
    note = Column(Text, default="")

    couple = relationship("Couple", back_populates="special_dates")


# =========================
# NOTIFICAÇÕES
# =========================
class Notification(Base):
    __tablename__ = "app_notifications" # <--- MUDANÇA AQUI
    __table_args__ = table_args(Index("ix_notifications_v2_couple", "couple_id"))

    id = Column(Integer, primary_key=True)
    couple_id = Column(Integer, ForeignKey(fk("app_couples"), ondelete="CASCADE"), nullable=False)

    created_at = Column(String(20), nullable=False)
    title = Column(String(120), nullable=False)
    body = Column(Text, default="")
    is_read = Column(Integer, default=0)

    couple = relationship("Couple", back_populates="notifications")
