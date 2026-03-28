import asyncio
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import init_db, get_db, Game, Review, SessionLocal
import engine as eng

# ---Cor Proxy---

import os
from dotenv import load_dotenv # pip install python-dotenv
from fastapi.middleware.cors import CORSMiddleware
# ... your existing imports (asyncio, datetime, etc.)

# Load environment: defaults to '.env.local'
app_mode = os.getenv("APP_MODE", "local")
load_dotenv(f".env.{app_mode}")

app = FastAPI()

# Configure CORS so your Proxy or Local Frontend can talk to the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("CORS_ORIGIN", "*")], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ---End Cor Proxy---

# --- Lifespan Management ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs on startup
    init_db()
    yield
    # Runs on shutdown (add cleanup here if needed)

app = FastAPI(title="EasySteamReview Analytics", lifespan=lifespan)

BASE = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE / "templates"))

# In-memory tracking for ETL jobs
_etl_running: dict[str, bool] = {}
_etl_results: dict[str, dict] = {}

# ── Pages ──────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def homepage(request: Request):
    # FIXED: request must be passed as a keyword or the first argument
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/dashboard/{app_id}", response_class=HTMLResponse)
async def dashboard(request: Request, app_id: str):
    return templates.TemplateResponse(
        request=request, 
        name="dashboard.html", 
        context={"app_id": app_id}
    )

# ── Games API ──────────────────────────────────────────────────────────────────

@app.get("/api/games/top100")
async def top100(db: Session = Depends(get_db)):
    cached = db.query(Game).limit(100).all()
    if len(cached) >= 80:
        return [_gd(g) for g in cached]
    
    games = await eng.fetch_steamspy_top100()
    for g in games:
        if not db.query(Game).filter(Game.app_id == g["app_id"]).first():
            try:
                safe = {k: v for k, v in g.items() if hasattr(Game, k)}
                db.add(Game(**safe))
                db.commit()
            except Exception:
                db.rollback()
    return games

@app.get("/api/games/search")
async def search_games(q: str = ""):
    if not q or len(q.strip()) < 2:
        return []
    return await eng.search_games(q.strip())

@app.get("/api/games/{app_id}")
async def game_detail(app_id: str, db: Session = Depends(get_db)):
    g = db.query(Game).filter(Game.app_id == str(app_id)).first()
    if g and g.name:
        return _gd(g)
    
    import httpx
    async with httpx.AsyncClient() as client:
        d = await eng.fetch_game_details(str(app_id), client)
    if not d or not d.get("name"):
        raise HTTPException(404, "Game not found")
    return d

# ── ETL API ────────────────────────────────────────────────────────────────────

@app.post("/api/etl/{app_id}")
async def start_etl(app_id: str, background_tasks: BackgroundTasks):
    app_id = str(app_id)
    if _etl_running.get(app_id):
        return {"status": "already_running", "app_id": app_id}
    
    _etl_running[app_id] = True
    _etl_results.pop(app_id, None)
    background_tasks.add_task(_etl_task, app_id)
    return {"status": "started", "app_id": app_id}

@app.get("/api/etl/{app_id}/status")
async def etl_status(app_id: str, db: Session = Depends(get_db)):
    app_id = str(app_id)
    if _etl_running.get(app_id):
        return {"status": "running"}
    
    result = _etl_results.get(app_id)
    if result:
        if result.get("error"):
            return {"status": "error", "message": result["error"]}
        return {"status": "complete", **result}

    rev_count = db.query(Review).filter(Review.game_id == app_id).count()
    g = db.query(Game).filter(Game.app_id == app_id).first()
    if rev_count > 0 and g:
        return {
            "status": "complete", 
            "total": rev_count, 
            "game": g.name,
            "positive": g.positive_reviews or 0, 
            "negative": g.negative_reviews or 0
        }
    return {"status": "idle"}

async def _etl_task(app_id: str):
    db = SessionLocal()
    try:
        result = await eng.run_etl(app_id, db)
        _etl_results[app_id] = result
    except Exception as e:
        _etl_results[app_id] = {"error": str(e)}
    finally:
        _etl_running[app_id] = False
        db.close()

# ── Reviews API ────────────────────────────────────────────────────────────────

@app.get("/api/reviews/{app_id}")
async def get_reviews(app_id: str, filter: str = "all", sort: str = "recent",
                      page: int = 1, db: Session = Depends(get_db)):
    q = db.query(Review).filter(Review.game_id == str(app_id))
    
    if filter == "positive":
        q = q.filter(Review.is_positive == True)
    elif filter == "negative":
        q = q.filter(Review.is_positive == False)
    elif filter == "flagged":
        q = q.filter(
            Review.trigger_keywords != None,
            Review.trigger_keywords != "[]",
            Review.trigger_keywords != "",
        )

    sort_options = {
        "helpful": Review.votes_up.desc(),
        "hours": Review.hours_played.desc(),
        "recent": Review.timestamp.desc()
    }
    q = q.order_by(sort_options.get(sort, Review.timestamp.desc()))

    total = q.count()
    per_page = 30
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    
    return {
        "total": total,
        "page": page,
        "pages": max(1, (total + per_page - 1) // per_page),
        "reviews": [_rd(r) for r in items],
    }

# ── Analytics API ──────────────────────────────────────────────────────────────

@app.get("/api/analytics/{app_id}")
async def get_analytics(app_id: str, db: Session = Depends(get_db)):
    app_id = str(app_id)
    reviews = db.query(Review).filter(Review.game_id == app_id).all()
    game = db.query(Game).filter(Game.app_id == app_id).first()

    if not reviews:
        return {"error": "no_data", "game": _gd(game) if game else {}}

    rev_list = [_rd(r) for r in reviews]
    pos = sum(1 for r in reviews if r.is_positive)
    neg = len(reviews) - pos
    flagged = sum(1 for r in reviews if r.trigger_keywords and r.trigger_keywords not in ([], "[]", ""))
    
    avg_sent = round(sum(float(r.sentiment_score or 0) for r in reviews) / len(reviews), 4)
    pos_pct = round(pos / len(reviews) * 100, 1)

    return {
        "summary": {
            "total": len(reviews),
            "positive": pos,
            "negative": neg,
            "flagged": flagged,
            "avg_sentiment": avg_sent,
            "positive_pct": pos_pct,
            "negative_pct": round(100 - pos_pct, 1),
        },
        "sentiment_trend": eng.get_sentiment_trend(rev_list),
        "hours_distribution": eng.get_hours_distribution(rev_list),
        "keyword_stats": eng.get_keyword_stats(rev_list),
        "heatmap": eng.get_heatmap_data(rev_list),
        "scatter": eng.get_scatter_data(rev_list),
        "game": _gd(game) if game else {},
    }

# ── Helpers ────────────────────────────────────────────────────────────────────

def _gd(g: Game) -> dict:
    if g is None: return {}
    return {
        "app_id": g.app_id, "name": g.name, "price": g.price, "genre": g.genre,
        "rating": g.rating, "release_date": g.release_date, "thumbnail_url": g.thumbnail_url,
        "developer": g.developer, "publisher": g.publisher, "description": g.description,
        "metacritic": g.metacritic, "total_reviews": g.total_reviews or 0,
        "positive_reviews": g.positive_reviews or 0, "negative_reviews": g.negative_reviews or 0,
        "tags": g.tags or [],
    }

def _rd(r: Review) -> dict:
    kw = r.trigger_keywords
    if isinstance(kw, str):
        import json as _j
        try: kw = _j.loads(kw)
        except: kw = []
    return {
        "id": r.id, "game_id": r.game_id, "review_text": r.review_text or "",
        "sentiment_score": float(r.sentiment_score or 0), "is_positive": bool(r.is_positive),
        "timestamp": r.timestamp.isoformat() if r.timestamp else None,
        "hours_played": float(r.hours_played or 0), "trigger_keywords": kw or [],
        "votes_up": int(r.votes_up or 0),
    }
#Original
#if __name__ == "__main__":
 #   import uvicorn
  #  uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

#--- Cor Proxy Entry Point ---
if __name__ == "__main__":
    import uvicorn
    
    # Get settings from your .env file
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", 8000))
    reload_mode = (app_mode == "local") # Auto-reload only when local

    print(f"--- Starting in {app_mode} mode on {host}:{port} ---")
    
    uvicorn.run(
        "main:app", # Assumes your file is named main.py
        host=host, 
        port=port, 
        reload=reload_mode
    )
