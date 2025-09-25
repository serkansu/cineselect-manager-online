def clear_filter_if_empty(key):
    """Resets the filter session state key to None if the associated widget selection is empty.
    Also clears the query param for that filter and triggers rerun if actually cleared.
    Additionally, if no filter is active after clearing, resets all query params and reruns to show the full list."""
    val = st.session_state.get(key)
    if not val:
        was_set = st.session_state.get(key, None) is not None
        st.session_state[key] = None
        # Clear corresponding query param
        qp = st.query_params
        rerun_needed = False
        if key in ["filter_director", "filter_actor", "filter_genre", "filter_created_by"]:
            if key in qp:
                del qp[key]
                rerun_needed = True
        # Only rerun if the key was set and got cleared, to avoid infinite loops
        if was_set or rerun_needed:
            st.rerun()
        # After rerun, if no filter is active, clear all query params and rerun again to fully reset
        if not any([
            st.session_state.get("filter_director"),
            st.session_state.get("filter_actor"),
            st.session_state.get("filter_genre"),
            st.session_state.get("filter_created_by")
        ]):
            st.query_params.clear()
            st.rerun()
import streamlit as st
from bs4 import BeautifulSoup
import urllib.parse
# --- Query param parsing for single-click filters ---
# At the top of the script, parse st.query_params and set session_state for filters
qp = st.query_params
for param, sskey in [
    ("filter_director", "filter_director"),
    ("filter_actor", "filter_actor"),
    ("filter_genre", "filter_genre"),
    ("filter_created_by", "filter_created_by"),
]:
    val = qp.get(param)
    # Normalize (Streamlit may give list or str)
    if isinstance(val, list):
        val = val[0] if val else None
    if val:
        st.session_state[sskey] = val
    else:
        # Only clear if not present in query params (don't clear if already set by button)
        if sskey not in st.session_state:
            st.session_state[sskey] = None

# Eksik metadata durumunda missing_metadata.csv dosyasına ekleme fonksiyonu
import csv


def overwrite_missing_meta(docs):
    """missing_metadata.csv'yi Firestore'dan tamamen yeniden yazar."""
    try:
        with open("missing_metadata.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["title", "year", "imdb_id", "note"])
            for doc in docs:
                item = doc.to_dict()
                title = item.get("title", "")
                year = item.get("year", "")
                imdb_id = item.get("imdb", "") or item.get("imdb_id", "")
                note = item.get("note", "")
                writer.writerow([title, year, imdb_id, note])
    except Exception as e:
        print(f"overwrite_missing_meta error: {e}")

# Eksik csv dosyalarını garantiye al
import os
import pandas as pd

for file_name in ["seed_meta.csv", "missing_metadata.csv"]:
    if not os.path.exists(file_name):
        pd.DataFrame().to_csv(file_name, index=False)
@st.cache_data(show_spinner=False)
def read_seed_meta(imdb_id: str):
    """
    seed_meta.csv içinden imdb_id ile eşleşen satırın metadata'sını döndürür.
    {'directors': [...], 'cast': [...], 'genres': [...]} veya None.
    """
    try:
        iid = (imdb_id or "").strip()
        if not iid or not SEED_META_PATH.exists():
            return None
        with SEED_META_PATH.open(newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                if (row.get("imdb_id") or "").strip() == iid:
                    return {
                        "directors": [d.strip() for d in (row.get("directors") or "").split(";") if d.strip()],
                        "cast": [c.strip() for c in (row.get("cast") or "").split(";") if c.strip()],
                        "genres": [g.strip() for g in (row.get("genres") or "").split(";") if g.strip()],
                    }
    except Exception as e:
        print("read_seed_meta error:", e)
    return None

@st.cache_data(show_spinner=False)
def fetch_metadata(imdb_id, title=None, year=None, is_series=False, existing=None):
    """
    OMDb öncelikli, gerekirse TMDB fallback ile metadata getirir.
    Yalnızca Firestore'daki mevcut (manuel) değerleri BOŞ olan alanları doldurur.
    `existing`: mevcut Firestore değerleri (dict), varsa.
    """
    # Fetch metadata as usual
    omdb_result = None
    tmdb_result = None
    # 1) OMDb
    try:
        omdb_key = os.getenv("OMDB_API_KEY")
        if omdb_key and imdb_id:
            url = f"http://www.omdbapi.com/?i={imdb_id}&apikey={omdb_key}&plot=short&r=json"
            r = requests.get(url, timeout=12)
            if r.status_code == 200:
                d = r.json()
                if d.get("Response") == "True":
                    directors = [x.strip() for x in (d.get("Director") or "").split(",") if x.strip() and x.strip() != "N/A"]
                    cast = [x.strip() for x in (d.get("Actors") or "").split(",") if x.strip() and x.strip() != "N/A"]
                    genres = [x.strip() for x in (d.get("Genre") or "").split(",") if x.strip() and x.strip() != "N/A"]
                    if directors or cast or genres:
                        omdb_result = {"directors": directors, "cast": cast, "genres": genres}
    except Exception as e:
        print("fetch_metadata OMDb error:", e)

    # 2) TMDB fallback (geliştirilmiş)
    try:
        tmdb_key = os.getenv("TMDB_API_KEY")
        if tmdb_key and imdb_id:
            find_url = f"https://api.themoviedb.org/3/find/{imdb_id}"
            params = {"api_key": tmdb_key, "external_source": "imdb_id"}
            r = requests.get(find_url, params=params, timeout=12)
            if r.status_code == 200:
                j = r.json()
                results = j.get("movie_results") or j.get("tv_results") or []
                if results:
                    tmdb_id = results[0].get("id")
                    search_type = "movie" if j.get("movie_results") else "tv"
                    # 🔑 detayları credits ile birlikte al
                    details_url = f"https://api.themoviedb.org/3/{search_type}/{tmdb_id}"
                    d_resp = requests.get(details_url, params={"api_key": tmdb_key, "append_to_response": "credits"}, timeout=12)
                    if d_resp.status_code == 200:
                        det = d_resp.json()
                        # Genres
                        genres = [g.get("name") for g in det.get("genres", []) if g.get("name")]
                        # Cast (ilk 8 kişi)
                        cast = [c.get("name") for c in det.get("credits", {}).get("cast", [])][:8]
                        # For TV shows, always set created_by from det["created_by"], and merge with all directors from crew
                        if search_type in ["tv", "show"]:
                            created_by = [c.get("name") for c in det.get("created_by", []) if c.get("name")]
                            all_directors = list({c.get("name") for c in det.get("credits", {}).get("crew", []) if c.get("job") == "Director" and c.get("name")})
                            # Merge created_by and directors, preserving order and removing duplicates
                            merged_creators = []
                            seen = set()
                            for name in created_by + all_directors:
                                if name and name not in seen:
                                    merged_creators.append(name)
                                    seen.add(name)
                            created_by = merged_creators
                            directors = merged_creators  # for backward compatibility if needed
                        else:
                            created_by = []
                            directors = list({c.get("name") for c in det.get("credits", {}).get("crew", []) if c.get("job") == "Director" and c.get("name")})
                            if not directors:
                                directors = ["Unknown"]
                        if not genres:
                            genres = ["Unknown"]
                        tmdb_result = {
                            "directors": directors,
                            "cast": cast,
                            "genres": genres,
                            "created_by": created_by
                        }
    except Exception as e:
        print("fetch_metadata TMDB error:", e)

    # --- IMDb full credits fallback if directors is empty or ["Unknown"] ---
    # Only attempt if both OMDb and TMDB failed to yield real directors
    # We'll merge into the TMDB result (if present), else meta
    imdb_fullcredits_result = None
    def _directors_empty(dlist):
        return not dlist or (isinstance(dlist, list) and (len(dlist) == 0 or dlist == ["Unknown"]))
    # Determine which result to patch (TMDB preferred for structure)
    target_result = tmdb_result if tmdb_result is not None else (omdb_result if omdb_result is not None else None)
    patch_needed = False
    if imdb_id:
        # Check if directors is missing or ["Unknown"]
        if target_result:
            if _directors_empty(target_result.get("directors", [])):
                patch_needed = True
        else:
            if _directors_empty(None):
                patch_needed = True
    if patch_needed or (not omdb_result and not tmdb_result):
        try:
            imdb_fullcredits_result = scrape_imdb_fullcredits(imdb_id)
            # Only patch if directors found
            if imdb_fullcredits_result and imdb_fullcredits_result.get("directors"):
                if target_result is not None:
                    # Patch into TMDB or OMDb result
                    target_result["directors"] = imdb_fullcredits_result.get("directors", [])
                    # Only update cast if original is empty
                    if not target_result.get("cast"):
                        target_result["cast"] = imdb_fullcredits_result.get("cast", [])
                    # Only update genres if original is empty or ["Unknown"]
                    if _directors_empty(target_result.get("genres", [])):
                        target_result["genres"] = imdb_fullcredits_result.get("genres", [])
                else:
                    # Patch into meta fallback below
                    tmdb_result = imdb_fullcredits_result
        except Exception as e:
            print(f"fetch_metadata IMDb fullcredits scrape error: {e}")

    # Merge fetched data, OMDb preferred
    meta = omdb_result or tmdb_result or {
        "directors": ["Unknown"],
        "cast": [],
        "genres": ["Unknown"],
        "created_by": []
    }

    # --- Only fill empty fields; keep existing manual values if present ---
    if existing is not None:
        # Defensive: support both None and empty list as "empty"
        result = {}
        for field in ("directors", "cast", "genres"):
            existing_val = existing.get(field)
            # Treat empty list, None, or ["Unknown"] as empty for directors/genres
            if field in ("directors", "genres"):
                if not existing_val or (isinstance(existing_val, list) and (len(existing_val) == 0 or existing_val == ["Unknown"])):
                    result[field] = meta.get(field, [])
                else:
                    result[field] = existing_val
            elif field == "cast":
                if not existing_val or (isinstance(existing_val, list) and len(existing_val) == 0):
                    result[field] = meta.get(field, [])
                else:
                    result[field] = existing_val
        # For TV shows, propagate created_by even if empty, and always if present in meta
        result["created_by"] = meta.get("created_by", [])
        return result
    else:
        return meta


# --- IMDb Full Credits Scraper Fallback ---
def scrape_imdb_fullcredits(imdb_id):
    """
    Scrape IMDb full credits page for directors and main cast.
    Returns dict: {'directors': [...], 'cast': [...], 'genres': []}
    """
    import requests
    from bs4 import BeautifulSoup
    url = f"https://www.imdb.com/title/{imdb_id}/fullcredits"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return {"directors": [], "cast": [], "genres": []}
        soup = BeautifulSoup(resp.text, "html.parser")
        directors = []
        # Find the Directors section (can be "Directed by" or "Director" or "Directors")
        # The page has a h4 or h3 with text "Directed by" or "Director(s)"
        dir_header = None
        for h in soup.find_all(["h4", "h3"]):
            if h.get_text(strip=True).lower().startswith("directed by") or h.get_text(strip=True).lower().startswith("director"):
                dir_header = h
                break
        if dir_header:
            # The directors are in the next sibling table or list
            sib = dir_header.find_next_sibling()
            # Sometimes in ul > li > a, sometimes in table
            if sib:
                # Try table rows first
                if sib.name == "table":
                    for row in sib.find_all("tr"):
                        for a in row.find_all("a"):
                            name = a.get_text(strip=True)
                            if name:
                                directors.append(name)
                elif sib.name == "ul":
                    for li in sib.find_all("li"):
                        a = li.find("a")
                        if a:
                            name = a.get_text(strip=True)
                            if name:
                                directors.append(name)
        # If not found, fallback: look for div with class "credit_summary_item"
        if not directors:
            for div in soup.find_all("div", class_="credit_summary_item"):
                h = div.find(["h4", "h3"])
                if h and ("Director" in h.get_text(strip=True)):
                    for a in div.find_all("a"):
                        name = a.get_text(strip=True)
                        if name:
                            directors.append(name)
        # Remove duplicates
        directors = list(dict.fromkeys(directors))
        # --- Cast extraction (main table: table with class "cast_list") ---
        cast = []
        cast_table = soup.find("table", class_="cast_list")
        if cast_table:
            for row in cast_table.find_all("tr"):
                # Each row: td with class "primary_photo", next td is actor name
                tds = row.find_all("td")
                if len(tds) >= 2:
                    a = tds[1].find("a")
                    if a:
                        name = a.get_text(strip=True)
                        if name:
                            cast.append(name)
                if len(cast) >= 20:
                    break
        # Genres: not present on fullcredits page, so leave empty
        return {"directors": directors, "cast": cast, "genres": []}
    except Exception as e:
        print(f"scrape_imdb_fullcredits error: {e}")
        return {"directors": [], "cast": [], "genres": []}

def backfill_metadata(limit=20):
    db = get_firestore()
    # toplamı göstermek için önce topla
    all_docs = []
    for type_name, collection in [("movie", "favorites"), ("show", "favorites")]:
        for d in db.collection(collection).where("type", "==", type_name).stream():
            all_docs.append((type_name, collection, d))

    total = len(all_docs) or 1
    progress = st.progress(0)
    status = st.empty()

    count = 0
    updated = 0
    not_updated = []

    docs_to_process = all_docs if limit is None else all_docs[:limit]

    for idx, (type_name, collection, doc) in enumerate(docs_to_process, start=1):
        item = doc.to_dict()
        imdb_id = (item.get("imdb") or "").strip()
        title = item.get("title")
        year = item.get("year")

        if not imdb_id or imdb_id == "tt0000000":
            status.write(f"⏭ Skipped (no imdb): {title} ({year}) [{idx}/{total}]")
            progress.progress(int(idx/total*100))
            append_missing_meta(title, year, imdb_id, "no imdb id")
            count += 1
            continue

        meta = read_seed_meta(imdb_id)
        meta_source = "seed"
        # If meta exists but directors, cast, or genres are missing, try to fetch again from OMDb/TMDB
        if meta and (not meta.get("directors") or not meta.get("cast") or not meta.get("genres")):
            new_meta = fetch_metadata(imdb_id, title, year, is_series=(type_name == "show"))
            if new_meta:
                if not meta.get("directors"):
                    meta["directors"] = new_meta.get("directors", [])
                if not meta.get("cast"):
                    meta["cast"] = new_meta.get("cast", [])
                if not meta.get("genres"):
                    meta["genres"] = new_meta.get("genres", [])
                meta_source = "fetch"
        if not meta:
            meta = fetch_metadata(imdb_id, title, year, is_series=(type_name == "show"))
            meta_source = "fetch"
            time.sleep(0.5)
            # If fetch_metadata returns None (should not anymore), set genres to ["Unknown"]
            if meta is None:
                meta = {"directors": [], "cast": [], "genres": ["Unknown"]}

        if meta and (meta.get("directors") or meta.get("cast") or meta.get("genres")):
            # Ensure genres is not empty; if so, set to ["Unknown"]
            if not meta.get("genres"):
                meta["genres"] = ["Unknown"]
            try:
                update_data = {
                    "directors": meta.get("directors", []),
                    "cast":      meta.get("cast", []),
                    "genres":    meta.get("genres", []),
                }
                if type_name == "show":
                    # fetch_metadata TV için 'created_by' döndürürse yaz
                    update_data["created_by"] = meta.get("created_by", [])
                db.collection(collection).document(item["id"]).update(update_data)
                append_seed_meta(imdb_id, title, year, meta)   # ✅ CSV’ye de yaz
                updated += 1
                status.write(f"✅ Updated: {title} ({year}) [{idx}/{total}] via {meta_source}")
            except Exception as e:
                not_updated.append(f"{title} ({year})")
                status.write(f"⚠️ Failed to update Firestore for {title} ({year}): {e}")
        else:
            not_updated.append(f"{title} ({year})")
            status.write(f"⚠️ No metadata: {title} ({year}) [{idx}/{total}]")
            # Write to missing_metadata.csv on failure
            append_missing_meta(title, year, imdb_id, "no meta found")

        count += 1
        progress.progress(int(idx/total*100))

    progress.progress(100)
    progress.empty()
    st.success(f"Done. Scanned: {count}, updated: {updated}, not updated: {len(not_updated)}")
    if not_updated:
        st.warning(f"⚠️ Güncellenemeyenler: {len(not_updated)}")
        st.write(not_updated)
        # --- Export not_updated list to CSV ---
        import csv
        rows = []
        for entry in not_updated:
            # Try to split "Title (Year)" pattern
            title = entry
            year = ""
            imdb_id = ""
            note = ""
            try:
                # Try to extract title and year
                import re
                m = re.match(r"^(.*)\s+\((\d{4})\)$", entry.strip())
                if m:
                    title = m.group(1).strip()
                    year = m.group(2).strip()
                else:
                    title = entry.strip()
                    year = ""
            except Exception:
                title = entry
                year = ""
            # Try to get imdb_id from Firestore
            # Search all_docs for matching title and year
            imdb_id = ""
            for _type, _coll, _doc in all_docs:
                d = _doc.to_dict()
                t = (d.get("title") or "").strip()
                y = str(d.get("year") or "").strip()
                if title == t and (not year or year == y):
                    imdb_id = (d.get("imdb") or d.get("imdb_id") or "").strip()
                    break
            rows.append([title, year, imdb_id, note])
        # Write to CSV
        with open("missing_metadata.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["title", "year", "imdb_id", "note"])
            for row in rows:
                writer.writerow(row)
        st.success("missing_metadata.csv dosyası oluşturuldu.")
def validate_imdb_id(imdb_id, title=None, year=None):
    """
    IMDb ID'nin OMDb'de geçerli olup olmadığını kontrol eder.
    Öncelikle seed_ratings.csv'yi kontrol eder. Eğer orada geçerli rating varsa imdb_id'yi döndürür.
    Eğer geçerli değilse, OMDb'den kontrol eder. Eğer OMDb'de geçerli rating varsa imdb_id'yi döndürür.
    Eğer OMDb'den de alınamazsa, fetch_ratings ile doğru IMDb ID'yi bulmaya çalışır.
    Doğru ID bulunursa onu döndürür, yoksa None döner.
    """
    # 1. Öncelikle seed_ratings.csv'yi kontrol et
    if imdb_id and imdb_id != "tt0000000":
        seed_stats = read_seed_rating(imdb_id)
        if seed_stats and (seed_stats.get("imdb_rating") or seed_stats.get("rt")):
            return imdb_id
    # 2. OMDb'de kontrol et
    if imdb_id and imdb_id != "tt0000000":
        stats = get_ratings(imdb_id)
        if stats and (stats.get("imdb_rating") or stats.get("rt")):
            return imdb_id
    # 3. OMDb'den rating alınamadıysa veya imdb_id eksikse, fetch_ratings ile deneriz
    if title:
        ir, rt, raw = fetch_ratings(title, year)
        # raw dict ise ve imdbID varsa ve başında "tt" ile başlıyorsa
        if isinstance(raw, dict):
            new_id = raw.get("imdbID") or raw.get("imdb_id")
            if new_id and isinstance(new_id, str) and new_id.startswith("tt") and new_id != "tt0000000":
                return new_id
    return None
from tmdb import search_movie, search_tv, search_by_actor
from omdb import get_ratings
from omdb import fetch_ratings
import csv
from pathlib import Path
SEED_META_PATH = Path(__file__).parent / "seed_meta.csv"
import requests
import firebase_admin
import base64
from firebase_admin import credentials, firestore
import json
import os
import time
# ---------- Sorting helpers for Streamio export ----------
ROMAN_MAP = {
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10,
}

def _roman_to_int(s: str) -> int | None:
    s = (s or "").strip().lower()
    return ROMAN_MAP.get(s)

import re
_FRANCHISE_WORDS = {"the", "a", "an"}

def _normalize_franchise(title: str) -> str:
    """Get a coarse franchise/base name from a movie title.
    Examples:
      - "The Terminator" -> "terminator"
      - "Terminator 2: Judgment Day" -> "terminator"
      - "Back to the Future Part II" -> "back to the future"
    This is a heuristic; it deliberately keeps it simple.
    """
    t = (title or "").lower()
    # drop leading article
    parts = t.split()
    if parts and parts[0] in _FRANCHISE_WORDS and len(parts) > 1:
        t = " ".join(parts[1:])
    # keep text before a colon if it looks like a subtitle
    t = t.split(":")[0]
    # remove trailing sequel tokens like numbers/roman/"part X"
    t = re.sub(r"\bpart\s+[ivx]+\b", "", t).strip()
    t = re.sub(r"\bpart\s+\d+\b", "", t).strip()
    t = re.sub(r"\b\d+\b", "", t).strip()
    t = re.sub(r"\s+", " ", t)
    return t

def _parse_sequel_number(title: str) -> int:
    """Try to extract sequel ordering number from a title.
    Returns 0 if not detected (so originals come first).
    Supports digits and roman numerals after words like 'part' or alone (e.g., 'Terminator 2').
    """
    t = (title or "").lower()
    # "Part II" / "Part 2"
    m = re.search(r"\bpart\s+([ivx]+|\d+)\b", t)
    if m:
        token = m.group(1)
        if token.isdigit():
            return int(token)
        ri = _roman_to_int(token)
        if ri:
            return ri
    # lone digits after the base word: e.g., "Terminator 2"
    m = re.search(r"\b(\d+)\b", t)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            pass
    # "II", "III" as standalone
    m = re.search(r"\b([ivx]{1,4})\b", t)
    if m:
        ri = _roman_to_int(m.group(1))
        if ri:
            return ri
    return 0

def _compute_franchise_min_year(items: list[dict]) -> dict[str, int]:
    """Return {base_name: min_year} for bases that have 2+ items in the list.
    Non-numeric/missing years are ignored.
    """
    years_by_base: dict[str, list[int]] = {}
    for it in items:
        base = _normalize_franchise(it.get("title", ""))
        try:
            y = int(it.get("year") or 0)
        except Exception:
            y = 0
        years_by_base.setdefault(base, []).append(y)
    return {b: min([y for y in ys if isinstance(y, int)]) for b, ys in years_by_base.items() if len(ys) >= 2}

def sort_media_for_export(items: list[dict], apply_franchise: bool = True) -> list[dict]:
    """Sort newest->oldest by *group year* (franchise min-year if grouped),
    then by sequel number (1,2,3…) inside the same franchise, otherwise by CineSelect.
    """
    items = list(items or [])
    base_min_year = _compute_franchise_min_year(items) if apply_franchise else {}

    def keyfn(it: dict):
        # group year: min franchise year if franchise exists (2+ items), else own year
        base = _normalize_franchise(it.get("title", ""))
        try:
            own_year = int(it.get("year") or 0)
        except Exception:
            own_year = 0
        group_year = base_min_year.get(base, own_year)
        # sequel number only meaningful if multiple in same base
        sequel_no = _parse_sequel_number(it.get("title", "")) if base in base_min_year else 0
        # tie-breaker by CineSelect rating (desc)
        cs = it.get("cineselectRating") or 0
        return (-group_year, base, sequel_no, -int(cs))

    return sorted(items, key=keyfn)
# ---------- /sorting helpers ----------
# --- seed_ratings.csv için yol ve ekleme fonksiyonu ---
SEED_PATH = Path(__file__).parent / "seed_ratings.csv"

def append_seed_rating(imdb_id, title, year, imdb_rating, rt_score):
    """seed_ratings.csv'ye (yoksa) yeni satır ekler; varsa dokunmaz."""
    if not imdb_id or imdb_id == "tt0000000":
        return

    # Zaten var mı kontrol et
    exists = False
    if SEED_PATH.exists():
        with SEED_PATH.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("imdb_id") == imdb_id:
                    exists = True
                    break
    if exists:
        return  # Aynı imdb_id zaten kayıtlı

    # Başlık yazmak gerekir mi?
    write_header = not SEED_PATH.exists() or SEED_PATH.stat().st_size == 0

    with SEED_PATH.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["imdb_id", "title", "year", "imdb_rating", "rt"])
        w.writerow([
            imdb_id,
            title,
            str(year or ""),
            (imdb_rating if imdb_rating is not None else ""),
            (rt_score if rt_score is not None else ""),
        ])
# --- /seed ekleme fonksiyonu ---

# --- seed okuma fonksiyonu ---
@st.cache_data(show_spinner=False)
def read_seed_rating(imdb_id: str):
    """seed_ratings.csv içinden imdb_id ile eşleşen satırı döndürür.
    {'imdb_rating': float|None, 'rt': int|None} şeklinde veri verir; bulunamazsa None döner.
    Hem 'imdb_id' hem de 'imdb' sütun adlarını destekler.
    """
    try:
        iid = (imdb_id or "").strip()
        if not iid or not SEED_PATH.exists():
            return None
        with SEED_PATH.open(newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                key = (row.get("imdb_id") or row.get("imdb") or "").strip()
                if key == iid:
                    # değerleri temizle
                    ir = row.get("imdb_rating")
                    rt = row.get("rt")
                    try:
                        ir_val = float(ir) if ir not in (None, "", "N/A") else None
                    except Exception:
                        ir_val = None
                    try:
                        rt_val = int(float(rt)) if rt not in (None, "", "N/A") else None
                    except Exception:
                        rt_val = None
                    # If both are missing/invalid/zero, return None so OMDb fallback works
                    imdb_invalid = ir_val in (None, 0, 0.0)
                    rt_invalid = rt_val in (None, 0)
                    # Special case: IMDb rating string "0.0"
                    if isinstance(ir, str) and ir.strip() in ("0", "0.0"):
                        imdb_invalid = True
                    if isinstance(rt, str) and rt.strip() == "0":
                        rt_invalid = True
                    # Also treat "N/A" as invalid (already handled above)
                    if imdb_invalid and rt_invalid:
                        return None
                    return {"imdb_rating": ir_val, "rt": rt_val}
    except Exception:
        pass
    return None
# --- /seed okuma fonksiyonu ---

# --- seed_meta.csv ekleme fonksiyonu ---
def overwrite_seed_meta(docs):
    """seed_meta.csv'yi Firestore'dan tamamen yeniden yazar."""
    try:
        with SEED_META_PATH.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["imdb_id", "title", "year", "directors", "created_by", "cast", "genres"])
            for doc in docs:
                item = doc.to_dict()
                imdb_id = item.get("imdb", "")
                title = item.get("title", "")
                year = item.get("year", "")
                directors   = "; ".join(item.get("directors", []))
                created_by  = "; ".join(item.get("created_by", []))
                cast        = "; ".join(item.get("cast", []))
                genres      = "; ".join(item.get("genres", []))
                w.writerow([imdb_id, title, year, directors, created_by, cast, genres])
    except Exception as e:
        print("overwrite_seed_meta error:", e)

def append_seed_meta(imdb_id, title, year, meta):
    """seed_meta.csv'ye (yoksa) yeni satır ekler; varsa dokunmaz."""
    if not imdb_id or imdb_id == "tt0000000":
        return
    exists = False
    if SEED_META_PATH.exists():
        with SEED_META_PATH.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("imdb_id") == imdb_id:
                    exists = True
                    break
    if exists:
        return
    write_header = not SEED_META_PATH.exists() or SEED_META_PATH.stat().st_size == 0
    with SEED_META_PATH.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["imdb_id", "title", "year", "directors", "created_by", "cast", "genres"])
        w.writerow([
            imdb_id,
            title,
            str(year or ""),
            "; ".join(meta.get("directors", [])),
            "; ".join(meta.get("created_by", [])) if "created_by" in meta else "",
            "; ".join(meta.get("cast", [])),
            "; ".join(meta.get("genres", [])),
        ])
# --- /seed okuma fonksiyonu ---
def get_imdb_id_from_tmdb(title, year=None, is_series=False):
    tmdb_api_key = os.getenv("TMDB_API_KEY")
    if not tmdb_api_key:
        print("❌ TMDB API key not found in environment variables.")
        return ""

    search_type = "tv" if is_series else "movie"
    search_url = f"https://api.themoviedb.org/3/search/{search_type}"
    params = {
        "api_key": tmdb_api_key,
        "query": title,
        "year": year if not is_series else None,
        "first_air_date_year": year if is_series else None,
    }

    response = requests.get(search_url, params=params)
    if response.status_code != 200:
        return ""

    results = response.json().get("results", [])
    if not results:
        return ""

    tmdb_id = results[0]["id"]
    external_ids_url = f"https://api.themoviedb.org/3/{search_type}/{tmdb_id}/external_ids"
    external_response = requests.get(external_ids_url, params={"api_key": tmdb_api_key})
    if external_response.status_code != 200:
        return ""

    imdb_id = external_response.json().get("imdb_id", "")
    return imdb_id or ""
def push_favorites_to_github():
    """Push favorites.json, seed_ratings.csv, seed_meta.csv, and missing_metadata.csv to their respective GitHub repos.
    - favorites.json  -> serkansu/cineselect-addon
    - seed_ratings.csv -> serkansu/cineselect-manager-online
    - seed_meta.csv -> serkansu/cineselect-manager-online
    - missing_metadata.csv -> serkansu/cineselect-manager-online
    """
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        st.warning("⚠️ GITHUB_TOKEN environment variable is missing!")
        st.error("❌ GitHub token bulunamadı. Environment variable ayarlanmalı.")
        return

    # Which file goes to which repo
    publish_plan = [
        {"file": "favorites.json", "owner": "serkansu", "repo": "cineselect-addon"},
        {"file": "seed_ratings.csv", "owner": "serkansu", "repo": "cineselect-manager-online"},
        {"file": "seed_meta.csv", "owner": "serkansu", "repo": "cineselect-manager-online"},
        {"file": "missing_metadata.csv", "owner": "serkansu", "repo": "cineselect-manager-online"},
    ]

    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json",
    }

    for item in publish_plan:
        file_path = item["file"]
        repo_owner = item["owner"]
        repo_name = item["repo"]
        commit_message = f"Update {file_path} via Streamlit sync"
        url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"

        # Read file to upload; skip if missing
        try:
            with open(file_path, "rb") as f:
                content = f.read()
        except FileNotFoundError:
            st.warning(f"⚠️ Dosya bulunamadı, atlandı: {file_path}")
            continue

        encoded_content = base64.b64encode(content).decode("utf-8")

        # Get current SHA if file exists
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            sha = response.json().get("sha")
        elif response.status_code == 404:
            sha = None
        else:
            st.error(f"❌ GitHub API erişim hatası ({file_path} → {repo_owner}/{repo_name}): {response.status_code}")
            try:
                st.code(response.json())
            except Exception:
                pass
            continue

        payload = {
            "message": commit_message,
            "content": encoded_content,
            "branch": "main",
        }
        if sha:
            payload["sha"] = sha

        put_response = requests.put(url, headers=headers, json=payload)
        if put_response.status_code not in (200, 201):
            st.error(f"❌ Push başarısız ({file_path} → {repo_owner}/{repo_name}): {put_response.status_code}")
            try:
                st.code(put_response.json())
            except Exception:
                pass
        else:
            st.success(f"✅ Push OK: {file_path} → {repo_owner}/{repo_name}")
from firebase_setup import get_firestore
def fix_invalid_imdb_ids(data):
    for section in ["movies", "shows"]:
        for item in data[section]:
            if isinstance(item.get("imdb"), (int, float)):
                item["imdb"] = ""

def sort_flat_for_export(items, mode):
    """Sort a flat media list by selected mode in descending order.
    mode: 'imdb' | 'cc' | 'year'
    """
    def key_fn(it):
        if mode == "imdb":
            v = it.get("imdbRating")
            try:
                return float(v) if v not in (None, "", "N/A") else -1
            except Exception:
                return -1
        elif mode == "year":
            try:
                return int(str(it.get("year", "0")).strip() or 0)
            except Exception:
                return 0
        # default: CineSelect score
        try:
            return int(it.get("cineselectRating") or 0)
        except Exception:
            return 0
    return sorted(items or [], key=key_fn, reverse=True)

# ---------------------- CineSelect clamp & sync helpers ----------------------
def _clamp_cs(v: int | float) -> int:
    try:
        iv = int(v)
    except Exception:
        iv = 0
    if iv < 1:
        return 1
    if iv > 10000:
        return 10000
    return iv

# Streamlit on_change helpers to keep slider and input in sync

def _sync_cs_from_slider(src_key: str, dst_key: str):
    v = _clamp_cs(st.session_state.get(src_key, 0))
    st.session_state[src_key] = v
    st.session_state[dst_key] = v


def _sync_cs_from_input(src_key: str, dst_key: str):
    v = _clamp_cs(st.session_state.get(src_key, 0))
    st.session_state[src_key] = v
    st.session_state[dst_key] = v

# --- Simple session-based auth gate using an env var ---
def ensure_authenticated():
    key = (os.getenv("APP_ACCESS_KEY") or "").strip()
    if not key:
        return

    if st.session_state.get("_auth_ok", False):
        return

    st.title("🔒 Serkan’s Watchagain (Manager)")

    # Visible HTML login form with username+password (autocomplete hints)
    # We include a small JS routine that: 1) clones the form and POSTS it into a hidden iframe
    #    so the browser sees a real POST (and offers to save the password / Face ID), and
    #    2) then navigates the main window to ?password=... so Streamlit can capture it.
    # This keeps UX smooth and triggers the browser password-manager save prompt.
    login_html = r'''
    <div>
      <form id="ss_login" autocomplete="on">
        <label style="font-size:14px">Kullanıcı (opsiyonel)</label><br>
        <input type="text" name="username" id="ss_username" placeholder="Kullanıcı" autocomplete="username" style="padding:8px; font-size:16px; width:260px; margin-bottom:8px;" />
        <br>
        <label style="font-size:14px">Şifre</label><br>
        <input type="password" name="password" id="ss_password" placeholder="Şifre" autocomplete="current-password" style="padding:8px; font-size:16px; width:260px;" />
        <br><br>
        <input type="submit" value="Giriş" style="padding:8px 12px; font-size:16px;" />
      </form>

      <!-- hidden iframe used to POST so browser will prompt to save password -->
      <iframe name="ss_pw_iframe" id="ss_pw_iframe" style="display:none"></iframe>

      <script>
        (function(){
          const form = document.getElementById('ss_login');
          form.addEventListener('submit', function(ev){
            ev.preventDefault();
            const u = document.getElementById('ss_username').value || '';
            const p = document.getElementById('ss_password').value || '';
            // 1) build a form and POST it into a hidden iframe to trigger browser save
            const f = document.createElement('form');
            f.method = 'post';
            f.action = window.location.pathname || window.location.href;
            f.target = 'ss_pw_iframe';
            f.style.display = 'none';
            const i1 = document.createElement('input'); i1.name = 'username'; i1.value = u; f.appendChild(i1);
            const i2 = document.createElement('input'); i2.name = 'password'; i2.value = p; f.appendChild(i2);
            document.body.appendChild(f);
            try{ f.submit(); }catch(e){ /* ignore */ }
            // 2) Parolayı sessionStorage'a koy, postMessage ile gönder, sonra sessionStorage'dan hemen sil
            sessionStorage.setItem('ss_pw', p);
            window.postMessage({type: 'ss_pw', pw: p}, '*');
            setTimeout(function(){ sessionStorage.removeItem('ss_pw'); }, 500);
          });

          // Listener: ss_pw mesajını yakala ve password paramını ekle
          window.addEventListener('message', function(ev){
            if (ev && ev.data && ev.data.type === 'ss_pw') {
              // sessionStorage temizlendikten hemen sonra URL'ye ekle
              setTimeout(function(){
                const params = new URLSearchParams(window.location.search);
                params.set('password', ev.data.pw);
                window.location.search = params.toString();
              }, 525); // sessionStorage.removeItem'dan hemen sonra
            }
          });
        })();
      </script>
    </div>
    '''

    st.markdown(login_html, unsafe_allow_html=True)

    # Read password from query params (string or None)
    pw = st.query_params.get('password')
    if pw:
        # In some Streamlit versions pw can be list; normalize
        if isinstance(pw, list):
            pw = pw[0]
        if pw == key:
            st.session_state['_auth_ok'] = True
            # Clear password from URL after successful login to avoid leaking it in history
            # Navigate to same path without query string using JS snippet
            st.markdown("""
                <script>
                  (function(){
                    try{
                      const url = window.location.pathname;
                      window.history.replaceState({}, document.title, url);
                    }catch(e){/* ignore */}
                  })();
                </script>
            """, unsafe_allow_html=True)
            st.rerun()
        else:
            st.error('❌ Hatalı şifre')

    st.stop()
# --- /auth gate ---

def sync_with_firebase(sort_mode="cc"):
    favorites_data = {
        "movies": st.session_state.get("favorite_movies", []),
        "shows": st.session_state.get("favorite_series", [])
    }
    fix_invalid_imdb_ids(favorites_data)  # IMDb puanı olanları temizle
    # IMDb düzeltmesinden sonra type alanını normalize et
    for section in ["movies", "shows"]:
        for item in favorites_data[section]:
            t = item.get("type", "").lower()
            if t in ["tv", "tvshow", "show", "series"]:
                item["type"] = "show"
            elif t in ["movie", "film"]:
                item["type"] = "movie"
    # IMDb ID eksikse ➜ tamamlama başlıyor
    # Eksik imdb id'leri tamamla
    for section in ["movies", "shows"]:
        for item in favorites_data[section]:
            if not item.get("imdb") or item.get("imdb") == "":
                title = item.get("title")
                year = item.get("year")
                raw_type = item.get("type", "").lower()
                section_name = section.lower()

                is_series_by_section = section_name in ["shows", "series"]
                is_series_by_type = raw_type in ["series", "tv", "tv_show", "tvshow", "show"]

                is_series = is_series_by_section or is_series_by_type
                # NOTE: İç tip alanını tutarlı hale getiriyoruz: dizi için 'show', film için 'movie'
                item["type"] = "show" if is_series else "movie"
                imdb_id = get_imdb_id_from_tmdb(title, year, is_series=is_series)
                # IMDb ve RT puanlarını çek
                stats = get_ratings(imdb_id)
                imdb_rating = stats.get("imdb_rating") if stats else None
                rt_score = stats.get("rt") if stats else None
                print(f"🎬 {title} ({year}) | is_series={is_series} → IMDb ID: {imdb_id}")
                item["imdb"] = imdb_id
                item["imdbRating"] = float(imdb_rating) if imdb_rating is not None else 0.0
                item["rt"] = int(rt_score) if rt_score is not None else 0
                # ⬇️ YENİ: seed_ratings.csv’ye (yoksa) ekle
                append_seed_rating(imdb_id, title, year, imdb_rating, rt_score)
    # seed_ratings.csv içinde her favorinin olduğundan emin ol (CSV'de zaten varsa eklenmez)
    for _section in ("movies", "shows"):
        for _it in favorites_data.get(_section, []):
            append_seed_rating(
                imdb_id=_it.get("imdb"),
                title=_it.get("title"),
                year=_it.get("year"),
                imdb_rating=_it.get("imdbRating"),
                rt_score=_it.get("rt"),
            )
    # ---- Apply export ordering
    sorted_movies = sort_flat_for_export(favorites_data.get("movies", []), sort_mode)
    sorted_series = sort_flat_for_export(favorites_data.get("shows", []), sort_mode)

    # Dışarı yazarken anahtar adını 'shows' -> 'series' olarak çevir
    output_data = {
        "movies": sorted_movies,
        "series": sorted_series,
    }
    with open("favorites.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=4)
        st.write("🔍 FAVORITES DEBUG (output):", output_data)
    st.success("✅ favorites.json dosyası yerel olarak oluşturuldu.")

    # --- Overwrite seed_meta.csv and missing_metadata.csv from Firestore ---
    movie_docs = list(db.collection("favorites").where("type", "==", "movie").stream())
    series_docs = list(db.collection("favorites").where("type", "==", "show").stream())
    all_docs = movie_docs + series_docs
    overwrite_seed_meta(all_docs)

    # Build missing_docs list based on Firestore docs with missing metadata
    missing_docs = []
    for d in all_docs:
        data = d.to_dict()
        dirs = data.get("directors") or []
        cast = data.get("cast") or []
        genres = data.get("genres") or []
        # Consider missing if any key fields are empty or contain only "Unknown"
        if (not dirs or dirs == ["Unknown"]) or (not cast) or (not genres or genres == ["Unknown"]):
            missing_docs.append(d)

    overwrite_missing_meta(missing_docs)

    # GitHub'a push et (tüm CSV dosyaları dahil)
    push_favorites_to_github()
    st.success("✅ favorites.json, seed_ratings.csv, seed_meta.csv ve missing_metadata.csv GitHub'a push edildi.")

# --- Page config and auth gate (must run before any Firestore access) ---
st.set_page_config(page_title="Serkan's Watchagain Movies & Series ONLINE", layout="wide")
ensure_authenticated()
# --- /Page config & auth gate ---
import sys
# --- Firestore bağlantısı kuruluyor ---
try:
    db = get_firestore()
except Exception as e:
    st.error(f"❌ Firebase bağlantısı kurulamadı: {e}")
    st.stop()

# --- Tek seferde Firestore'dan tüm favoriler çek ---
all_docs = [doc.to_dict() for doc in db.collection("favorites").stream()]

# Firestore'dan verileri çek ve session'a yaz
movie_docs = db.collection("favorites").where("type", "==", "movie").stream()
series_docs = db.collection("favorites").where("type", "==", "show").stream()

st.session_state["favorite_movies"] = [doc.to_dict() for doc in movie_docs]
st.session_state["favorite_series"] = [doc.to_dict() for doc in series_docs]
st.markdown("""
    <h1 style='text-align:center;'>🍿 <b>Serkan's Watchagain Movies & Series <span style="color:#2ecc71;">ONLINE ✅</span></b></h1>
""", unsafe_allow_html=True)

col1, col2 = st.columns([1, 2])
with col1:
    if st.button("🏠 Go to Top"):
        st.rerun()

with col2:
    if "show_posters" not in st.session_state:
        st.session_state["show_posters"] = True

    # Varsayılan sıralama modu (cc = CineSelect)
    if "sync_sort_mode" not in st.session_state:
        st.session_state["sync_sort_mode"] = "year"

    if st.button("📂 JSON & CSV Sync"):
        sync_with_firebase(sort_mode=st.session_state.get("sync_sort_mode", "cc"))
        st.success("✅ favorites.json ve seed_ratings.csv senkronize edildi.")

    # Butonun ALTINA üç radyo butonu (imdb, cc, year)
    st.radio(
        "Sync sıralaması",
        ["imdb", "cc", "year"],
        key="sync_sort_mode",
        horizontal=True,
        help="IMDb = IMDb puanı, cc = CineSelect, year = Yıl. Hepsi yüksekten düşüğe sıralar."
    )

def show_favorites_count():
    movie_docs = db.collection("favorites").where("type", "==", "movie").stream()
    series_docs = db.collection("favorites").where("type", "==", "show").stream()

    movie_count = len(list(movie_docs))
    series_count = len(list(series_docs))

    st.info(f"🎬 Favorite Movies: {movie_count} | 📺 Favorite TV Shows: {series_count}")
if st.button("📊 Favori Sayılarını Göster"):
    show_favorites_count()


show_posters = st.session_state["show_posters"]
media_type = st.radio("Search type:", ["Movie", "TV Show", "Actor/Actress"], horizontal=True)

# ---- Safe clear for search widgets (avoid modifying after instantiation)
if "clear_search" not in st.session_state:
    st.session_state.clear_search = False

if st.session_state.clear_search:
    # reset the flag and clear both the input widget's value and the session copy
    st.session_state.clear_search = False
    st.session_state["query_input"] = ""
    st.session_state.query = ""

if "query" not in st.session_state:
    st.session_state.query = ""

query = st.text_input(
    f"🔍 Search for a {media_type.lower()}",
    value=st.session_state.query,
    key="query_input",
)

if query:
    st.session_state.query = query
    if media_type == "Movie":
        results = search_movie(query)
    elif media_type == "TV Show":
        results = search_tv(query)
    else:
        results = search_by_actor(query)

    try:
        results = sorted(results, key=lambda x: x.get("cineselectRating", 0), reverse=True)
    except:
        pass

    if not results:
        st.error("❌ No results found.")
    else:
        for idx, item in enumerate(results):
            st.divider()
            if item.get("poster") and show_posters:
                # Prefer an actual IMDb ID (e.g., "tt0133093"); fall back across common key variants
                imdb_id_link = str(
                    item.get("imdb")
                    or item.get("imdb_id")
                    or item.get("imdbID")
                    or ""
                ).strip()
                poster_url = item["poster"]
                if imdb_id_link.startswith("tt"):
                    st.markdown(
                        f'<a href="https://www.imdb.com/title/{imdb_id_link}/" target="_blank" rel="noopener">'
                        f'<img src="{poster_url}" width="180"/></a>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.image(poster_url, width=180)

            st.markdown(f"**{idx+1}. {item['title']} ({item.get('year', '—')})**")

            imdb_val = item.get("imdbRating")
            if imdb_val in (None, "", "N/A") or (isinstance(imdb_val, (int, float)) and float(imdb_val) == 0.0):
                imdb_display = "N/A"
            else:
                try:
                    imdb_display = f"{float(imdb_val):.1f}"
                except:
                    imdb_display = "N/A"

            rt_val = item.get("rt", 0)
            rt_display = f"{int(rt_val)}%" if isinstance(rt_val, (int, float)) and rt_val > 0 else "N/A"
            st.markdown(f"⭐ IMDb: {imdb_display} &nbsp;&nbsp; 🍅 RT: {rt_display}", unsafe_allow_html=True)

            slider_key = f"stars_{item['id']}"
            manual_key = f"manual_{item['id']}"
            slider_val = st.slider("🎯 CineSelect Rating:", 1, 10000, st.session_state.get(slider_key, 5000), step=10, key=slider_key)
            manual_val = st.number_input("Manual value:", min_value=1, max_value=10000, value=slider_val, step=1, key=manual_key)

            if st.button("Add to Favorites", key=f"btn_{item['id']}"):
                media_key = "movie" if media_type == "Movie" else ("show" if media_type == "TV Show" else "movie")
                # 1) IMDb ID garanti altına al
                imdb_id = (item.get("imdb") or "").strip()
                if not imdb_id or imdb_id == "tt0000000":
                    imdb_id = get_imdb_id_from_tmdb(
                        title=item["title"],
                        year=item.get("year"),
                        is_series=(media_key == "show"),
                    )

                # IMDb ID doğrulama/düzeltme
                imdb_id = validate_imdb_id(imdb_id, item["title"], item.get("year")) or imdb_id

                # 2) IMDb/RT puanlarını getir (ÖNCE yerel CSV, yoksa OMDb-ID, o da yoksa Title/Year)
                stats = {}
                raw_id = {}
                raw_title = {}
                source = None

                # a) yerel CSV
                seed_hit = read_seed_rating(imdb_id)
                if seed_hit and (seed_hit.get("imdb_rating") or seed_hit.get("rt")):
                    stats = {"imdb_rating": seed_hit.get("imdb_rating"), "rt": seed_hit.get("rt")}
                    source = "CSV"

                # b) CSV yoksa/eksikse OMDb by ID
                if not source:
                    if imdb_id:
                        stats = get_ratings(imdb_id) or {}
                        raw_id = (stats.get("raw") or {})
                        source = "CSV/OMDb-ID" if raw_id else None  # get_ratings CSV'den dönerse raw boş kalabilir

                # OMDb-ID fallback: if both ratings are 0, try fetch_ratings by title/year
                if not stats or (float(stats.get("imdb_rating") or 0) == 0.0 and int(stats.get("rt") or 0) == 0):
                    ir, rt, raw_title = fetch_ratings(item["title"], item.get("year"))
                    stats = {"imdb_rating": ir, "rt": rt}
                    source = "OMDb-title (auto-fallback)"

                imdb_rating = float(stats.get("imdb_rating") or 0.0)
                rt_score    = int(stats.get("rt") or 0)

                # --- Fetch full metadata (directors, cast, genres) ---
                new_meta = fetch_metadata(imdb_id, item["title"], item.get("year"), is_series=(media_key == "show"))

                # 🔎 DEBUG: Kaynak ve ham yanıtlar
                st.write(f"🔍 Source: {source or '—'} | 🆔 IMDb ID: {imdb_id or '—'} | ⭐ IMDb: {imdb_rating} | 🍅 RT: {rt_score}")

                # Extra, user-visible diagnostics
                error_msg = None
                if isinstance(raw_id, dict):
                    error_msg = raw_id.get("Error")
                if not error_msg and isinstance(raw_title, dict):
                    error_msg = raw_title.get("Error")

                if error_msg:
                    st.error(f"OMDb error: {error_msg}. Check OMDB_API_KEY.", icon="🚨")
                elif source == "CSV":
                    st.info("Source: seed_ratings.csv (cached)", icon="📂")
                elif source == "CSV/OMDb-ID":
                    st.info(f"Source: OMDb by IMDb ID ({imdb_id})", icon="🔎")
                else:
                    st.info(f"Source: OMDb by Title/Year ({item['title']} {item.get('year')})", icon="🔎")

                if raw_id:
                    import json as _json
                    st.caption("OMDb by ID (raw JSON)")
                    st.code(_json.dumps(raw_id, ensure_ascii=False, indent=2))
                if raw_title:
                    import json as _json
                    st.caption("OMDb by title (raw JSON)")
                    st.code(_json.dumps(raw_title, ensure_ascii=False, indent=2))

                # 3) Firestore'a yaz
                doc_data = {
                    "id": item["id"],
                    "title": item["title"],
                    "year": item.get("year"),
                    "imdb": imdb_id,
                    "poster": item.get("poster"),
                    "imdbRating": imdb_rating,                 # ✅ eklendi
                    "rt": rt_score,                            # ✅ CSV/OMDb’den gelen kesin değer
                    "cineselectRating": manual_val,
                    "type": media_key,
                    "directors": new_meta.get("directors", []) if new_meta else [],
                    "cast": new_meta.get("cast", []) if new_meta else [],
                    "genres": new_meta.get("genres", []) if new_meta else [],
                }
                # For TV shows, add created_by field if present
                if media_key == "show" and new_meta and "created_by" in new_meta:
                    doc_data["created_by"] = new_meta["created_by"]
                db.collection("favorites").document(item["id"]).set(doc_data)
                # 4) seed_ratings.csv'ye (yoksa) ekle
                append_seed_rating(
                    imdb_id=imdb_id,
                    title=item["title"],
                    year=item.get("year"),
                    imdb_rating=imdb_rating,
                    rt_score=rt_score,
                )
                # 5) seed_meta.csv'ye de ekle (yoksa)
                append_seed_meta(
                    imdb_id,
                    item["title"],
                    item.get("year"),
                    new_meta if new_meta else {"directors": [], "cast": [], "genres": []}
                )
                st.success(f"✅ {item['title']} added to favorites!")
                # clear search on next run to avoid "modified after instantiation" error
                st.session_state.clear_search = True
                # Let the user see the diagnostics before refresh
                st.toast("Refreshing…", icon="🔄")
                time.sleep(1.2)
                st.rerun()

st.divider()
st.subheader("❤️ Your Favorites")
sort_option = st.selectbox("Sort by:", ["IMDb", "RT", "CineSelect", "Year"], index=2)


#
# Build directors, actors, genres, created_by lists based on selected media_type
if media_type == "Movie":
    source_docs = db.collection("favorites").where("type", "==", "movie").stream()
elif media_type == "TV Show":
    source_docs = db.collection("favorites").where("type", "==", "show").stream()
else:
    source_docs = []

directors = sorted({d for doc in source_docs for d in (doc.to_dict().get("directors") or [])})
if media_type == "Movie":
    source_docs = db.collection("favorites").where("type", "==", "movie").stream()
elif media_type == "TV Show":
    source_docs = db.collection("favorites").where("type", "==", "show").stream()
else:
    source_docs = []
actors = sorted({a for doc in source_docs for a in (doc.to_dict().get("cast") or [])})
if media_type == "Movie":
    source_docs = db.collection("favorites").where("type", "==", "movie").stream()
elif media_type == "TV Show":
    source_docs = db.collection("favorites").where("type", "==", "show").stream()
else:
    source_docs = []
genres = sorted({g for doc in source_docs for g in (doc.to_dict().get("genres") or [])})

# For created_by: only for TV Show
created_by_list = []
if media_type == "TV Show":
    source_docs = db.collection("favorites").where("type", "==", "show").stream()
    created_by_list = sorted({cb for doc in source_docs for cb in (doc.to_dict().get("created_by") or [])})

## --- Unified filter row (stateless, no query_params) ---
if media_type == "TV Show":
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        default_director = (
            [st.session_state["filter_director"]]
            if st.session_state.get("filter_director") in directors
            else []
        )
        selected_directors = st.multiselect(
            "🎬 Filter by Director", directors, default=default_director,
            key="director_multiselect",
            on_change=clear_filter_if_empty, args=("filter_director",)
        )
    with col2:
        default_actor = (
            [st.session_state["filter_actor"]]
            if st.session_state.get("filter_actor") in actors
            else []
        )
        selected_actors = st.multiselect(
            "🎭 Filter by Actor", actors, default=default_actor,
            key="actor_multiselect",
            on_change=clear_filter_if_empty, args=("filter_actor",)
        )
    with col3:
        default_genre = (
            [st.session_state["filter_genre"]]
            if st.session_state.get("filter_genre") in genres
            else []
        )
        selected_genres = st.multiselect(
            "🎞 Filter by Genre", genres, default=default_genre,
            key="genre_multiselect",
            on_change=clear_filter_if_empty, args=("filter_genre",)
        )
    with col4:
        default_created_by = (
            [st.session_state["filter_created_by"]]
            if st.session_state.get("filter_created_by") in created_by_list
            else []
        )
        selected_created_by = st.multiselect(
            "🎬 Filter by Created by", created_by_list, default=default_created_by,
            key="createdby_multiselect",
            on_change=clear_filter_if_empty, args=("filter_created_by",)
        )
else:
    col1, col2, col3 = st.columns(3)
    with col1:
        default_director = (
            [st.session_state["filter_director"]]
            if st.session_state.get("filter_director") in directors
            else []
        )
        selected_directors = st.multiselect(
            "🎬 Filter by Director", directors, default=default_director,
            key="director_multiselect",
            on_change=clear_filter_if_empty, args=("filter_director",)
        )
    with col2:
        default_actor = (
            [st.session_state["filter_actor"]]
            if st.session_state.get("filter_actor") in actors
            else []
        )
        selected_actors = st.multiselect(
            "🎭 Filter by Actor", actors, default=default_actor,
            key="actor_multiselect",
            on_change=clear_filter_if_empty, args=("filter_actor",)
        )
    with col3:
        default_genre = (
            [st.session_state["filter_genre"]]
            if st.session_state.get("filter_genre") in genres
            else []
        )
        selected_genres = st.multiselect(
            "🎞 Filter by Genre", genres, default=default_genre,
            key="genre_multiselect",
            on_change=clear_filter_if_empty, args=("filter_genre",)
        )
    
def get_sort_key(fav):
    try:
        if sort_option == "IMDb":
            return float(fav.get("imdbRating", 0) or 0)
        elif sort_option == "RT":
            return float(fav.get("rt", 0))
        elif sort_option == "CineSelect":
            return fav.get("cineselectRating", 0)
        elif sort_option == "Year":
            return int(fav.get("year", 0))
    except:
        return 0

def show_favorites(fav_type, label):
    # --- Ensure session_state filter keys are cleared if widget selections are empty ---
    # EXPLICIT resets: if any selected_x is empty, reset session_state and reload all
    global selected_directors, selected_actors, selected_genres, selected_created_by
    if "selected_directors" in globals() and not selected_directors:
        st.session_state["filter_director"] = None
    if "selected_actors" in globals() and not selected_actors:
        st.session_state["filter_actor"] = None
    if "selected_genres" in globals() and not selected_genres:
        st.session_state["filter_genre"] = None
    if fav_type == "show" and "selected_created_by" in globals() and not selected_created_by:
        st.session_state["filter_created_by"] = None
    clear_filter_if_empty("filter_director")
    clear_filter_if_empty("filter_actor")
    clear_filter_if_empty("filter_genre")
    clear_filter_if_empty("filter_created_by")
    # --- Unified filtering logic: apply filters across movies and shows together if any filter is active ---
    # Gather all favorites if any filter is active, else only per section.
    fd = st.session_state.get("filter_director")
    fa = st.session_state.get("filter_actor")
    fg = st.session_state.get("filter_genre")
    fcb = st.session_state.get("filter_created_by")
    # Combine all selected filters (from multiselects and single-click)
    any_filter_active = (
        (selected_directors if "selected_directors" in globals() else []) or
        (selected_actors if "selected_actors" in globals() else []) or
        (selected_genres if "selected_genres" in globals() else []) or
        (fav_type == "show" and "selected_created_by" in globals() and selected_created_by) or
        fd or fa or fg or (fav_type == "show" and fcb)
    )
    # If any filter is active, fetch all movies+shows together, else only current section
    if any_filter_active:
        # Get all favorites
        all_favs = [doc.to_dict() for doc in db.collection("favorites").stream()]
        # Apply filters
        filtered = all_favs
        # Multiselects
        if "selected_directors" in globals() and selected_directors:
            filtered = [f for f in filtered if any(d in (f.get("directors") or []) for d in selected_directors)]
        if "selected_actors" in globals() and selected_actors:
            filtered = [f for f in filtered if any(a in (f.get("cast") or []) for a in selected_actors)]
        if "selected_genres" in globals() and selected_genres:
            filtered = [f for f in filtered if any(g in (f.get("genres", []) or []) for g in selected_genres)]
        # created_by only for shows
        if fav_type == "show" and "selected_created_by" in globals() and selected_created_by:
            filtered = [f for f in filtered if any(cb in (f.get("created_by") or []) for cb in selected_created_by)]
        # Single-click session_state filters
        if fd:
            filtered = [f for f in filtered if fd in f.get("directors",[])]
        if fa:
            filtered = [f for f in filtered if fa in f.get("cast",[])]
        if fg:
            filtered = [f for f in filtered if fg in f.get("genres",[])]
        if fav_type == "show" and fcb:
            filtered = [f for f in filtered if fcb in (f.get("created_by") or [])]
        # Now, split back by type
        favorites = [f for f in filtered if (f.get("type", "").lower() == fav_type)]
        favorites = sorted(favorites, key=get_sort_key, reverse=True)
    else:
        docs = db.collection("favorites").where("type", "==", fav_type).stream()
        favorites = sorted([doc.to_dict() for doc in docs], key=get_sort_key, reverse=True)

    st.markdown(f"### 📁 {label}")
    for idx, fav in enumerate(favorites):
        imdb_val = fav.get("imdbRating")
        if imdb_val in (None, "", "N/A") or (isinstance(imdb_val, (int, float)) and float(imdb_val) == 0.0):
            imdb_display = "N/A"
        else:
            try:
                imdb_display = f"{float(imdb_val):.1f}"
            except:
                imdb_display = "N/A"
        rt_display = f"{fav['rt']}%" if isinstance(fav["rt"], (int, float)) else "N/A"
        cols = st.columns([1, 5, 1, 1])
        with cols[0]:
            if show_posters and fav.get("poster"):
                imdb_id_link = str(
                    fav.get("imdb") or fav.get("imdb_id") or fav.get("imdbID") or ""
                ).strip()
                poster_url = fav["poster"]
                if imdb_id_link and imdb_id_link.startswith("tt"):
                    st.markdown(
                        f'<a href="https://www.imdb.com/title/{imdb_id_link}/" target="_blank" rel="noopener">'
                        f'<img src="{poster_url}" width="120"/></a>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.image(poster_url, width=120)
        with cols[1]:
            st.markdown(f"**{idx+1}. {fav['title']} ({fav['year']})** | ⭐ IMDb: {imdb_display} | 🍅 RT: {rt_display} | 🎯 CS: {fav.get('cineselectRating', 'N/A')}")

            # --- Directors / Cast / Genres as inline markdown links ---
            def link_list(items, filter_type, emoji, label):
                if not items:
                    return
                filter_param = f"filter_{filter_type}"
                links = [
                    f"<a href='?{filter_param}={urllib.parse.quote(name)}' "
                    f"style='color:#3498db; text-decoration:underline; margin-right:8px;'>{name}</a>"
                    for name in items
                ]
                st.markdown(f"{emoji} <b>{label}:</b> " + " ".join(links), unsafe_allow_html=True)

            # Directors + Created by (for shows, combine both as Created by + Directors)
            if fav.get("type") == "show":
                # Merge created_by and directors for display, preserving unique order
                cb = fav.get("created_by", []) or []
                dirs = fav.get("directors", []) or []
                merged = []
                seen = set()
                for name in cb + dirs:
                    if name and name not in seen:
                        merged.append(name)
                        seen.add(name)
                if merged:
                    link_list(merged, "created_by", "🎬", "Created by + Directors")
            else:
                if fav.get("directors"):
                    link_list(fav.get("directors", []), "director", "🎬", "Directors")
            # Cast
            if fav.get("cast"):
                link_list(fav["cast"], "actor", "🎭", "Cast")
            # Genres
            if fav.get("genres"):
                link_list(fav["genres"], "genre", "📚", "Genres")

            # --- IMDb&RT ve Full Meta butonlarını yan yana ve küçük göster ---
            btn_cols = st.columns([1, 1])
            with btn_cols[0]:
                if st.button("🔄 IMDb&RT", key=f"refresh_{fav['id']}", use_container_width=True):
                    imdb_id = (fav.get("imdb") or "").strip()
                    title = fav.get("title")
                    year = fav.get("year")
                    is_series = (fav.get("type") == "show")
                    # 1) IMDb ID guarantee
                    if not imdb_id or imdb_id == "tt0000000":
                        imdb_id = get_imdb_id_from_tmdb(title, year, is_series=is_series)
                        st.info(f"🎬 IMDb ID TMDb'den alındı: {imdb_id}")
                    # IMDb ID doğrulama/düzeltme (OMDb sorgusundan önce)
                    imdb_id = validate_imdb_id(imdb_id, title, year) or imdb_id

                    stats = {}
                    raw_id = {}
                    raw_title = {}
                    source = None

                    # 2a) Try seed_ratings.csv
                    seed_hit = read_seed_rating(imdb_id)
                    if seed_hit and (seed_hit.get("imdb_rating") or seed_hit.get("rt")):
                        stats = {"imdb_rating": seed_hit.get("imdb_rating"), "rt": seed_hit.get("rt")}
                        source = "CSV"

                    # 2b) If missing/empty → OMDb by ID
                    if not source:
                        if imdb_id:
                            stats = get_ratings(imdb_id) or {}
                            raw_id = (stats.get("raw") or {})
                            source = "CSV/OMDb-ID" if raw_id else None

                    # OMDb-ID fallback: if both ratings are 0, try fetch_ratings by title/year
                    if not stats or (float(stats.get("imdb_rating") or 0) == 0.0 and int(stats.get("rt") or 0) == 0):
                        ir, rt, raw_title = fetch_ratings(title, year)
                        stats = {"imdb_rating": ir, "rt": rt}
                        source = "OMDb-title (auto-fallback)"

                    imdb_rating = float(stats.get("imdb_rating") or 0.0)
                    rt_score = int(stats.get("rt") or 0)

                    # --- Debug log before updating Firestore ---
                    st.info(f"🎬 Refresh Debug → Title='{title}' ({year}) | IMDb ID={imdb_id} | IMDb={imdb_rating} | RT={rt_score}")

                    # Update Firestore
                    db.collection("favorites").document(fav["id"]).update({
                        "imdb": imdb_id,
                        "imdbRating": imdb_rating,
                        "rt": rt_score,
                    })

                    # Update seed_ratings.csv
                    append_seed_rating(
                        imdb_id=imdb_id,
                        title=title,
                        year=year,
                        imdb_rating=imdb_rating,
                        rt_score=rt_score,
                    )

                    st.success(f"✅ {title} IMDb & RT yenilendi. (IMDb={imdb_rating}, RT={rt_score}%)")
                    st.rerun()
            with btn_cols[1]:
                if st.button("🎬 Full Meta", key=f"fullmeta_{fav['id']}", use_container_width=True):
                    imdb_id = (fav.get("imdb") or "").strip()
                    title = fav.get("title")
                    year = fav.get("year")
                    is_series = (fav.get("type") == "show")

                    new_meta = fetch_metadata(imdb_id, title, year, is_series=is_series)
                    if new_meta:
                        update_data = {
                            "directors": new_meta.get("directors", []),
                            "cast": new_meta.get("cast", []),
                            "genres": new_meta.get("genres", []),
                        }
                        # For TV shows, add or update created_by field
                        if is_series and "created_by" in new_meta:
                            update_data["created_by"] = new_meta["created_by"]
                        elif is_series:
                            update_data["created_by"] = []
                        db.collection("favorites").document(fav["id"]).update(update_data)
                        append_seed_meta(imdb_id, title, year, new_meta)
                        st.success(f"✅ Metadata updated for {title} ({year})")
                        st.rerun()
        with cols[2]:
            if st.button("❌", key=f"remove_{fav['id']}"):
                db.collection("favorites").document(fav["id"]).delete()
                st.rerun()
        with cols[3]:
            if st.button("✏️", key=f"edit_{fav['id']}"):
                st.session_state[f"edit_mode_{fav['id']}"] = True

        if st.session_state.get(f"edit_mode_{fav['id']}", False):
            s_key = f"slider_{fav['id']}"
            i_key = f"input_{fav['id']}"
            current = _clamp_cs(fav.get("cineselectRating", 5000))
            if s_key not in st.session_state:
                st.session_state[s_key] = current
            if i_key not in st.session_state:
                st.session_state[i_key] = current

            # --- Editable fields for directors, cast, genres (single-line text_area) ---
            dir_key = f"edit_dirs_{fav['id']}"
            cast_key = f"edit_cast_{fav['id']}"
            genres_key = f"edit_genres_{fav['id']}"
            # Pre-populate with joined string
            if dir_key not in st.session_state:
                st.session_state[dir_key] = "; ".join(fav.get("directors", []))
            if cast_key not in st.session_state:
                st.session_state[cast_key] = "; ".join(fav.get("cast", []))
            if genres_key not in st.session_state:
                st.session_state[genres_key] = "; ".join(fav.get("genres", []))

            st.slider(
                "🎯 CS:", 1, 10000, st.session_state[s_key], step=1,
                key=s_key, on_change=_sync_cs_from_slider, args=(s_key, i_key)
            )
            st.number_input(
                "CS (manuel):", min_value=1, max_value=10000, value=st.session_state[i_key], step=1,
                key=i_key, on_change=_sync_cs_from_input, args=(i_key, s_key)
            )

            # Compact editable text areas (single-line each)
            edit_cols = st.columns(3)
            with edit_cols[0]:
                st.text_area(
                    "Directors", value=st.session_state[dir_key], key=dir_key,
                    height=28, label_visibility="visible"
                )
            with edit_cols[1]:
                st.text_area(
                    "Cast", value=st.session_state[cast_key], key=cast_key,
                    height=28, label_visibility="visible"
                )
            with edit_cols[2]:
                st.text_area(
                    "Genres", value=st.session_state[genres_key], key=genres_key,
                    height=28, label_visibility="visible"
                )

            cols_edit = st.columns([1, 1, 2])
            with cols_edit[0]:
                if st.button("✅ Kaydet", key=f"save_{fav['id']}"):
                    new_val = _clamp_cs(st.session_state.get(i_key, st.session_state.get(s_key, current)))
                    # Parse directors/cast/genres from textareas (split on ";")
                    dir_list = [d.strip() for d in (st.session_state.get(dir_key, "") or "").split(";") if d.strip()]
                    cast_list = [c.strip() for c in (st.session_state.get(cast_key, "") or "").split(";") if c.strip()]
                    genres_list = [g.strip() for g in (st.session_state.get(genres_key, "") or "").split(";") if g.strip()]

                    db.collection("favorites").document(fav["id"]).update({
                        "cineselectRating": new_val,
                        "directors": dir_list,
                        "cast": cast_list,
                        "genres": genres_list,
                    })
                    # Also update seed_meta.csv
                    append_seed_meta(
                        fav.get("imdb") or fav.get("imdb_id") or "",
                        fav.get("title"),
                        fav.get("year"),
                        {
                            "directors": dir_list,
                            "cast": cast_list,
                            "genres": genres_list,
                        }
                    )
                    st.success(f"✅ {fav['title']} güncellendi.")
                    st.session_state[f"edit_mode_{fav['id']}"] = False
                    st.rerun()
            with cols_edit[1]:
                if st.button("📌 Başa tuttur", key=f"pin_{fav['id']}"):
                    # Aynı türdeki favorilerde en yüksek CS'yi bul, 10 ekle (üst sınır 10000)
                    cur_max = 0
                    for d in db.collection("favorites").where("type", "==", fav_type).stream():
                        try:
                            cs = int((d.to_dict() or {}).get("cineselectRating") or 0)
                            if cs > cur_max:
                                cur_max = cs
                        except Exception:
                            pass
                    pin_val = _clamp_cs(cur_max + 10)
                    db.collection("favorites").document(fav["id"]).update({"cineselectRating": pin_val})
                    st.session_state[s_key] = pin_val
                    st.session_state[i_key] = pin_val
                    st.success(f"📌 {fav['title']} en üste taşındı (CS={pin_val}).")
                    st.rerun()



if media_type == "Movie":
    show_favorites("movie", "Favorite Movies")
elif media_type == "TV Show":
    show_favorites("show", "Favorite TV Shows")

st.markdown("---")
if st.button("🔝 Go to Top Again"):
    st.rerun()

st.markdown("<p style='text-align: center; color: gray;'>Created by <b>SS</b></p>", unsafe_allow_html=True)
