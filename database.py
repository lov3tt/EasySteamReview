from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

DATABASE_URL = "sqlite:///./easysteamreview.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Game(Base):
    __tablename__ = "games"
    id            = Column(Integer, primary_key=True, index=True)
    app_id        = Column(String, unique=True, index=True)
    name          = Column(String)
    price         = Column(String)
    genre         = Column(String)
    rating        = Column(Float)
    release_date  = Column(String)
    thumbnail_url = Column(String)
    developer     = Column(String)
    publisher     = Column(String)
    description   = Column(Text)
    metacritic    = Column(Integer)
    total_reviews    = Column(Integer, default=0)
    positive_reviews = Column(Integer, default=0)
    negative_reviews = Column(Integer, default=0)
    tags          = Column(JSON)
    last_updated  = Column(DateTime, default=datetime.utcnow)

class Review(Base):
    __tablename__    = "reviews"
    id               = Column(Integer, primary_key=True, index=True)
    game_id          = Column(String, index=True)
    review_text      = Column(Text)
    sentiment_score  = Column(Float)
    is_positive      = Column(Boolean)
    timestamp        = Column(DateTime)
    hours_played     = Column(Float)
    trigger_keywords = Column(JSON)
    author_id        = Column(String)
    votes_up         = Column(Integer, default=0)

class Analytics(Base):
    __tablename__   = "analytics"
    id              = Column(Integer, primary_key=True, index=True)
    game_id         = Column(String, index=True)
    date            = Column(DateTime)
    positive_count  = Column(Integer, default=0)
    negative_count  = Column(Integer, default=0)
    flagged_count   = Column(Integer, default=0)
    avg_sentiment   = Column(Float)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    Base.metadata.create_all(bind=engine)
