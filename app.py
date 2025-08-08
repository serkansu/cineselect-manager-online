import streamlit as st
import requests
import os
import base64

def push_favorites_to_github():
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        st.warning("⚠️ GITHUB_TOKEN environment variable is missing!")
    if not github_token:
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

    # Dosya içeriğini oku ve base64 encode et
    with open("favorites.json", "rb") as f:
        content = f.read()
    encoded_content = base64.b64encode(content).decode("utf-8")

    # Mevcut dosya bilgisi (SHA) alınmalı
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
import streamlit as st
from firebase_setup import get_firestore
from tmdb import search_movie, search_tv, search_by_actor  # Actor arama fonksiyonu eklendi
import json


def sync_with_firebase():
    favorites_data = {
        "movies": st.session_state.get("favorite_movies", []),
        "shows": st.session_state.get("favorite_series", [])
    }
    with open("favorites.json", "w", encoding="utf-8") as f:
        json.dump(favorites_data, f, ensure_ascii=False, indent=4)
        st.write("🔍 FAVORITES DEBUG:", favorites_data)  # DEBUG SATIRI
    st.success("✅ favorites.json dosyası yerel olarak oluşturuldu.")

    # GitHub'a push et
    push_favorites_to_github()

db = get_firestore()

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
        st.success("✅ favorites.json dosyası senkronize edildi.")

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



import os
import base64
import requests

def push_favorites_to_github():
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
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

    # Dosya içeriğini oku ve base64 encode et
    with open("favorites.json", "rb") as f:
        content = f.read()
    encoded_content = base64.b64encode(content).decode("utf-8")

    # Mevcut dosya bilgisi (SHA) alınmalı
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
