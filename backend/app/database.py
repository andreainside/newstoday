# backend/app/database.py

import os
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker, declarative_base

# 1) 连接串：优先读环境变量；没有就用本地 docker 默认
# 注意：这里用 psycopg（SQLAlchemy 的 postgresql+psycopg 方言）
_RAW_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/newstoday",
)

# 1.1) 强制使用 psycopg(v3) 驱动。
# psycopg2 连接 Supabase 连接池(Supavisor / PgBouncer) 时会抛
# "server didn't return client encoding"，psycopg3 不会。
# 不管 DATABASE_URL 写的是 postgresql:// 还是 postgresql+psycopg2://，
# 这里都统一改写成 postgresql+psycopg。
_url = make_url(_RAW_DATABASE_URL)
if _url.drivername in ("postgresql", "postgres", "postgresql+psycopg2"):
    _url = _url.set(drivername="postgresql+psycopg")
DATABASE_URL = _url

# 2) Engine
# connect_args: 关闭 psycopg3 自动 prepared statements，
# 兼容 Supabase transaction 模式连接池(6543)。
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # 防止连接假死
    connect_args={"prepare_threshold": None},
)

# 3) Session factory
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)

# 4) Declarative Base
Base = declarative_base()
