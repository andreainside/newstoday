from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Response
from sqlalchemy import func

_BACKEND_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BACKEND_DIR.parent
load_dotenv(_REPO_ROOT / ".env")
load_dotenv(_BACKEND_DIR / ".env")

from app.api.events import router as events_router
from database import SessionLocal
from models import Article, Event, EventArticle, Source


app = FastAPI()
print("[boot] main.py loaded")

app.include_router(events_router, prefix="/api")
print("[boot] events router included")


@app.get("/")
def root():
    return {"message": "NewsToday API is running"}


@app.api_route("/health", methods=["HEAD", "GET"])
def health():
    return Response(status_code=200)


@app.get("/sources")
def list_sources():
    db = SessionLocal()
    try:
        rows = db.query(Source).order_by(Source.id.asc()).all()
        return [{"id": r.id, "name": r.name, "url": r.url} for r in rows]
    finally:
        db.close()


@app.get("/articles")
def list_articles(limit: int = 20):
    db = SessionLocal()
    try:
        rows = db.query(Article).order_by(Article.id.desc()).limit(limit).all()
        return [
            {
                "id": r.id,
                "source_id": r.source_id,
                "title": r.title,
                "url": r.url,
                "published_at": r.published_at.isoformat() if r.published_at else None,
            }
            for r in rows
        ]
    finally:
        db.close()


@app.get("/events")
def list_events():
    db = SessionLocal()
    try:
        rows = (
            db.query(
                Event.id,
                Event.title,
                func.count(EventArticle.article_id).label("article_count"),
            )
            .outerjoin(EventArticle, EventArticle.event_id == Event.id)
            .group_by(Event.id, Event.title)
            .order_by(Event.id.desc())
            .all()
        )
        return [
            {"id": r.id, "title": r.title, "article_count": int(r.article_count)}
            for r in rows
        ]
    finally:
        db.close()
