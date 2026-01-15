from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime

from database import Base


# =========================
# 表 1：events（事件表）
# =========================
class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )

    # 一个事件 → 多篇文章
    articles = relationship("EventArticle", back_populates="event")


# =========================
# 表 2：event_articles（事件-文章 关联表）
# =========================
class EventArticle(Base):
    __tablename__ = "event_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id"), nullable=False
    )
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id"), nullable=False
    )

    event = relationship("Event", back_populates="articles")

    # 同一篇文章不能重复绑定同一个事件
    __table_args__ = (
        UniqueConstraint(
            "event_id", "article_id",
            name="uq_event_article"
        ),
    )
