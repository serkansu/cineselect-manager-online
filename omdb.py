import os
import csv
import requests
from pathlib import Path

OMDB_API_KEY = "295944aa"  # .env yoksa bunu kullan

def fetch_ratings(title, year):
    url = "https://www.omdbapi.com/"
    try:
        r = requests.get(url, params={"apikey": OMDB_API_KEY, "t": title, "y": year}, timeout=12)
        data = r.json()
        imdb = float(data.get("imdbRating", 0) or 0)
        rt = 0
        for rating in data.get("Ratings", []):
            if rating.get("Source") == "Rotten Tomatoes":
                rt = int((rating.get("Value") or "0").replace("%", ""))
                break
        return imdb, rt
    except Exception as e:
        print(f"Hata oluştu: {e}")
        return 0.0, 0

def get_ratings(imdb_id: str):
    imdb_rating = None
    rt = None

    # 1) CSV fallback
    seed_path = Path(__file__).parent / "seed_ratings.csv"
    if seed_path.exists():
        with seed_path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("imdb_id") == imdb_id:
                    ir = row.get("imdb_rating")
                    rt_s = row.get("rt")
                    imdb_rating = float(ir) if ir not in (None, "", "N/A") else None
                    try:
                        rt = int(rt_s) if rt_s not in (None, "", "N/A") else None
                    except:
                        rt = None
                    return {"imdb_rating": imdb_rating, "rt": rt}

    # 2) OMDb API (env varsa onu, yoksa sabiti kullan)
    api_key = os.getenv("OMDB_API_KEY", OMDB_API_KEY)
    if not api_key:
        return {"imdb_rating": None, "rt": None}

    url = "https://www.omdbapi.com/"
    try:
        r = requests.get(url, params={"apikey": api_key, "i": imdb_id, "tomatoes": "true"}, timeout=12)
        r.raise_for_status()
        data = r.json()
        ir = data.get("imdbRating")
        imdb_rating = float(ir) if ir and ir != "N/A" else None
        rt_pct = None
        for s in data.get("Ratings", []):
            if s.get("Source") == "Rotten Tomatoes":
                rt_pct = s.get("Value")  # "92%"
                break
        rt = int(rt_pct.strip("%")) if rt_pct and rt_pct.endswith("%") else None
    except Exception:
        return {"imdb_rating": None, "rt": None}

    return {"imdb_rating": imdb_rating, "rt": rt}
