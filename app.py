# Kusursuz app.py + fetch_and_push_auto.py entegrasyonu
import os
import json
import streamlit as st
from tmdb import search_movie, search_tv, add_to_favorites
from github import Github
from dotenv import load_dotenv

# GitHub ayarları
load_dotenv()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") or st.secrets.get("GITHUB_TOKEN", None)
REPO_NAME = "serkansu/cineselect-addon"
TARGET_FILE = "favorites.json"

# Sayfa yapılandırması
st.set_page_config(page_title="CineSelect Manager", layout="centered")
st.title("🎬 CineSelect Manager")

# --- favorites.json eski format ise dönüştür ---
def ensure_favorites_structure():
    if os.path.exists("favorites.json"):
        with open("favorites.json", "r") as f:
            try:
                data = json.load(f)
                if isinstance(data, list):  # eski format
                    new_data = {"movies": data, "shows": []}
                    with open("favorites.json", "w") as fw:
                        json.dump(new_data, fw, indent=2)
            except:
                pass

ensure_favorites_structure()

# Firebase'den çek + favorites_updated.json oluştur + GitHub'a push et
def sync_favorites_to_github():
    try:
        with open("favorites.json", "r") as f:
            favorites = json.load(f)

        with open("favorites_updated.json", "w") as fw:
            json.dump(favorites, fw, indent=2)

        num_movies = len(favorites.get("movies", []))
        num_series = len(favorites.get("shows", []))

        if not GITHUB_TOKEN:
            st.warning("⚠️ GitHub token bulunamadı.")
            return

        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        contents = repo.get_contents(TARGET_FILE)

        with open("favorites_updated.json", "r") as fup:
            updated_content = fup.read()

        repo.update_file(contents.path, "Update favorites.json from app.py", updated_content, contents.sha)
        st.success(f"✅ GitHub güncellendi — 🎬 {num_movies} movie, 📺 {num_series} series")
    except Exception as e:
        st.error(f"🚨 Hata oluştu: {e}")

# Arama bölümü
media_type = st.radio("What would you like to search for?", ["Movie", "TV Show"], horizontal=True)
query = st.text_input(f"🔍 Search for a {media_type.lower()}")
if query:
    results = search_movie(query) if media_type == "Movie" else search_tv(query)
    for idx, item in enumerate(results):
        if item["poster"]:
            st.image(item["poster"])
        else:
            st.warning("No poster available.")
        st.markdown(f"**{item['title']} ({item['year']})**")
        st.markdown(f"⭐ IMDb: {item['imdb']} &nbsp;&nbsp; 🍅 RT: {item['rt']}%")

        stars = st.slider("🎯 CineSelect Rating", 1, 5, 3, key=f"stars_{idx}")
        if st.button("Add to Favorites", key=f"btn_{idx}"):
            key = "movie" if media_type == "Movie" else "show"
            add_to_favorites(item, stars, key)
            st.success(f"✅ {item['title']} added to your favorites!")
            sync_favorites_to_github()  # 🎯 Otomatik güncelleme burada

# Favori gösterimi
st.markdown("---")
st.subheader("❤️ Your Favorites")

def show_favorites(fav_type, label):
    if os.path.exists("favorites.json"):
        with open("favorites.json", "r") as f:
            data = json.load(f)
        favs = data.get(fav_type, [])
        if favs:
            st.markdown(f"### 📁 {label}")
            for fav in favs:
                if fav.get("poster"):
                    st.image(fav["poster"], width=150)
                else:
                    st.warning("No poster available.")
                st.markdown(f"**{fav['title']} ({fav['year']})**")
                st.markdown(f"⭐ IMDb: {fav['imdb']} &nbsp;&nbsp; 🍅 RT: {fav['rt']}%")
                st.markdown(f"🎯 CineSelect Rating: {fav.get('cineselectRating', 'N/A')}")
                st.markdown("---")
        else:
            st.info(f"No {label.lower()} favorites yet.")
    else:
        st.info("No favorites file found.")

show_favorites("movies", "Favorite Movies")
show_favorites("shows", "Favorite TV Shows")

# Footer
st.markdown("---")
st.markdown("<p style='text-align: center; color: gray;'>Created by <b>SS</b></p>", unsafe_allow_html=True)
