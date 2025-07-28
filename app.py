import streamlit as st
import requests
import json
from firebase_setup import get_database

st.set_page_config(page_title="CineSelect Manager Online", layout="wide")

TMDB_API_KEY = "3028d7f0a392920b78e3549d4e6a66ec"
FIREBASE_DB = get_database()

st.title("🍿 CineSelect Manager Online")

query = st.text_input("Search Movie or Series on TMDB:")

def search_tmdb(query):
    url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={query}"
    res = requests.get(url)
    if res.status_code == 200:
        return res.json().get("results", [])
    return []

def send_to_firebase(entry, media_type):
    try:
        ref = FIREBASE_DB.child(media_type)
        ref.push(entry)
        st.success(f"{entry['title']} added to {media_type} successfully!")
    except Exception as e:
        st.error(f"Failed to add: {e}")

if query:
    results = search_tmdb(query)
    for item in results:
        title = item.get("title") or item.get("name")
        overview = item.get("overview", "")
        poster_path = item.get("poster_path", "")
        imdb_id = "tt0000000"
        year = (item.get("release_date") or item.get("first_air_date") or "")[:4]

        col1, col2 = st.columns([1, 4])
        with col1:
            if poster_path:
                st.image(f"https://image.tmdb.org/t/p/w500{poster_path}", width=120)
        with col2:
            st.subheader(title)
            st.write(overview)
            media_type = item.get("media_type", "movie")
            if st.button(f"✅ Add to {media_type}", key=f"{title}-{media_type}"):
                send_to_firebase({
                    "title": title,
                    "poster": f"https://image.tmdb.org/t/p/w500{poster_path}",
                    "description": overview,
                    "imdb": imdb_id,
                    "year": year
                }, media_type="movies" if media_type == "movie" else "series")