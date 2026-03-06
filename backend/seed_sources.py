from database import SessionLocal
from models import Source


def main():
    db = SessionLocal()
    try:
        sources = [
            {"name": "BBC News", "url": "http://feeds.bbci.co.uk/news/rss.xml"},
            {"name": "BBC World", "url": "http://feeds.bbci.co.uk/news/world/rss.xml"},
            {"name": "CNN Top", "url": "http://rss.cnn.com/rss/edition.rss"},
            {"name": "CNN World", "url": "http://rss.cnn.com/rss/edition_world.rss"},
            {"name": "NPR News", "url": "https://feeds.npr.org/1001/rss.xml"},
            {"name": "NYTimes Home", "url": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"},
            {"name": "NYTimes World", "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"},
            {"name": "NYTimes US", "url": "https://rss.nytimes.com/services/xml/rss/nyt/US.xml"},
            {"name": "NYTimes Business", "url": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml"},
            {"name": "NYTimes Technology", "url": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml"},
            {"name": "The Guardian World", "url": "https://www.theguardian.com/world/rss"},
            {"name": "The Guardian US", "url": "https://www.theguardian.com/us-news/rss"},
            {"name": "Al Jazeera", "url": "https://www.aljazeera.com/xml/rss/all.xml"},
            {"name": "Deutsche Welle", "url": "https://rss.dw.com/rdf/rss-en-all"},
            {"name": "Sky News World", "url": "https://feeds.skynews.com/feeds/rss/world.xml"},
            {"name": "ABC News Top", "url": "https://abcnews.go.com/abcnews/topstories"},
            {"name": "NBC News Top", "url": "https://feeds.nbcnews.com/nbcnews/public/news"},
            {"name": "Fox News Latest", "url": "https://feeds.foxnews.com/foxnews/latest"},
            {"name": "NYTimes Politics", "url": "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml"},
            {"name": "Washington Post Politics", "url": "https://feeds.washingtonpost.com/rss/politics"},
            {"name": "CNN US", "url": "http://rss.cnn.com/rss/cnn_us.rss"},
            {"name": "DW World (EN)", "url": "https://rss.dw.com/rdf/rss-en-world"},
            {"name": "France24 EN", "url": "https://www.france24.com/en/rss"},
            {"name": "Japan Times", "url": "https://www.japantimes.co.jp/feed/"},
            {"name": "PBS NewsHour Headlines", "url": "https://www.pbs.org/newshour/feeds/rss/headlines"},
            {"name": "Vox", "url": "https://www.vox.com/rss/index.xml"},
            {"name": "The Conversation Global Atom", "url": "https://theconversation.com/global/articles.atom"},
            {"name": "WSJ World News", "url": "https://feeds.a.dj.com/rss/RSSWorldNews.xml"},
            {"name": "WSJ US Business", "url": "https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml"},
            {"name": "CNBC Top News", "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html"},
            {"name": "CNBC World News", "url": "https://www.cnbc.com/id/100727362/device/rss/rss.html"},
            {"name": "NBC News World", "url": "https://feeds.nbcnews.com/nbcnews/public/world"},
            {"name": "CBS News World", "url": "https://www.cbsnews.com/latest/rss/world"},
            {"name": "ABC News World", "url": "https://abcnews.go.com/abcnews/internationalheadlines"},
            {"name": "Korea Times", "url": "https://www.koreatimes.co.kr/www/rss/rss.xml"},
            {"name": "Channel NewsAsia", "url": "https://www.channelnewsasia.com/rssfeeds/8396082"},
            {"name": "SCMP Top News", "url": "https://www.scmp.com/rss/91/feed"},
            {"name": "Al Jazeera English", "url": "https://www.aljazeera.com/xml/rss/all.xml"},
            {"name": "The Straits Times", "url": "https://www.straitstimes.com/news/world/rss.xml"},
            {"name": "Hong Kong Free Press", "url": "https://hongkongfp.com/feed/"},
            {"name": "BBC Chinese", "url": "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml"},
            {"name": "FT Chinese", "url": "https://www.ftchinese.com/rss/feed"},
        ]

        inserted = 0
        for s in sources:
            exists = db.query(Source).filter(Source.url == s["url"]).first()
            if exists:
                print(" Source already exists:", exists.id, exists.name, exists.url)
                continue
            row = Source(name=s["name"], url=s["url"])
            db.add(row)
            db.commit()
            db.refresh(row)
            inserted += 1
            print("Inserted:", row.id, row.name, row.url)

        print(f" Done. Inserted {inserted} new sources.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
