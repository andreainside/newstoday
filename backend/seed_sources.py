from database import SessionLocal
from models import Source

def main():
    db = SessionLocal()
    try:
        # 先查一下是否已经有这条（避免重复插入）
        exists = db.query(Source).filter(Source.url == "https://www.bbc.com").first()
        if exists:
            print(" Source already exists:", exists.id, exists.name, exists.url)
            return

        s = Source(name="BBC", url="https://www.bbc.com")
        db.add(s)
        db.commit()
        db.refresh(s)  # 让 s 拿到数据库生成的 id
        print("Inserted:", s.id, s.name, s.url)
    finally:
        db.close()

if __name__ == "__main__":
    main()
