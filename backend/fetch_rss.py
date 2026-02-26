import json
import feedparser
from datetime import datetime
from database import SessionLocal
from models import Source, Article
from sqlalchemy.dialects.postgresql import insert

SKIP_SOURCE_NAMES = {"CBC World"}
SKIP_SOURCE_URLS = {"https://rss.cbc.ca/lineup/world.xml"}


def parse_published(entry) -> datetime | None:
    # feedparser may expose published_parsed (time.struct_time)
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
        total_duplicates = 0
        sources_total = len(sources)
        sources_ok = 0
        sources_failed = 0
        failed_sources = []

        for source in sources:
            if source.name in SKIP_SOURCE_NAMES or source.url in SKIP_SOURCE_URLS:
                print(f" Skip source: {source.name} ({source.url})")
                continue
            try:
                feed = feedparser.parse(source.url)

                if getattr(feed, "bozo", False):
                    err_obj = getattr(feed, "bozo_exception", None)
                    err = str(err_obj or "unknown error")
                    status_code = getattr(feed, "status", None)
                    print(f" RSS parse error for {source.name}: {err}")
                    sources_failed += 1
                    failed_sources.append(
                        {
                            "source_id": source.id,
                            "name": source.name,
                            "url": source.url,
                            "reason": "bozo",
                            "status_code": status_code,
                            "exception_type": type(err_obj).__name__ if err_obj else None,
                            "error_short": err[:120],
                        }
                    )
                    continue

                inserted = 0
                rows = []
                seen_urls = set()

                for entry in feed.entries[:limit]:
                    title = getattr(entry, "title", "").strip()
                    url = getattr(entry, "link", "").strip()
                    summary = getattr(entry, "summary", "").strip()
                    published_at = parse_published(entry)

                    if not url:
                        continue

                    if url in seen_urls:
                        continue
                    seen_urls.add(url)

                    rows.append(
                        {
                            "source_id": source.id,
                            "title": title[:500],
                            "url": url[:1000],
                            "summary": summary[:2000],
                            "published_at": published_at,
                        }
                    )

                if rows:
                    stmt = insert(Article).values(rows)
                    stmt = stmt.on_conflict_do_nothing(index_elements=["url"]).returning(Article.id)
                    inserted = len(db.execute(stmt).fetchall())
                    inserted = max(0, int(inserted))
                    total_duplicates += max(0, len(rows) - inserted)

                # commit per source to isolate failures
                db.commit()
                total_inserted += inserted
                sources_ok += 1
                print(f" Inserted {inserted} new articles from {source.name}.")
            except Exception as e:
                db.rollback()
                sources_failed += 1
                err = str(e)
                failed_sources.append(
                    {
                        "source_id": source.id,
                        "name": source.name,
                        "url": source.url,
                        "reason": "exception",
                        "status_code": None,
                        "exception_type": type(e).__name__,
                        "error_short": err[:120],
                    }
                )
                print(f" RSS fetch error for {source.name}: {err}")

        top_failed_sources = failed_sources[:5]
        print(" Health Summary:")
        print(f"  sources_total={sources_total} sources_ok={sources_ok} sources_failed={sources_failed}")
        print(f"  articles_inserted={total_inserted} articles_duplicate={total_duplicates}")
        print(f"  top_failed_sources={top_failed_sources}")
        print(f" Done. Total inserted = {total_inserted}.")
        summary = {
            "sources_total": sources_total,
            "sources_ok": sources_ok,
            "sources_failed": sources_failed,
            "articles_inserted": total_inserted,
            "articles_duplicate": total_duplicates,
            "failed_sources": failed_sources,
        }
        print(json.dumps(summary, ensure_ascii=False))

    finally:
        db.close()


if __name__ == "__main__":
    main()
