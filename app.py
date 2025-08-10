import streamlit as st
import requests
import firebase_admin
from firebase_admin import credentials, firestore
import json
import base64
import os
import time
# --- OMDb (IMDb & Rotten Tomatoes) ---
OMDB_API_KEY = os.getenv("OMDB_API_KEY", "")
_omdb_cache = {}  # { "tt0105323": {"imdb": 8.0, "rt": 92} }
@st.cache_data(ttl=60*60*24, show_spinner=False)  # 24 saat cache
def fetch_ratings_from_omdb(imdb_id: str):
    """IMDb ID ('tt...') ver, IMDb puanı (float) ve RT yüzdesi (int) döndür."""
    if not imdb_id or not isinstance(imdb_id, str) or not imdb_id.startswith("tt"):
        return {"imdb": 0.0, "rt": 0}

    if imdb_id in _omdb_cache:
        return _omdb_cache[imdb_id]

    if not OMDB_API_KEY:
        data = {"imdb": 0.0, "rt": 0}
        _omdb_cache[imdb_id] = data
        return data

    url = f"https://www.omdbapi.com/?i={imdb_id}&apikey={OMDB_API_KEY}&tomatoes=true"
    r = requests.get(url, timeout=6)  # OMDb API isteği

    # JSON parse güvenliği
    try:
        data = r.json()
    except Exception:
        data = {}

    # Limit / hata kontrolü
    if (r.status_code != 200) or ("Error" in data and "limit" in str(data.get("Error", "")).lower()):
    print(f"[OMDb] limit/status: {r.status_code} body={data}")
    return {}
        
        # IMDb
        imdb_val = data.get("imdbRating")
        try:
            imdb_float = float(imdb_val) if imdb_val and imdb_val != "N/A" else 0.0
        except Exception:
            imdb_float = 0.0

        # Rotten Tomatoes (OMDb Patreon anahtarı yoksa çoğu zaman gelmez)
        rt_pct = 0
        for x in data.get("Ratings", []):
            if x.get("Source") == "Rotten Tomatoes":
                v = x.get("Value")  # "92%" gibi
                try:
                    rt_pct = int(str(v).replace("%", "")) if v and v != "N/A" else 0
                except Exception:
                    rt_pct = 0
                break

        data = {"imdb": imdb_float, "rt": rt_pct}
        _omdb_cache[imdb_id] = data
        return data
    except Exception:
        return {"imdb": 0.0, "rt": 0}

def resolve_ratings_for_item(item: dict):
    """
    item['imdb'] sende çoğu kayıt için 'tt...' (IMDb ID).
    Eğer zaten puan (float) ise onu kullan; 'tt...' ise OMDb'dan çek.
    Döndürür: (imdb_display_str, rt_display_str, imdb_float, rt_int)
    """
    imdb_display, rt_display = "N/A", "N/A"
    imdb_float, rt_int = 0.0, 0

    val = item.get("imdb")

    # imdb alanı puan olarak tutulmuşsa
    if isinstance(val, (int, float)):
        imdb_float = float(val)
        imdb_display = f"{imdb_float:.1f}" if imdb_float > 0 else "N/A"

    # imdb alanı 'tt...' ise OMDb'dan çek
    elif isinstance(val, str) and val.startswith("tt"):
        ratings = fetch_ratings_from_omdb(val)
        imdb_float = ratings["imdb"]
        rt_int = ratings["rt"]
        imdb_display = f"{imdb_float:.1f}" if imdb_float > 0 else "N/A"
        rt_display = f"{rt_int}%" if rt_int > 0 else "N/A"

    # item['rt'] sayısal ise onu tercih et (favorilerde önceden yazılmış olabilir)
    if rt_display == "N/A":
        if isinstance(item.get("rt"), (int, float)) and item["rt"] > 0:
            rt_int = int(item["rt"])
            rt_display = f"{rt_int}%"

    return imdb_display, rt_display, imdb_float, rt_int
# Firebase yapılandırması
def to_export_item(fav: dict) -> dict:
    # imdb_id'yi çıkar
    imdb_id = fav.get("imdb_id") or (
        fav.get("imdb") if isinstance(fav.get("imdb"), str) and str(fav.get("imdb")).startswith("tt")
        else ""
    )

    # yıl -> int
    try:
        year_int = int(fav.get("year", 0) or 0)
    except Exception:
        year_int = 0

    # imdb puanı -> float (opsiyonel: ayrı anahtara yazacağız)
    try:
        imdb_rating = round(float(fav.get("imdb") or 0), 1)
    except Exception:
        imdb_rating = 0.0

    return {
        "id": fav.get("id", imdb_id or ""),
        "title": fav.get("title", ""),
        "year": year_int,
        "poster": fav.get("poster", ""),
        "type": fav.get("type", "movie"),
        "imdb": imdb_id,                 # ← JSON’da TT kimliği HER ZAMAN buraya
        "rt": int(fav.get("rt", 0) or 0),
        "imdbRating": imdb_rating        # (opsiyonel) puan ayrı anahtar
    }
def get_firestore():
    if not firebase_admin._apps:
        firebase_config = os.getenv("FIREBASE_ADMINSDK_JSON")
        if firebase_config:
            cred = credentials.Certificate(json.loads(firebase_config))
        else:
            cred = credentials.Certificate("firebase-adminsdk.json")
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = get_firestore()
FAVORITES_FILE = "favorites.json"
favorites = {"movies": [], "series": []}  # Ön tanım
# Eğer favorites.json dosyası varsa, onu yükle
if os.path.exists(FAVORITES_FILE):
    try:
        with open(FAVORITES_FILE, "r", encoding="utf-8") as f:
            favorites = json.load(f)
    except json.JSONDecodeError:
        pass  # default 'favorites' ile devam et
# Favoriler dosyasını oku (yoksa boş yapı oluştur)
    # Bozuk veya eksik kayıtları ayıkla
    for key in ["movies", "series"]:
        cleaned = []
        for item in favorites.get(key, []):
            if item and isinstance(item, dict) and "imdb" in item and "title" in item:
                cleaned.append(item)
        favorites[key] = cleaned
        # CineSelect puanına göre (büyükten küçüğe), sonra yıl ve başlığa göre sırala
        favorites[key].sort(
            key=lambda x: int(x.get("cineselectRating", 0) or 0),
            reverse=True
        )
# IMDb ID'si eksik olanları TMDB'den otomatik doldur
updated_count = 0
for key in ["movies", "series"]:
    for item in favorites.get(key, []):
        imdb_id = (item.get("imdb") or "").strip()
        if not imdb_id or imdb_id == "tt0000000":
            title = item.get("title", "")
            poster = item.get("poster", "")
            year = (str(item.get("year", "")).strip() or None)
            is_series = (key == "series") or (item.get("type") == "show")

            new_imdb = get_imdb_id(
                title=title,
                poster_url=poster,
                year=year,
                is_series=is_series
            )

            if new_imdb and new_imdb != "tt0000000":
                item["imdb"] = new_imdb
                updated_count += 1
                print(f"✅ IMDb güncellendi: {title} -> {new_imdb}")
            else:
                print(f"⚠ IMDb bulunamadı: {title}")

# Güncelleme yapıldıysa dosyayı geri yaz
# Temizleme + sıralama sonrası favorites.json'u her koşulda yaz
for key in ["movies", "series"]:
    favorites[key].sort(
        key=lambda x: int(x.get("cineselectRating", 0) or 0),
        reverse=True
    )
with open(FAVORITES_FILE, "w", encoding="utf-8") as f:
    json.dump(favorites, f, ensure_ascii=False, indent=4)
print("💾 favorites.json temizlenip sıralı şekilde kaydedildi.")
# Tek tek uyarı
for key in ["movies", "series"]:
    for item in favorites.get(key, []):
        imdb_id = item.get("imdb", "").strip()
        if not imdb_id or imdb_id == "tt0000000":
            print(f"❌ '{item.get('title', 'Bilinmeyen')}' ({key}) yüklenemedi.")

# Toplam say ve listele
failed_items = []
for key in ["movies", "series"]:
    for item in favorites.get(key, []):
        imdb_id = (item.get("imdb") or "").strip()
        if not imdb_id or imdb_id == "tt0000000":
            failed_items.append(f"{item.get('title','Bilinmeyen')} [{key}]")

if failed_items:
    print(f"❌ Toplam yüklenemeyen kayıt: {len(failed_items)}")
    for name in failed_items:
        print(f"   - {name}")
else:
    print("✅ Tüm kayıtlar geçerli IMDb ID ile yüklendi.")
# TMDB API Key
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "3028d7f0a392920b78e3549d4e6a66ec")
SEARCH_URL = "https://api.themoviedb.org/3/search/multi"
EXTERNAL_IDS_URL = "https://api.themoviedb.org/3/{media_type}/{tmdb_id}/external_ids"
POSTER_BASE = "https://image.tmdb.org/t/p/w500"

def get_imdb_id(title, poster_url="", year=None, is_series=False):
    """IMDb ID alma (retry + backoff + timeout ile)"""
    params = {
        "api_key": TMDB_API_KEY,
        "query": title,
        "year": year if not is_series else None,
        "first_air_date_year": year if is_series else None,
    }

    try:
        # --- SEARCH: retry + backoff ---
        for attempt in range(4):
            res = requests.get(SEARCH_URL, params=params, timeout=6)
            if res.status_code == 429:
                wait = int(res.headers.get("Retry-After", "4"))
                time.sleep(min(wait, 10))
                continue
            try:
                res.raise_for_status()
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2 * (attempt + 1))

        results = res.json().get("results", [])
        if not results:
            return "tt0000000"

        match = next(
            (r for r in results if r.get("poster_path") and poster_url and r["poster_path"] in poster_url),
            results[0]
        )

        tmdb_id = match["id"]
        media_type = match.get("media_type", "tv" if is_series else "movie")
        external_url = EXTERNAL_IDS_URL.format(media_type=media_type, tmdb_id=tmdb_id)

        # --- EXTERNAL IDS: retry + backoff ---
        for attempt in range(4):
            ext_res = requests.get(external_url, params={"api_key": TMDB_API_KEY}, timeout=6)
            if ext_res.status_code == 429:
                wait = int(ext_res.headers.get("Retry-After", "4"))
                time.sleep(min(wait, 10))
                continue
            try:
                ext_res.raise_for_status()
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2 * (attempt + 1))

        return ext_res.json().get("imdb_id", "tt0000000")

    except Exception as e:
        print(f"❌ IMDb ID alınırken hata ({title}): {str(e)}")
        return "tt0000000"
        print(f"❌ IMDb ID alınırken hata ({title}): {str(e)}")
        return "tt0000000"
def _norm_item_from_tmdb(r, media_type):
    """TMDB sonucu -> uygulama formatı."""
    if media_type == "movie":
        title = r.get("title") or r.get("name") or ""
        year = (r.get("release_date") or "")[:4]
    else:  # "tv"
        title = r.get("name") or r.get("title") or ""
        year = (r.get("first_air_date") or "")[:4]

    poster = f"{POSTER_BASE}{r['poster_path']}" if r.get("poster_path") else ""
    imdb_id = get_imdb_id(title=title, poster_url=poster, year=year, is_series=(media_type == "tv"))

    return {
        "id": f"tmdb{r.get('id')}",
        "title": title,
        "year": year,
        "imdb": imdb_id,
        "poster": poster,
        "rt": 0,                    # İstersen sonra OMDb ile doldururuz
        "cineselectRating": 5000,   # Başlangıç değeri; slider ile güncellersin
        "type": "movie" if media_type == "movie" else "show"
    }

def search_movie(query: str):
    """Film araması."""
    url = "https://api.themoviedb.org/3/search/movie"
    res = requests.get(url, params={"api_key": TMDB_API_KEY, "query": query})
    res.raise_for_status()
    results = res.json().get("results", [])[:20]
    return [_norm_item_from_tmdb(r, "movie") for r in results]

def search_tv(query: str):
    """Dizi (TV) araması."""
    url = "https://api.themoviedb.org/3/search/tv"
    res = requests.get(url, params={"api_key": TMDB_API_KEY, "query": query})
    res.raise_for_status()
    results = res.json().get("results", [])[:20]
    return [_norm_item_from_tmdb(r, "tv") for r in results]

def search_by_actor(query: str):
    """Oyuncu araması: kişinin 'known_for' listesinden film/dizi döndürür."""
    url = "https://api.themoviedb.org/3/search/person"
    res = requests.get(url, params={"api_key": TMDB_API_KEY, "query": query})
    res.raise_for_status()
    people = res.json().get("results", [])
    items = []
    for p in people[:5]:
        for k in p.get("known_for", [])[:10]:
            if k.get("media_type") == "movie":
                items.append(_norm_item_from_tmdb(k, "movie"))
            elif k.get("media_type") == "tv":
                items.append(_norm_item_from_tmdb(k, "tv"))
    return items

def push_favorites_to_github():
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        st.warning("⚠️ GITHUB_TOKEN environment variable is missing!")
        st.error("❌ GitHub token bulunamadı. Environment variable ayarlanmalı.")
        return

    repo_owner = "serkansu"
    repo_name = "cineselect-addon"
    file_path = "favorites.json"
    commit_message = "Update favorites.json via Streamlit sync"

    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }

    with open("favorites.json", "rb") as f:
        content = f.read()
    encoded_content = base64.b64encode(content).decode("utf-8")

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        sha = response.json()["sha"]
    elif response.status_code == 404:
        sha = None
    else:
        st.error(f"❌ GitHub API erişim hatası: {response.status_code}")
        return

    payload = {
        "message": commit_message,
        "content": encoded_content,
        "branch": "main"
    }
    if sha:
        payload["sha"] = sha

    put_response = requests.put(url, headers=headers, json=payload)
    if put_response.status_code in [200, 201]:
        st.success("✅ GitHub'a başarılı şekilde push edildi.")
    else:
        st.error(f"❌ Push başarısız: {put_response.status_code}")
        try:
            st.code(put_response.json())
        except:
            st.write("Yanıt alınamadı.")

def create_favorites_json():
    """Firestore'dan verileri çekip IMDb ID'leri düzeltilmiş favorites.json oluşturur"""
    favorites_data = {"movies": [], "series": []}

    for doc in db.collection("favorites").stream():
        item = doc.to_dict()

        # --- TYPE NORMALIZATION ---
        raw_type = str(item.get("type", item.get("media_type", ""))).strip().lower()
        if raw_type in ("movie", "film"):
            norm_type = "movie"
        elif raw_type in ("show", "tv", "series", "tvshow"):
            norm_type = "show"
        else:
            # emin olamıyorsak default movie
            norm_type = "movie"
        item["type"] = norm_type

        # (İSTEĞE BAĞLI) Firebase içindeki kirli kaydı da düzelt
        try:
            if item.get("type") != raw_type:
                db.collection("favorites").document(doc.id).update({"type": norm_type})
        except Exception:
            pass

        # --- BURASI EXCEPT'İN DIŞINDA OLMALI ---
        # Eksik/geçersiz IMDb ID varsa yeniden al
        if (
            not item.get("imdb")
            or isinstance(item.get("imdb"), (int, float))
            or item.get("imdb") == "tt0000000"
        ):
            is_series = item.get("type", "").lower() in ["show", "series"]
            item["imdb"] = get_imdb_id(
                title=item.get("title", ""),
                poster_url=item.get("poster", ""),
                year=item.get("year", 0),
                is_series=is_series,
            )

        # Export formatına çevir ve listeye ekle
        exp = to_export_item(item)
        if exp["type"] == "movie":
            favorites_data["movies"].append(exp)
        else:
            favorites_data["series"].append(exp)

    # --- Döngü BİTTİKTEN SONRA sanitize ---
    favorites_data["movies"] = [
        {**it, "type": "movie"}
        for it in favorites_data.get("movies", [])
        if str(it.get("type", "")).strip().lower() in ("movie", "")
    ]
    favorites_data["series"] = [
        {**it, "type": "show"}
        for it in favorites_data.get("series", [])
        if str(it.get("type", "")).strip().lower() in ("show", "tv", "series")
    ]

    try:
        with open("favorites.json", "w", encoding="utf-8") as f:
            json.dump(favorites_data, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        st.error(f"❌ favorites.json oluşturulamadı: {str(e)}")
        return False
def sync_with_firebase(enrich=False, max_updates=50):
    db = get_firestore()
    movies = []
    series = []
    updates = 0
    
    for doc in db.collection("favorites").stream():
        item = doc.to_dict()
        # --- TYPE NORMALIZATION (fix trailing \n etc.) ---
        raw_type = str(item.get("type", item.get("media_type", ""))).strip().lower()
        if raw_type in ("movie", "film"):
            item["type"] = "movie"
        elif raw_type in ("show", "tv", "series", "tvshow"):
            item["type"] = "show"
        else:
            item["type"] = "movie"
        # (opsiyonel) Firebase içindeki kirli değeri de düzelt
        try:
            if item.get("type") != raw_type:
                db.collection("favorites").document(doc.id).update({"type": item["type"]})
        except Exception:
            pass
        # --------------------------------------------------
        if enrich and (not item.get("imdb") or isinstance(item.get("imdb"), (int, float)) or item["imdb"] == "tt0000000"):
            if updates >= max_updates:
                break
        # Bu turda limit doldu; kalanları sonraya bırak
       
        is_series = item.get("type", "").lower() in ["show", "series"]
        imdb_id = get_imdb_id(
            item["title"],
            item.get("poster", ""),
            item.get("year"),
            is_series
        )
        item["imdb"] = imdb_id
        try:
            db.collection("favorites").document(doc.id).update({"imdb": imdb_id})
            updates += 1             # ← IMDb güncellemesi sayacı burada artıyor
        except Exception:
            pass
        updates += 1
        time.sleep(0.1)

        if item["type"] == "movie":
            movies.append(item)
        else:
            series.append(item)
    # --- SANITIZATION BLOCK (2. yazma öncesi) ---
    def sanitize_items(items):
        cleaned = []
        for item in items:
            # type alanını normalize et
            raw_type = str(item.get("type", "")).strip().lower()
            if raw_type in ("movie", "film"):
                item["type"] = "movie"
            elif raw_type in ("show", "tv", "series", "tvshow"):
                item["type"] = "show"
            else:
                item["type"] = "movie"

            # imdb alanını temizle
            if isinstance(item.get("imdb"), str):
                item["imdb"] = item["imdb"].strip()

            # title alanındaki boşlukları ve satır sonlarını temizle
            if isinstance(item.get("title"), str):
                item["title"] = item["title"].strip()

            cleaned.append(item)
        return cleaned

    movies = sanitize_items(movies)
        # --- SANITIZATION BLOCK (2. yazma öncesi) ---
    def sanitize_items(items):
        cleaned = []
        for item in items:
            # type normalize
            raw_type = str(item.get("type", "")).strip().lower()
            if raw_type in ("movie", "film"):
                item["type"] = "movie"
            elif raw_type in ("show", "tv", "series", "tvshow"):
                item["type"] = "show"
            else:
                item["type"] = "movie"

            # basic field trims
            if isinstance(item.get("imdb"), str):
                item["imdb"] = item["imdb"].strip()
            if isinstance(item.get("title"), str):
                item["title"] = item["title"].strip()

            cleaned.append(item)
        return cleaned

    movies = sanitize_items(movies)
    series = sanitize_items(series)

    # güvenlik: yanlış gruba sızanları ele
    movies = [it for it in movies if str(it.get("type","")).strip().lower() == "movie"]
    series = [it for it in series if str(it.get("type","")).strip().lower() == "show"]
    # --------------------------------------------------------------
    with open("favorites.json", "w", encoding="utf-8") as f:
        json.dump({"movies": movies, "series": series}, f, ensure_ascii=False, indent=4)
    st.session_state["favorite_movies"] = movies
    st.session_state["favorite_series"] = series
    st.success("✅ favorites.json güncellendi ve IMDb ID'ler düzeltildi.")

# Streamlit Arayüzü
st.set_page_config(page_title="Serkan's Watchagain Movies & Series ONLINE", layout="wide")
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

    if st.button("🖼️ Toggle Posters"):
        st.session_state["show_posters"] = not st.session_state["show_posters"]

do_enrich = st.checkbox("IMDb ID’leri TMDB’den doldur (limitli, yavaş olabilir)", value=False)

if st.button("🔄 Senkronize Et (Firebase JSON)"):
    sync_with_firebase(enrich=do_enrich, max_updates=50)
    if create_favorites_json():
        push_favorites_to_github()
        st.success("✅ favorites.json senkronize edildi ve GitHub'a pushlandı!")
    else:
        st.error("❌ favorites.json üretilemedi, GitHub'a push edilmedi.")
# ⬇️ Bu satırdan itibaren ekle
try:
    with open("favorites.json", "rb") as f:
        st.download_button(
            "📥 favorites.json indir",
            data=f,
            file_name="favorites.json",
            mime="application/json",
            key="dl_favorites_json",
        )
except FileNotFoundError:
    pass
def show_favorites_count():
    """Firebase'den film ve dizi sayılarını çekip gösterir."""
    try:
        db = get_firestore()
        movie_count = len(list(db.collection("favorites").where("type", "==", "movie").stream()))
        series_count = len(list(db.collection("favorites").where("type", "==", "show").stream()))
        
        st.info(f"🎬 Favorite Movies: **{movie_count}** | 📺 Favorite TV Shows: **{series_count}**")
    except Exception as e:
        st.error(f"❌ Veriler çekilemedi: {str(e)}")

# Streamlit arayüzünde çağırın (üst kısma ekleyin)
show_favorites_count()  # Doğrudan çağırın, içinde butonla tekrar çağırmayın!

show_posters = st.session_state["show_posters"]
media_type = st.radio("Search type:", ["Movie", "TV Show", "Actor/Actress"], horizontal=True)

if "query" not in st.session_state:
    st.session_state.query = ""

query = st.text_input(f"🔍 Search for a {media_type.lower()}", value=st.session_state.query, key="query_input")

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
            if item["poster"] and show_posters:
                st.image(item["poster"], width=180)

            st.markdown(f"**{idx+1}. {item['title']} ({item['year']})**")
            imdb_display, rt_display, imdb_f, rt_i = resolve_ratings_for_item(item)
            rt_display = f"{item['rt']}%" if isinstance(item['rt'], (int, float)) and item['rt'] > 0 else "N/A"
            st.markdown(f"⭐ IMDb: {imdb_display} &nbsp;&nbsp; 🍅 RT: {rt_display}", unsafe_allow_html=True)

            slider_key = f"stars_{item['id']}"
            manual_key = f"manual_{item['id']}"
            slider_val = st.slider("🎯 CineSelect Rating:", 1, 10000, st.session_state.get(slider_key, 5000), step=10, key=slider_key)
            manual_val = st.number_input("Manual value:", min_value=1, max_value=10000, value=slider_val, step=1, key=manual_key)

            if st.button("Add to Favorites", key=f"btn_{item['id']}"):
            # IMDb/RT puanlarını hazırla (imdb alanı 'tt...' ise OMDb'dan çeker)
                imdb_d, rt_d, imdb_f, rt_i = resolve_ratings_for_item(item)
                media_key = "movie" if media_type == "Movie" else ("show" if media_type == "TV Show" else "movie")
                db.collection("favorites").document(item["id"]).set({
                    "id": item["id"],
                    "title": item["title"],
                    "year": item["year"],
                    "poster": item["poster"],
                    "type": media_key,
                    "cineselectRating": manual_val,
                    # --- puanlar ---
                    "imdb": float(imdb_f or 0),  # IMDb puanı (float)
                    "rt": int(rt_i or 0),        # RT yüzdesi (int, yoksa 0)
                    # IMDb ID'yi ayrıca sakla (sonradan güncelleme/backfill için)
                    "imdb_id": (
                        item["imdb"] if isinstance(item.get("imdb"), str) and item["imdb"].startswith("tt")
                        else item.get("imdb_id", "")
                    )
                }, merge=True)

st.divider()
st.subheader("❤️ Your Favorites")
sort_option = st.selectbox("Sort by:", ["IMDb", "RT", "CineSelect", "Year"], index=2)
# Yardımcı: string sayıları da çevir
def _as_float(x):
    try:
        if isinstance(x, str):
            x = x.replace(",", ".").strip()
        return float(x)
    except Exception:
        return 0.0

def get_sort_key(fav):
    try:
        if sort_option == "IMDb":
            v = fav.get("imdb")
            if isinstance(v, str) and v.startswith("tt"):
                return 0.0
            return _as_float(v)
        elif sort_option == "RT":
            return _as_float(fav.get("rt"))
        elif sort_option == "CineSelect":
            return _as_float(fav.get("cineselectRating"))
        elif sort_option == "Year":
            return int(fav.get("year", 0) or 0)
    except:
        return 0.0

def show_favorites(fav_type, label):
    global db

    # Backfill butonuresolve_ratings_for_item
    if st.button("🔄 Backfill IMDb/RT Ratings", key=f"backfill_{fav_type}"):
        # Ayarlar
        MAX_UPDATES = 60          # tek tıklamada en fazla kaç kayıt güncellensin
        BASE_DELAY  = 0.25        # her istek arası bekleme (sn)
        RETRIES     = 3           # hata/429 için tekrar sayısı
        BACKOFF_SEC = 5           # 429 gelince bekleme (sn)

        # Veri seti
        q = db.collection("favorites").where("type", "==", fav_type).stream()
        items = [d.to_dict() for d in q]

        # imdb_id bulma fonksiyonu
        def pick_imdb_id(f):
            if isinstance(f.get("imdb"), str) and f["imdb"].startswith("tt"):
                return f["imdb"]
            return f.get("imdb_id", "")

        # Güncellenecek adaylar
        candidates = []
        for f in items:
            imdb_id = pick_imdb_id(f)
            if imdb_id:
                if not isinstance(f.get("imdb"), (int, float)) or float(f.get("imdb") or 0) == 0 \
                   or int(f.get("rt") or 0) == 0:
                    candidates.append({"doc_id": f["id"], "imdb_id": imdb_id, "rt": f.get("rt", 0)})

        total = min(len(candidates), MAX_UPDATES)
        if total == 0:
            st.info("Güncellenecek uygun kayıt yok.")
        else:
            prog = st.progress(0.0, text="OMDb'den puanlar çekiliyor…")
            done = 0

            for c in candidates[:MAX_UPDATES]:
                # Retry/backoff döngüsü
                for attempt in range(1, RETRIES + 1):
                    try:
                        _, _, imdb_f, rt_i = resolve_ratings_for_item({"imdb": c["imdb_id"], "rt": c["rt"]})
                        db.collection("favorites").document(c["doc_id"]).update({
                            "imdb": float(imdb_f or 0),
                            "rt": int(rt_i or 0),
                            "imdb_id": c["imdb_id"]
                        })
                        break  # retry döngüsünden çık
                    except Exception as e:
                        msg = str(e)
                        time.sleep(BACKOFF_SEC if ("429" in msg or "Too Many" in msg) else 1.5)
                        if attempt == RETRIES:
                            st.write(f"⚠️ {c['doc_id']} güncellenemedi: {msg}")

                done += 1
                prog.progress(done / total)
                time.sleep(BASE_DELAY)  # istekler arası kısa bekleme

            prog.empty()
            st.success(f"Backfill tamamlandı. Güncellenen kayıt: {done}/{total}. Lütfen yenileyin.")
            st.rerun()
    docs = db.collection("favorites").where("type", "==", fav_type).stream()
    favorites = [doc.to_dict() for doc in docs]
    favorites_sorted = sorted(favorites, key=get_sort_key, reverse=True)

    st.markdown(f"### 📁 {label}")
    for idx, fav in enumerate(favorites_sorted):
        # Ağ çağrısı yok: önce DB’deki sayısal değerleri kullan
imdb_num = _as_float(fav.get("imdb", 0))
imdb_display = f"{imdb_num:.1f}" if imdb_num > 0 else "N/A"

# RT yüzdeyi int'e çevir (string gelse bile)
try:
    rt_num = int(float(fav.get("rt", 0) or 0))
except Exception:
    rt_num = 0
rt_display = f"{rt_num}%" if rt_num > 0 else "N/A"
        
        cols = st.columns([1, 5, 1, 1])
        with cols[0]:
            if show_posters and fav.get("poster"):
                st.image(fav["poster"], width=120)
        with cols[1]:
            st.markdown(f"**{idx+1}. {fav['title']} ({fav.get('year', 'N/A')})** | ⭐ IMDb: {imdb_display} | 🍅 RT: {rt_display} | 🎯 CS: {fav.get('cineselectRating', 'N/A')}")
        with cols[2]:
            if st.button("❌", key=f"remove_{fav['id']}"):
                db.collection("favorites").document(fav["id"]).delete()
                st.rerun()
        with cols[3]:
            if st.button("✏️", key=f"edit_{fav['id']}"):
                st.session_state[f"edit_mode_{fav['id']}"] = True

        if st.session_state.get(f"edit_mode_{fav['id']}", False):
            new_val = st.slider("🎯 CS:", 1, 10000, fav.get("cineselectRating", 5000), step=10, key=f"slider_{fav['id']}")
            if st.button("✅ Save", key=f"save_{fav['id']}"):
                db.collection("favorites").document(fav["id"]).update({"cineselectRating": new_val})
                st.success(f"✅ Updated {fav['title']}'s rating.")
                st.session_state[f"edit_mode_{fav['id']}"] = False
                st.rerun()

if media_type == "Movie":
    show_favorites("movie", "Favorite Movies")
elif media_type == "TV Show":
    show_favorites("show", "Favorite TV Shows")

st.markdown("---")
if st.button("🔝 Go to Top Again"):
    st.rerun()

st.markdown("<p style='text-align: center; color: gray;'>Created by <b>SS</b></p>", unsafe_allow_html=True)
