from sqlalchemy import Column, Integer, String, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from .db import Base

class Couple(Base):
    __tablename__ = "couples"
    id = Column(Integer, primary_key=True)
    code = Column(String(16), unique=True, index=True, nullable=False)

    users = relationship("User", back_populates="couple")
    entries = relationship("Entry", back_populates="couple")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    couple_id = Column(Integer, ForeignKey("couples.id"), nullable=True)

    name = Column(String(80), nullable=False)
    email = Column(String(160), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)

    couple = relationship("Couple", back_populates="users")

class Entry(Base):
    __tablename__ = "entries"
    id = Column(Integer, primary_key=True)
    couple_id = Column(Integer, ForeignKey("couples.id"), nullable=False)

    day = Column(String(10), index=True, nullable=False)  # "YYYY-MM-DD"
    author = Column(String(8), nullable=False)  # "me" ou "par"

    mood = Column(String(120), default="")
    moment_special = Column(Text, default="")
    love_action = Column(Text, default="")
    character = Column(String(200), default="")
    music = Column(String(200), default="")
    updated_at = Column(String(32), default="")

    couple = relationship("Couple", back_populates="entries")

    __table_args__ = (
        UniqueConstraint("couple_id", "day", "author", name="uq_entry_side"),
    )
