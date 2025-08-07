import streamlit as st
import json
import requests
import os
from firebase_admin import credentials, firestore, initialize_app
import subprocess

# Firebase bağlantısı
@st.cache_resource
def get_firestore():
    if not firestore._apps:
        cred = credentials.Certificate({
            "type": "service_account",
            "project_id": "cineselect",
            "private_key_id": os.getenv("PRIVATE_KEY_ID"),
            "private_key": os.getenv("PRIVATE_KEY").replace("\\n", "\n"),
            "client_email": os.getenv("CLIENT_EMAIL"),
            "client_id": os.getenv("CLIENT_ID"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": os.getenv("CLIENT_CERT_URL")
        })
        initialize_app(cred)
    return firestore.client()

db = get_firestore()

# TMDB API
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_SEARCH_MOVIE = "https://api.themoviedb.org/3/search/movie"
TMDB_SEARCH_TV = "https://api.themoviedb.org/3/search/tv"
TMDB_EXTERNAL_IDS = "https://api.themoviedb.org/3/{type}/{id}/external_ids"

def search_tmdb(title, content_type):
    params = {
        "api_key": TMDB_API_KEY,
        "query": title,
        "include_adult": False
    }
    url = TMDB_SEARCH_MOVIE if content_type == "movie" else TMDB_SEARCH_TV
    response = requests.get(url, params=params)
    if response.status_code == 200 and response.json()["results"]:
        return response.json()["results"][0]
    return None

def get_imdb_id(type_, tmdb_id):
    url = TMDB_EXTERNAL_IDS.format(type=type_, id=tmdb_id)
    response = requests.get(url, params={"api_key": TMDB_API_KEY})
    if response.status_code == 200:
        return response.json().get("imdb_id", "")
    return ""

# Streamlit UI
st.set_page_config(layout="wide")
st.title("🎬 CineSelect Manager")

selection = st.radio("Seçim", ["Favoriler", "İstek Listesi"])
col1, col2 = st.columns([3, 1])

with col1:
    title = st.text_input("Film/Dizi Adı")
    content_type = st.selectbox("Tür", ["movie", "series"])

with col2:
    if st.button("🎯 Ekle ve Güncelle"):
        collection = "favorites" if selection == "Favoriler" else "watchlist"
        ref = db.collection(collection)
        docs = ref.stream()
        existing_titles = [doc.to_dict().get("title", "").lower() for doc in docs]

        if title.lower() not in existing_titles:
            result = search_tmdb(title, "movie" if content_type == "movie" else "tv")
            if result:
                imdb = get_imdb_id("movie" if content_type == "movie" else "tv", result["id"])
                ref.add({
                    "title": result["title"] if content_type == "movie" else result["name"],
                    "poster": f"https://image.tmdb.org/t/p/w500{result['poster_path']}" if result.get("poster_path") else "",
                    "imdb": imdb,
                    "type": content_type
                })
                st.success(f"✅ {title} başarıyla eklendi.")
            else:
                st.error("❌ TMDB'de sonuç bulunamadı.")
        else:
            st.info("ℹ️ Bu içerik zaten eklenmişti.")

        # Güncelleme betiğini çalıştır
        try:
            result = subprocess.run(["python3", "fetch_and_push_auto.py"], capture_output=True, text=True)
            output_lines = result.stdout.splitlines()
            for line in output_lines:
                st.info(line)
        except Exception as e:
            st.error(f"fetch_and_push_auto.py çalıştırılamadı: {e}")

# Favori ve istek listesi görüntüleme
def load_list(name):
    try:
        with open("favorites_updated.json") as f:
            return json.load(f).get(name, [])
    except:
        return []

with st.expander("🎬 Favori Filmler"):
    for item in load_list("movies"):
        st.markdown(f"**{item['title']}** — {item.get('imdb', '')}")

with st.expander("📺 Favori Diziler"):
    for item in load_list("series"):
        st.markdown(f"**{item['title']}** — {item.get('imdb', '')}")

with st.expander("📌 Watch List"):
    watchlist = db.collection("watchlist").stream()
    for doc in watchlist:
        item = doc.to_dict()
        st.markdown(f"**{item['title']}** — {item.get('imdb', '')}")
