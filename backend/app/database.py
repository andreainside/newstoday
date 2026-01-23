# backend/app/database.py

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 1) 连接串：优先读环境变量；没有就用本地 docker 默认
# 注意：这里用 psycopg（SQLAlchemy 的 postgresql+psycopg 方言）
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/newstoday_fresh",
)

# 2) Engine
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # 防止连接假死
)

# 3) Session factory
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)

# 4) Declarative Base
Base = declarative_base()
