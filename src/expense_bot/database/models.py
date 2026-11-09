from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    expenses: Mapped[list["Expense"]] = relationship(back_populates="category")

    __table_args__ = (
        # Accelerates checking if a category exists for a user during dynamic onboarding
        Index("ix_categories_user_name", "user_id", "name"),
    )


class LLMCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    task: Mapped[str] = mapped_column(String(32), nullable=False)  # extraction, vision, asr, intent
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="success", nullable=False)  # success, failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    expenses: Mapped[list["Expense"]] = relationship(back_populates="llm_call")

    __table_args__ = (
        # Speeds up analytics on recent LLM usage, token trends, and latency
        Index("ix_llm_calls_user_created_at", "user_id", "created_at"),
    )


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    user_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)  # Stored directly in Rupees
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    merchant: Mapped[str | None] = mapped_column(String(128), nullable=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False, index=True)
    llm_call_id: Mapped[int | None] = mapped_column(ForeignKey("llm_calls.id"), nullable=True, index=True)
    note: Mapped[str | None] = mapped_column(String(256), nullable=True)
    spent_on: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="text", nullable=False)  # text, voice, image, manual
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    category: Mapped[Category] = relationship(back_populates="expenses")
    llm_call: Mapped[LLMCall | None] = relationship(back_populates="expenses")

    __table_args__ = (
        # Core query path: filtering by user and date ranges (/today, /month, custom timeframes)
        Index("ix_expenses_user_spent_on", "user_id", "spent_on"),
        # Speeds up querying recent insertions or logs
        Index("ix_expenses_user_created_at", "user_id", "created_at"),
    )