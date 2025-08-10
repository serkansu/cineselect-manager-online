# omdb.py
import os, csv, requests
from pathlib import Path

# .env/Render yoksa şu fallback kullanılır (istersen boş bırak)
OMDB_FALLBACK = os.getenv("OMDB_FALLBACK", "295944aa")

SEED_PATH = Path(__file__).parent / "seed_ratings.csv"


def _read_from_seed(imdb_id: str):
    """seed_ratings.csv içinden (imdb_id, imdb_rating, rt) bulmaya çalışır."""
    if not SEED_PATH.exists():
        return None
    with SEED_PATH.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("imdb_id") == imdb_id:
                ir = row.get("imdb_rating")
                rt = row.get("rt")
                imdb_rating = float(ir) if ir and ir != "N/A" else None
                try:
                    rt_score = int(rt) if rt and rt != "N/A" else None
                except:
                    rt_score = None
                return {"imdb_rating": imdb_rating, "rt": rt_score}
    return None


def get_ratings(imdb_id: str):
    """
    1) seed_ratings.csv içinde varsa oradan döner
    2) Yoksa OMDb'yi IMDb ID ile çağırır (tomatoes=true)
       Dönüşe 'raw' alanında ham OMDb JSON'u iliştirir (debug için).
    """
    if not imdb_id:
        return {"imdb_rating": None, "rt": None}

    # 1) CSV
    seeded = _read_from_seed(imdb_id)
    if seeded:
        return seeded

    # 2) OMDb by ID
    api_key = os.getenv("OMDB_API_KEY", OMDB_FALLBACK)
    if not api_key:
        return {"imdb_rating": None, "rt": None}

    try:
        r = requests.get(
            "https://www.omdbapi.com/",
            params={"apikey": api_key, "i": imdb_id, "tomatoes": "true"},
            timeout=12,
        )
        data = r.json()
        ir = data.get("imdbRating")
        imdb_rating = float(ir) if ir and ir != "N/A" else None
        # RT %
        rt_pct = None
        for s in data.get("Ratings", []):
            if s.get("Source") == "Rotten Tomatoes":
                rt_pct = s.get("Value")  # "92%"
                break
        rt = int(rt_pct.strip("%")) if rt_pct and rt_pct.endswith("%") else None
        return {"imdb_rating": imdb_rating, "rt": rt, "raw": data}
    except Exception:
        return {"imdb_rating": None, "rt": None}


def fetch_ratings(title: str, year):
    """
    IMDb ID bulunamazsa başlık+yıl ile OMDb'den dener.
    Dönüş: (imdb_rating: float, rt: int, raw: dict)
    """
    api_key = os.getenv("OMDB_API_KEY", OMDB_FALLBACK)
    if not api_key:
        return 0.0, 0, {}
    try:
        r = requests.get(
            "https://www.omdbapi.com/",
            params={"apikey": api_key, "t": title, "y": year, "tomatoes": "true"},
            timeout=12,
        )
        data = r.json()
        ir = data.get("imdbRating")
        imdb_rating = float(ir) if ir and ir != "N/A" else None
        rt_pct = None
        for s in data.get("Ratings", []):
            if s.get("Source") == "Rotten Tomatoes":
                rt_pct = s.get("Value")
                break
        rt = int(rt_pct.strip("%")) if rt_pct and rt_pct.endswith("%") else None
        return imdb_rating or 0.0, rt or 0, data
    except Exception:
        return 0.0, 0, {}
