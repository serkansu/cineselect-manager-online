
import requests
import json
from omdb import fetch_ratings  # Yeni eklendi

API_KEY = "3028d7f0a392920b78e3549d4e6a66ec"
BASE_URL = "https://api.themoviedb.org/3"
POSTER_BASE = "https://image.tmdb.org/t/p/w500"

def search_movie(query):
    url = f"{BASE_URL}/search/movie?api_key={API_KEY}&query={query}"
    res = requests.get(url).json()
    results = []
    for item in res.get("results", []):
        title = item["title"]
        year = item["release_date"][:4] if item.get("release_date") else "N/A"
        poster = f"{POSTER_BASE}{item['poster_path']}" if item.get("poster_path") else ""
        description = item.get("overview", "")

        imdb, rt = fetch_ratings(title, year)
        results.append({
            "id": f"tmdb{item['id']}",
            "title": title,
            "year": year,
            "poster": poster,
            "description": description,
            "imdb": imdb,
            "rt": rt
        })
    return results

def search_tv(query):
    url = f"{BASE_URL}/search/tv?api_key={API_KEY}&query={query}"
    res = requests.get(url).json()
    results = []
    for item in res.get("results", []):
        title = item["name"]
        year = item["first_air_date"][:4] if item.get("first_air_date") else "N/A"
        poster = f"{POSTER_BASE}{item['poster_path']}" if item.get("poster_path") else ""
        description = item.get("overview", "")

        imdb, rt = fetch_ratings(title, year)
        results.append({
            "id": f"tmdb{item['id']}",
            "title": title,
            "year": year,
            "poster": poster,
            "description": description,
            "imdb": imdb,
            "rt": rt
        })
    return results

def search_by_actor(actor_name):
    url = f"{BASE_URL}/search/person?api_key={API_KEY}&query={actor_name}"
    res = requests.get(url).json()
    actor_results = []
    for actor in res.get("results", []):
        actor_id = actor.get("id")
        if not actor_id:
            continue
        credits_url = f"{BASE_URL}/person/{actor_id}/combined_credits?api_key={API_KEY}"
        credits_res = requests.get(credits_url).json()
        for item in credits_res.get("cast", []):
            title = item.get("title") or item.get("name")
            year = (item.get("release_date") or item.get("first_air_date") or "")[:4]
            poster = f"{POSTER_BASE}{item['poster_path']}" if item.get("poster_path") else ""
            imdb, rt = fetch_ratings(title, year)
            actor_results.append({
                "id": f"tmdb{item['id']}",
                "title": title,
                "year": year,
                "poster": poster,
                "description": "",
                "imdb": imdb,
                "rt": rt
            })
    return actor_results
