from sqlalchemy.orm import Session
from database import SessionLocal
from models import Event, Article, EventArticle

def main():
    db: Session = SessionLocal()

    # 1) 新建一个事件
    event = Event(title="UK rail infrastructure reform (manual seed)")
    db.add(event)
    db.commit()
    db.refresh(event)

    # 2) 取最近的 3 篇文章，绑定到这个事件
    recent_articles = db.query(Article).order_by(Article.id.desc()).limit(3).all()

    for a in recent_articles:
        link = EventArticle(event_id=event.id, article_id=a.id)
        db.add(link)

    db.commit()

    print(f"Created event id={event.id}, linked {len(recent_articles)} articles.")

if __name__ == "__main__":
    main()
