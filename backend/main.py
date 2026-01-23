from fastapi import FastAPI

app = FastAPI()
print("[boot] main.py loaded")

from app.api.events import router as events_router
app.include_router(events_router, prefix="/api")
print("[boot] events router included")


@app.get("/")
def root():
    return {"message": "NewsToday API is running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/sources")
def list_sources():
    # 先用假数据占位：之后会从数据库读
    return [
        {"id": 1, "name": "BBC", "url": "https://www.bbc.co.uk"},
        {"id": 2, "name": "Reuters", "url": "https://www.reuters.com"},
        {"id": 3, "name": "AP", "url": "https://apnews.com"},
    ]
from fastapi import FastAPI
from database import SessionLocal
from models import Source

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/sources")
def list_sources():
    db = SessionLocal()
    try:
        rows = db.query(Source).order_by(Source.id.asc()).all()
        return [{"id": r.id, "name": r.name, "url": r.url} for r in rows]
    finally:
        db.close()
from models import Article

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
from models import Event, EventArticle

@app.get("/events")
def list_events():
    db = SessionLocal()
    events = db.query(Event).order_by(Event.id.desc()).all()

    result = []
    for e in events:
        count = db.query(EventArticle).filter(EventArticle.event_id == e.id).count()
        result.append({
            "id": e.id,
            "title": e.title,
            "article_count": count
        })

    return result

