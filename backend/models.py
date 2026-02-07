from sqlalchemy import Column, Integer, String
from database import Base

class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    country = Column(String, nullable=True)
    region = Column(String, nullable=True)
    language = Column(String, nullable=True)
    ownership_group = Column(String, nullable=True)

from sqlalchemy import String, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime

class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # 来源（外键，指向 sources.id）
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    source = relationship("Source")

    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(1000))
    summary: Mapped[str] = mapped_column(String(2000), default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("url", name="uq_articles_url"),
    )

from event_models import Event, EventArticle  # 确保被加载、被注册


