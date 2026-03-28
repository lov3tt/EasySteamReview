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

# --- Lifespan Management ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="EasySteamReview Analytics", lifespan=lifespan)

# Configure CORS so your Proxy or Local Frontend can talk to the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("CORS_ORIGIN", "*")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ---End Cor Proxy---

BASE = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE / "templates"))


def _norm_app_id(app_id: str | int | None) -> str:
    """Steam app id as trimmed string (search vs grid must match DB keys)."""
    if app_id is None:
        return ""
    return str(app_id).strip()


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
        context={"app_id": _norm_app_id(app_id)},
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
    app_id = _norm_app_id(app_id)
    g = db.query(Game).filter(Game.app_id == app_id).first()
    if g and g.name:
        gd = dict(_gd(g))
        await eng.merge_lifetime_stats_if_missing(app_id, gd)
        return gd

    import httpx
    async with httpx.AsyncClient() as client:
        d = await eng.fetch_game_details(app_id, client)
    if not d or not d.get("name"):
        raise HTTPException(404, "Game not found")
    await eng.merge_lifetime_stats_if_missing(app_id, d)
    return d

# ── ETL API ────────────────────────────────────────────────────────────────────

@app.post("/api/etl/{app_id}")
async def start_etl(app_id: str, background_tasks: BackgroundTasks):
    app_id = _norm_app_id(app_id)
    if _etl_running.get(app_id):
        return {"status": "already_running", "app_id": app_id}
    
    _etl_running[app_id] = True
    _etl_results.pop(app_id, None)
    background_tasks.add_task(_etl_task, app_id)
    return {"status": "started", "app_id": app_id}

@app.get("/api/etl/{app_id}/status")
async def etl_status(app_id: str, db: Session = Depends(get_db)):
    app_id = _norm_app_id(app_id)
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
    app_id = _norm_app_id(app_id)
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
    app_id = _norm_app_id(app_id)
    q = db.query(Review).filter(Review.game_id == app_id)
    
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

def _lifetime_payload(gd: dict) -> dict:
    if not gd:
        return {}
    lt_total = int(gd.get("total_reviews") or 0)
    lt_pos = int(gd.get("positive_reviews") or 0)
    lt_neg = int(gd.get("negative_reviews") or 0)
    if lt_total <= 0 and lt_pos + lt_neg > 0:
        lt_total = lt_pos + lt_neg

    life_rating = float(gd.get("rating") or 0)
    overall_pos_pct = overall_neg_pct = None
    rating_pct_out = None

    if lt_total > 0:
        overall_pos_pct = round(lt_pos / lt_total * 100, 1)
        overall_neg_pct = round(lt_neg / lt_total * 100, 1)
        if life_rating <= 0:
            life_rating = overall_pos_pct
        rating_pct_out = round(life_rating, 1)
    elif life_rating > 0:
        overall_pos_pct = round(life_rating, 1)
        overall_neg_pct = round(100 - life_rating, 1)
        rating_pct_out = round(life_rating, 1)

    return {
        "total_reviews": lt_total,
        "positive_reviews": lt_pos,
        "negative_reviews": lt_neg,
        "rating_pct": rating_pct_out,
        "overall_positive_pct": overall_pos_pct,
        "overall_negative_pct": overall_neg_pct,
    }


@app.get("/api/analytics/{app_id}")
async def get_analytics(app_id: str, db: Session = Depends(get_db)):
    app_id = _norm_app_id(app_id)
    reviews = db.query(Review).filter(Review.game_id == app_id).all()
    game = db.query(Game).filter(Game.app_id == app_id).first()

    if not reviews:
        gd: dict = {}
        if game and game.name:
            gd = dict(_gd(game))
            await eng.merge_lifetime_stats_if_missing(app_id, gd)
        else:
            import httpx
            async with httpx.AsyncClient() as client:
                fd = await eng.fetch_game_details(app_id, client)
            if fd:
                gd = dict(fd)
                await eng.merge_lifetime_stats_if_missing(app_id, gd)
        return {
            "error": "no_data",
            "game": gd,
            "lifetime": _lifetime_payload(gd),
            "keyword_stats": {},
        }

    rev_list = [_rd(r) for r in reviews]
    gd = dict(_gd(game)) if game else {}

    if gd:
        changed = await eng.maybe_refresh_lifetime_from_steamspy(app_id, gd, len(reviews))
        if changed and game:
            game.total_reviews = gd["total_reviews"]
            game.positive_reviews = gd["positive_reviews"]
            game.negative_reviews = gd["negative_reviews"]
            game.rating = gd["rating"]
            db.commit()

    lifetime_out = _lifetime_payload(gd)
    life_rating = float(lifetime_out.get("rating_pct") or 0)
    if life_rating <= 0 and lifetime_out.get("overall_positive_pct") is not None:
        life_rating = float(lifetime_out["overall_positive_pct"])

    chart_end = datetime.utcnow().date()
    rev_chart = eng.filter_reviews_in_utc_calendar_days(
        rev_list, 30, end_date=chart_end
    )

    pos = sum(1 for r in reviews if r.is_positive)
    neg = len(reviews) - pos
    flagged = sum(1 for r in reviews if r.trigger_keywords and r.trigger_keywords not in ([], "[]", ""))

    avg_sent = round(sum(float(r.sentiment_score or 0) for r in reviews) / len(reviews), 4)
    pos_pct = round(pos / len(reviews) * 100, 1)

    sample_rating = pos_pct
    rating_delta = (
        round(sample_rating - life_rating, 1) if (life_rating and life_rating > 0) else None
    )

    return {
        "meta": {
            "window_days": 30,
            "max_reviews": 800,
            "reviews_used": len(reviews),
            "chart_window_days": 30,
            "chart_reviews_used": len(rev_chart),
            "description": "Charts use only reviews from the last 30 calendar days (UTC). The dashboard sample is up to 800 recent English reviews; Steam store cards use all-time totals.",
        },
        "lifetime": lifetime_out,
        "summary": {
            "total": len(reviews),
            "positive": pos,
            "negative": neg,
            "flagged": flagged,
            "avg_sentiment": avg_sent,
            "positive_pct": pos_pct,
            "negative_pct": round(100 - pos_pct, 1),
            "rating_pct": round(sample_rating, 1),
        },
        "comparison": {
            "sample_rating_pct": round(sample_rating, 1),
            "lifetime_rating_pct": round(life_rating, 1) if life_rating else None,
            "rating_delta_pct": rating_delta,
        },
        "sentiment_trend": eng.get_sentiment_trend(rev_chart, 30, end_date=chart_end),
        "hours_distribution": eng.get_hours_distribution(rev_chart),
        "keyword_stats": eng.get_keyword_stats(rev_chart),
        "scatter": eng.get_scatter_data(rev_chart),
        "game": gd,
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
