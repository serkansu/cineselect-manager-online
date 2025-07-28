import requests

OMDB_API_KEY = "295944aa"

def fetch_ratings(title, year):
    """
    OMDb API üzerinden verilen başlık ve yıl bilgisiyle
    IMDb ve Rotten Tomatoes puanlarını çeker.

    Args:
        title (str): Film veya dizi adı
        year (str or int): Yıl bilgisi ("2010" gibi)

    Returns:
        tuple: (imdb_rating: float, rt_score: int)
    """
    url = f"http://www.omdbapi.com/?apikey={OMDB_API_KEY}&t={title}&y={year}"
    try:
        res = requests.get(url)
        data = res.json()

        imdb = float(data.get("imdbRating", 0))
        rt = 0
        for rating in data.get("Ratings", []):
            if rating["Source"] == "Rotten Tomatoes":
                rt = int(rating["Value"].replace("%", ""))
                break

        return imdb, rt
    except Exception as e:
        print(f"Hata oluştu: {e}")
        return 0.0, 0
