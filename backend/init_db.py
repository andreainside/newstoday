from database import engine
from models import Base  # 关键：Base 来自 models

def init_db():
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    init_db()
    print("Tables created (if not already).")