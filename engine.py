import httpx
import asyncio
import re
import json
from datetime import datetime, timedelta
from textblob import TextBlob
from collections import Counter, defaultdict
import nltk

# Download NLTK data silently
for pkg in ["vader_lexicon", "punkt", "stopwords", "punkt_tab"]:
    try:
        nltk.download(pkg, quiet=True)
    except Exception:
        pass

try:
    from nltk.sentiment.vader import SentimentIntensityAnalyzer
    VADER = SentimentIntensityAnalyzer()
    USE_VADER = True
except Exception:
    USE_VADER = False

TRIGGER_KEYWORDS = [
    "cheating", "cheat", "hacked", "hack", "scam", "unfair",
    "buggy", "bug", "crash", "broken", "pay-to-win", "p2w",
    "moderation", "ban", "toxic", "refund", "stolen", "fraud"
]

STEAM_STORE_URL   = "https://store.steampowered.com/api/appdetails"
STEAM_REVIEWS_URL = "https://store.steampowered.com/appreviews"
STEAMSPY_ALL_URL  = "https://steamspy.com/api.php?request=all"
STEAMSPY_TOP100_URL = "https://steamspy.com/api.php?request=top100in2weeks"
STEAMSPY_APP_URL  = "https://steamspy.com/api.php?request=appdetails&appid={}"
STEAM_SEARCH_URL  = "https://store.steampowered.com/api/storesearch"
CDN_HEADER        = "https://cdn.cloudflare.steamstatic.com/steam/apps/{}/header.jpg"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) EasySteamReview/2.0",
    "Accept-Language": "en-US,en;q=0.9",
}

# ── HTTP helper ───────────────────────────────────────────────────────────────

async def fetch_json(client: httpx.AsyncClient, url: str, params: dict = None) -> dict | None:
    try:
        r = await client.get(url, params=params, headers=HEADERS, timeout=20,
                             follow_redirects=True)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None

# ── SteamSpy top 100 ─────────────────────────────────────────────────────────

async def fetch_steamspy_top100() -> list:
    """Fetch top 100 most-played games from SteamSpy. Returns list of dicts."""
    async with httpx.AsyncClient() as client:
        data = await fetch_json(client, STEAMSPY_TOP100_URL)
        if not data:
            data = await fetch_json(client, STEAMSPY_ALL_URL)
        if not data:
            return []
        games = []
        for app_id, info in list(data.items())[:100]:
            name = info.get("name", "")
            if not name or name.lower() in ("", "unknown"):
                continue
            owners_raw = info.get("owners", "0 .. 0")
            positive   = int(info.get("positive", 0) or 0)
            negative   = int(info.get("negative", 0) or 0)
            total_rv   = positive + negative
            rating     = round(positive / total_rv * 100, 1) if total_rv > 0 else 0
            price_cents = int(info.get("price", 0) or 0)
            price_str   = f"${price_cents/100:.2f}" if price_cents > 0 else "Free"
            games.append({
                "app_id":       str(app_id),
                "name":         name,
                "developer":    info.get("developer", ""),
                "publisher":    info.get("publisher", ""),
                "genre":        info.get("genre", ""),
                "tags":         list((info.get("tags") or {}).keys())[:8],
                "price":        price_str,
                "rating":       rating,
                "thumbnail_url": CDN_HEADER.format(app_id),
                "release_date": info.get("release_date", ""),
                "description":  "",
                "metacritic":   None,
                "total_reviews":   total_rv,
                "positive_reviews": positive,
                "negative_reviews": negative,
            })
        return games[:100]

# ── Steam Store detail (single game) ─────────────────────────────────────────

async def fetch_game_details(app_id: str, client: httpx.AsyncClient) -> dict:
    data = await fetch_json(client, STEAM_STORE_URL, {"appids": app_id, "l": "english"})
    if not data or str(app_id) not in data:
        # Try SteamSpy fallback
        return await _steamspy_detail(app_id, client)
    info = data[str(app_id)]
    if not info.get("success"):
        return await _steamspy_detail(app_id, client)
    d = info.get("data", {})
    price_obj  = d.get("price_overview", {})
    metacritic = d.get("metacritic", {}).get("score") if d.get("metacritic") else None
    genres     = [g["description"] for g in d.get("genres", [])]
    tags       = [c["description"] for c in d.get("categories", [])]
    rv_summary = d.get("reviews", "")
    return {
        "app_id":       str(app_id),
        "name":         d.get("name", "Unknown"),
        "description":  re.sub(r"<[^>]+>", "", d.get("short_description", "")),
        "developer":    ", ".join(d.get("developers", [])),
        "publisher":    ", ".join(d.get("publishers", [])),
        "genre":        ", ".join(genres[:3]),
        "tags":         tags[:10],
        "release_date": d.get("release_date", {}).get("date", ""),
        "thumbnail_url": d.get("header_image", CDN_HEADER.format(app_id)),
        "price":        price_obj.get("final_formatted", "Free") if price_obj else "Free",
        "metacritic":   metacritic,
        "rating":       0.0,
        "total_reviews":    0,
        "positive_reviews": 0,
        "negative_reviews": 0,
    }

async def _steamspy_detail(app_id: str, client: httpx.AsyncClient) -> dict:
    data = await fetch_json(client, STEAMSPY_APP_URL.format(app_id))
    if not data or not data.get("name"):
        return {}
    positive = int(data.get("positive", 0) or 0)
    negative = int(data.get("negative", 0) or 0)
    total    = positive + negative
    rating   = round(positive / total * 100, 1) if total > 0 else 0
    price_cents = int(data.get("price", 0) or 0)
    return {
        "app_id":       str(app_id),
        "name":         data.get("name", "Unknown"),
        "description":  "",
        "developer":    data.get("developer", ""),
        "publisher":    data.get("publisher", ""),
        "genre":        data.get("genre", ""),
        "tags":         list((data.get("tags") or {}).keys())[:10],
        "release_date": data.get("release_date", ""),
        "thumbnail_url": CDN_HEADER.format(app_id),
        "price":        f"${price_cents/100:.2f}" if price_cents > 0 else "Free",
        "metacritic":   None,
        "rating":       rating,
        "total_reviews":    total,
        "positive_reviews": positive,
        "negative_reviews": negative,
    }

# ── Smart search ──────────────────────────────────────────────────────────────

async def search_games(query: str) -> list:
    """Search Steam Store then enrich results with SteamSpy data."""
    async with httpx.AsyncClient() as client:
        # Primary: Steam store search
        data = await fetch_json(client, STEAM_SEARCH_URL, {
            "term": query, "l": "english", "cc": "US", "category1": 998
        })
        results = []
        if data and data.get("items"):
            items = data["items"][:12]
            tasks = [fetch_game_details(str(item["id"]), client) for item in items]
            details = await asyncio.gather(*tasks, return_exceptions=True)
            for item, d in zip(items, details):
                if isinstance(d, Exception) or not d or not d.get("name"):
                    # minimal fallback from search result
                    results.append({
                        "app_id":       str(item["id"]),
                        "name":         item.get("name", "Unknown"),
                        "price":        item.get("price", {}).get("final_formatted", "Free") if item.get("price") else "Free",
                        "genre":        "",
                        "rating":       0,
                        "thumbnail_url": item.get("tiny_image", CDN_HEADER.format(item["id"])),
                        "developer":    "",
                        "publisher":    "",
                        "description":  "",
                        "metacritic":   None,
                        "tags":         [],
                        "release_date": "",
                        "total_reviews": 0,
                        "positive_reviews": 0,
                        "negative_reviews": 0,
                    })
                else:
                    results.append(d)
        return results

# ── Reviews ETL ───────────────────────────────────────────────────────────────

async def fetch_reviews(app_id: str, client: httpx.AsyncClient, days: int = 30) -> list:
    cutoff  = datetime.utcnow() - timedelta(days=days)
    reviews = []
    cursor  = "*"
    for _ in range(8):   # up to 800 reviews
        params = {
            "json": 1, "filter": "recent", "language": "english",
            "day_range": days, "review_type": "all", "purchase_type": "all",
            "num_per_page": 100, "cursor": cursor
        }
        data = await fetch_json(client, f"{STEAM_REVIEWS_URL}/{app_id}", params)
        if not data or not data.get("reviews"):
            break
        batch = data["reviews"]
        new_cursor = data.get("cursor", "*")
        for r in batch:
            if len(reviews) >= 800:
                break
            ts = datetime.utcfromtimestamp(r.get("timestamp_created", 0))
            if ts < cutoff:
                continue
            author = r.get("author", {})
            playtime = (author.get("playtime_at_review") or author.get("playtime_forever") or 0)
            reviews.append({
                "author_id":    author.get("steamid", ""),
                "review_text":  r.get("review", ""),
                "is_positive":  bool(r.get("voted_up", False)),
                "timestamp":    ts,
                "hours_played": round(playtime / 60, 2),
                "votes_up":     int(r.get("votes_up", 0)),
            })
        if len(reviews) >= 800:
            break
        if new_cursor == cursor or new_cursor == "*" or len(batch) < 100:
            break
        cursor = new_cursor
        await asyncio.sleep(0.25)
    return reviews

# ── NLP ───────────────────────────────────────────────────────────────────────

def analyze_sentiment(text: str) -> float:
    if not text or len(text.strip()) < 3:
        return 0.0
    if USE_VADER:
        return round(VADER.polarity_scores(text)["compound"], 4)
    try:
        return round(TextBlob(text).sentiment.polarity, 4)
    except Exception:
        return 0.0

def extract_trigger_keywords(text: str) -> list:
    tl = text.lower()
    return [kw for kw in TRIGGER_KEYWORDS if kw in tl]

# ── Review timestamp / 30-day window (for charts) ─────────────────────────────

def _review_ts_naive_utc(r: dict) -> datetime | None:
    ts = r.get("timestamp")
    if isinstance(ts, datetime):
        return ts
    if isinstance(ts, str) and len(ts) >= 10:
        s = ts.replace("Z", "").strip()
        if " " in s and "T" not in s:
            s = s.replace(" ", "T", 1)
        try:
            return datetime.fromisoformat(s[:19])
        except ValueError:
            return None
    return None


def filter_reviews_by_recent_days(reviews: list, days: int = 30) -> list:
    """Keep only reviews with timestamp within the last `days` (UTC, rolling window)."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    out = []
    for r in reviews:
        dt = _review_ts_naive_utc(r)
        if dt is not None and dt >= cutoff:
            out.append(r)
    return out


async def maybe_refresh_lifetime_from_steamspy(app_id: str, gd: dict, sample_count: int) -> bool:
    """
    If stored lifetime totals look missing or equal to the in-app sample (common ETL bug),
    replace with SteamSpy all-time totals. Returns True if gd was updated.
    """
    lt = int(gd.get("total_reviews") or 0)
    needs = (lt == 0) or (sample_count > 0 and lt == sample_count)
    if not needs:
        return False
    async with httpx.AsyncClient() as client:
        spy = await _steamspy_detail(app_id, client)
    if not spy:
        return False
    st = int(spy.get("total_reviews") or 0)
    if lt > 0 and st <= lt:
        return False
    gd["total_reviews"] = int(spy.get("total_reviews") or 0)
    gd["positive_reviews"] = int(spy.get("positive_reviews") or 0)
    gd["negative_reviews"] = int(spy.get("negative_reviews") or 0)
    gd["rating"] = float(spy.get("rating") or 0)
    return True


# ── Analytics builders ────────────────────────────────────────────────────────

def get_keyword_stats(reviews: list) -> dict:
    c = Counter()
    for r in reviews:
        for kw in (r.get("trigger_keywords") or []):
            c[kw] += 1
    return dict(c.most_common(15))

def get_sentiment_trend(reviews: list, days: int = 30) -> list:
    """One row per calendar day for the last `days` days (UTC), even if a day has no reviews."""
    end = datetime.utcnow().date()
    start = end - timedelta(days=days - 1)
    day_list: list[str] = []
    d = start
    while d <= end:
        day_list.append(d.isoformat())
        d += timedelta(days=1)
    daily = {day: {"positive": 0, "negative": 0, "scores": []} for day in day_list}
    for r in reviews:
        dt = _review_ts_naive_utc(r)
        if not dt:
            continue
        day = dt.date().isoformat()
        if day not in daily:
            continue
        daily[day]["scores"].append(float(r.get("sentiment_score") or 0))
        if r.get("is_positive"):
            daily[day]["positive"] += 1
        else:
            daily[day]["negative"] += 1
    result = []
    for day in day_list:
        sc = daily[day]["scores"]
        result.append({
            "date":          day,
            "avg_sentiment": round(sum(sc) / len(sc), 4) if sc else 0.0,
            "positive":      daily[day]["positive"],
            "negative":      daily[day]["negative"],
        })
    return result

def get_hours_distribution(reviews: list) -> dict:
    order = ["0-1h", "1-10h", "10-50h", "50-200h", "200h+"]
    pos = {k: 0 for k in order}
    neg = {k: 0 for k in order}
    def bkt(h):
        h = float(h or 0)
        if h < 1:   return "0-1h"
        if h < 10:  return "1-10h"
        if h < 50:  return "10-50h"
        if h < 200: return "50-200h"
        return "200h+"
    for r in reviews:
        b = bkt(r.get("hours_played", 0))
        if r.get("is_positive"):
            pos[b] += 1
        else:
            neg[b] += 1
    return {"labels": order, "positive": [pos[k] for k in order], "negative": [neg[k] for k in order]}

def get_heatmap_data(reviews: list, days: int = 30) -> dict:
    hour_labels = ["0-1h", "1-10h", "10-50h", "50-200h", "200h+"]
    def bkt(h):
        h = float(h or 0)
        if h < 1:   return 0
        if h < 10:  return 1
        if h < 50:  return 2
        if h < 200: return 3
        return 4
    end = datetime.utcnow().date()
    start = end - timedelta(days=days - 1)
    days_set = []
    d = start
    while d <= end:
        days_set.append(d.isoformat())
        d += timedelta(days=1)
    if not days_set:
        return {"x": [], "y": hour_labels, "z": [[] for _ in range(5)]}
    grid = {day: [0] * 5 for day in days_set}
    for r in reviews:
        dt = _review_ts_naive_utc(r)
        if not dt:
            continue
        day = dt.date().isoformat()
        if day in grid:
            grid[day][bkt(r.get("hours_played", 0))] += 1
    return {
        "x": days_set,
        "y": hour_labels,
        "z": [[grid[d][i] for d in days_set] for i in range(5)]
    }

def get_scatter_data(reviews: list) -> list:
    """Sentiment vs hours played scatter — sampled to 300 points."""
    pts = [{"x": float(r.get("hours_played") or 0),
            "y": float(r.get("sentiment_score") or 0),
            "pos": bool(r.get("is_positive"))} for r in reviews]
    # sample if too many
    if len(pts) > 300:
        import random
        pts = random.sample(pts, 300)
    return pts

# ── Full ETL run ──────────────────────────────────────────────────────────────

async def run_etl(app_id: str, db) -> dict:
    from database import Game, Review
    async with httpx.AsyncClient() as client:
        game_data   = await fetch_game_details(app_id, client)
        if not game_data:
            return {"error": "Game not found"}
        # Store page keeps review totals at 0 often — fill lifetime stats from SteamSpy
        tr = int(game_data.get("total_reviews") or 0)
        if tr == 0 and int(game_data.get("positive_reviews") or 0) + int(game_data.get("negative_reviews") or 0) == 0:
            spy = await _steamspy_detail(app_id, client)
            if spy:
                game_data["total_reviews"] = int(spy.get("total_reviews") or 0)
                game_data["positive_reviews"] = int(spy.get("positive_reviews") or 0)
                game_data["negative_reviews"] = int(spy.get("negative_reviews") or 0)
                game_data["rating"] = float(spy.get("rating") or 0)
                for fld in ("developer", "publisher", "genre"):
                    if spy.get(fld) and not game_data.get(fld):
                        game_data[fld] = spy[fld]
        raw_reviews = await fetch_reviews(app_id, client)

    pos = neg = flagged = 0
    processed = []
    for r in raw_reviews:
        score    = analyze_sentiment(r["review_text"])
        keywords = extract_trigger_keywords(r["review_text"])
        r["sentiment_score"]    = score
        r["trigger_keywords"]   = keywords
        if r["is_positive"]: pos += 1
        else:                neg += 1
        if keywords:         flagged += 1
        processed.append(r)

    # Keep Steam all-time review totals on the Game row; sample analytics come from Review rows
    lt_total = int(game_data.get("total_reviews") or 0)
    lt_pos = int(game_data.get("positive_reviews") or 0)
    lt_neg = int(game_data.get("negative_reviews") or 0)
    if lt_total <= 0 and lt_pos + lt_neg > 0:
        lt_total = lt_pos + lt_neg
        game_data["total_reviews"] = lt_total
    if (game_data.get("rating") or 0) == 0 and lt_total > 0:
        game_data["rating"] = round(lt_pos / lt_total * 100, 1)

    # Upsert game
    existing = db.query(Game).filter(Game.app_id == str(app_id)).first()
    if existing:
        for k, v in game_data.items():
            if hasattr(existing, k):
                setattr(existing, k, v)
        existing.last_updated = datetime.utcnow()
    else:
        db.add(Game(**{k: v for k, v in game_data.items() if hasattr(Game, k)}))

    # Replace reviews
    db.query(Review).filter(Review.game_id == str(app_id)).delete()
    for r in processed:
        db.add(Review(
            game_id         = str(app_id),
            review_text     = r["review_text"],
            sentiment_score = r["sentiment_score"],
            is_positive     = r["is_positive"],
            timestamp       = r["timestamp"],
            hours_played    = r["hours_played"],
            trigger_keywords= r["trigger_keywords"],
            author_id       = r["author_id"],
            votes_up        = r["votes_up"],
        ))
    db.commit()
    sample_n = len(processed)
    return {
        "app_id": app_id,
        "total": sample_n,
        "positive": pos,
        "negative": neg,
        "flagged": flagged,
    }
