import feedparser
from datetime import datetime
from database import SessionLocal
from models import Source, Article


def parse_published(entry) -> datetime | None:
    # feedparser 可能给 published_parsed（time.struct_time）
    if getattr(entry, "published_parsed", None):
        t = entry.published_parsed
        return datetime(t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec)
    return None


def main(limit: int = 50):
    db = SessionLocal()
    try:
        sources = db.query(Source).all()
        if not sources:
            print(" No sources found in DB. Please insert sources first.")
            return

        total_inserted = 0

        for source in sources:
            feed = feedparser.parse(source.url)

            if getattr(feed, "bozo", False):
                print(f" RSS parse error for {source.name}: {feed.bozo_exception}")
                continue

            inserted = 0

            for entry in feed.entries[:limit]:
                title = getattr(entry, "title", "").strip()
                url = getattr(entry, "link", "").strip()
                summary = getattr(entry, "summary", "").strip()
                published_at = parse_published(entry)

                if not url:
                    continue

                # 去重：同链接不重复入库
                exists = db.query(Article).filter(Article.url == url).first()
                if exists:
                    continue

                a = Article(
                    source_id=source.id,
                    title=title[:500],
                    url=url[:1000],
                    summary=summary[:2000],
                    published_at=published_at,
                )
                db.add(a)
                inserted += 1

            # 每个 source 单独提交：一个源坏了不会拖累全部
            db.commit()
            total_inserted += inserted
            print(f" Inserted {inserted} new articles from {source.name}.")

        print(f" Done. Total inserted = {total_inserted}.")

    finally:
        db.close()


if __name__ == "__main__":
    main()

