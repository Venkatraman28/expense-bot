from sqlalchemy import Column, Integer, Numeric, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import relationship
from expense_bot.database import Base


class Budget(Base):
    __tablename__ = "budgets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=True)
    monthly_limit = Column(Numeric(12, 2), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    category = relationship("Category", lazy="joined")

    __table_args__ = (
        UniqueConstraint("user_id", "category_id", name="uq_user_category_budget"),
    )