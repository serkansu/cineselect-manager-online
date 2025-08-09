import streamlit as st
import requests
import firebase_admin
from firebase_admin import credentials, firestore
import json
import base64
import os
import time

# Firebase yapılandırması
def get_firestore():
    if not firebase_admin._apps:
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = get_firestore()

# TMDB API Key
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "3028d7f0a392920b78e3549d4e6a66ec")
SEARCH_URL = "https://api.themoviedb.org/3/search/multi"
EXTERNAL_IDS_URL = "https://api.themoviedb.org/3/{media_type}/{tmdb_id}/external_ids"

def get_imdb_id(title, poster_url="", year=None, is_series=False):
    """Geliştirilmiş IMDb ID alma fonksiyonu"""
    params = {
        "api_key": TMDB_API_KEY,
        "query": title,
        "year": year if not is_series else None,
        "first_air_date_year": year if is_series else None,
    }
    
    try:
        res = requests.get(SEARCH_URL, params=params)
        res.raise_for_status()
        results = res.json().get("results", [])
        if not results:
            return "tt0000000"

        # Poster URL'si ile eşleşen sonucu bul
        match = next(
            (r for r in results if r.get("poster_path") and poster_url and r["poster_path"] in poster_url),
            results[0]
        )

        tmdb_id = match["id"]
        media_type = match.get("media_type", "tv" if is_series else "movie")

        external_url = EXTERNAL_IDS_URL.format(media_type=media_type, tmdb_id=tmdb_id)
        ext_res = requests.get(external_url, params={"api_key": TMDB_API_KEY})
        ext_res.raise_for_status()
        return ext_res.json().get("imdb_id", "tt0000000")
    except Exception as e:
        print(f"❌ IMDb ID alınırken hata ({title}): {str(e)}")
        return "tt0000000"

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
    try:
        favorites_data = {"movies": [], "shows": []}
        
        for doc in db.collection("favorites").stream():
            item = doc.to_dict()
            
            # Eksik/geçersiz IMDb ID varsa yeniden al
            if not item.get("imdb") or isinstance(item.get("imdb"), (int, float)) or item["imdb"] == "tt0000000":
                is_series = item.get("type", "").lower() in ["show", "series"]
                item["imdb"] = get_imdb_id(
                    title=item["title"],
                    poster_url=item.get("poster", ""),
                    year=item.get("year"),
                    is_series=is_series
                )
                time.sleep(0.1)  # API rate limit için
                db.collection("favorites").document(doc.id).update({"imdb": item["imdb"]})
            
            if item["type"] == "movie":
                favorites_data["movies"].append(item)
            else:
                favorites_data["shows"].append(item)

        with open("favorites.json", "w", encoding="utf-8") as f:
            json.dump(favorites_data, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        st.error(f"❌ favorites.json oluşturulamadı: {str(e)}")
        return False

def sync_with_firebase():
    db = get_firestore()
    movies = []
    series = []
    
    for doc in db.collection("favorites").stream():
        item = doc.to_dict()
            
        if not item.get("imdb") or isinstance(item.get("imdb"), (int, float)) or item["imdb"] == "tt0000000":
            is_series = item.get("type", "").lower() in ["show", "series"]
            imdb_id = get_imdb_id(
                item["title"],
                item.get("poster", ""),
                item.get("year"),
                is_series
            )
            item["imdb"] = imdb_id
            db.collection("favorites").document(doc.id).update({"imdb": imdb_id})
            time.sleep(0.1)

        if item["type"] == "movie":
            movies.append(item)
        else:
            series.append(item)

    with open("favorites.json", "w", encoding="utf-8") as f:
        json.dump({"movies": movies, "shows": series}, f, ensure_ascii=False, indent=4)
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

    if st.button("🔄 Senkronize Et (Firebase JSON)"):
        sync_with_firebase()
        push_favorites_to_github()
    st.success("✅ favorites.json senkronize edildi ve GitHub'a pushlandı!")

def show_favorites_count():
    global db
    movie_docs = db.collection("favorites").where("type", "==", "movie").stream()
    series_docs = db.collection("favorites").where("type", "==", "show").stream()

    movie_count = len(list(movie_docs))
    series_count = len(list(series_docs))

    st.info(f"🎬 Favorite Movies: {movie_count} | 📺 Favorite TV Shows: {series_count}")
    if st.button("📊 Favori Sayılarını Göster"):
        show_favorites_count()

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
            imdb_display = f"{item['imdb']:.1f}" if isinstance(item['imdb'], (int, float)) and item['imdb'] > 0 else "N/A"
            rt_display = f"{item['rt']}%" if isinstance(item['rt'], (int, float)) and item['rt'] > 0 else "N/A"
            st.markdown(f"⭐ IMDb: {imdb_display} &nbsp;&nbsp; 🍅 RT: {rt_display}", unsafe_allow_html=True)

            slider_key = f"stars_{item['id']}"
            manual_key = f"manual_{item['id']}"
            slider_val = st.slider("🎯 CineSelect Rating:", 1, 10000, st.session_state.get(slider_key, 5000), step=10, key=slider_key)
            manual_val = st.number_input("Manual value:", min_value=1, max_value=10000, value=slider_val, step=1, key=manual_key)

            if st.button("Add to Favorites", key=f"btn_{item['id']}"):
                media_key = "movie" if media_type == "Movie" else ("show" if media_type == "TV Show" else "movie")
                db.collection("favorites").document(item["id"]).set({
                    "id": item["id"],
                    "title": item["title"],
                    "year": item["year"],
                    "imdb": item["imdb"],
                    "poster": item["poster"],
                    "rt": item["rt"],
                    "cineselectRating": manual_val,
                    "type": media_key
                })
                st.success(f"✅ {item['title']} added to favorites!")
                st.session_state.query = ""
                st.rerun()

st.divider()
st.subheader("❤️ Your Favorites")
sort_option = st.selectbox("Sort by:", ["IMDb", "RT", "CineSelect", "Year"], index=2)
    
def get_sort_key(fav):
    try:
        if sort_option == "IMDb":
            return float(fav.get("imdb", 0))
        elif sort_option == "RT":
            return float(fav.get("rt", 0))
        elif sort_option == "CineSelect":
            return fav.get("cineselectRating", 0)
        elif sort_option == "Year":
            return int(fav.get("year", 0))
    except:
        return 0

def show_favorites(fav_type, label):
    global db
    docs = db.collection("favorites").where("type", "==", fav_type).stream()
    favorites = sorted([doc.to_dict() for doc in docs], key=get_sort_key, reverse=True)

    st.markdown(f"### 📁 {label}")
    for idx, fav in enumerate(favorites):
        imdb_display = f"{fav['imdb']:.1f}" if isinstance(fav["imdb"], (int, float)) else "N/A"
        rt_display = f"{fav['rt']}%" if isinstance(fav["rt"], (int, float)) else "N/A"
        cols = st.columns([1, 5, 1, 1])
        with cols[0]:
            if show_posters and fav.get("poster"):
                st.image(fav["poster"], width=120)
        with cols[1]:
            st.markdown(f"**{idx+1}. {fav['title']} ({fav['year']})** | ⭐ IMDb: {imdb_display} | 🍅 RT: {rt_display} | 🎯 CS: {fav.get('cineselectRating', 'N/A')}")
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

# Ana işlem akışı
if __name__ == "__main__":
    db = get_firestore()
    if create_favorites_json():
        print("✅ favorites.json başarıyla oluşturuldu!")
    else:
        print("❌ favorites.json oluşturulamadı!")
