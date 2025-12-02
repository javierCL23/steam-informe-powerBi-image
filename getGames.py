
import requests
from bs4 import BeautifulSoup
import time
import pandas as pd
from typing import Optional

# --------------------------------------------
# CONFIGURACIÓN
# --------------------------------------------
API_KEY = "A16099EAFE55A83219DF77C4031228B9"
BASE_SEARCH_URL = "https://store.steampowered.com/search/"
FILTER = "topsellers"             # puedes cambiar a: "popularnew", "wishlist", "toprated", "specials"
PAGES = 25                        # 20 páginas ≈ 500 juegos
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://store.steampowered.com/",
}

# --------------------------------------------
# FUNCIONES AUXILIARES
# --------------------------------------------

def get_player_count(appid: int) -> Optional[int]:
    """Obtiene jugadores concurrentes desde Steam API."""
    if not API_KEY:
        return None
    url = "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"
    try:
        r = requests.get(url, params={"appid": appid, "key": API_KEY}, timeout=10)
        r.raise_for_status()
        return r.json().get("response", {}).get("player_count")
    except:
        return None
    
def get_required_age(details: dict) -> str:
    if "ratings" not in details:
        posibles = ["pegi","steam_germany","dejus","usk","agcom"]
        for i in posibles:
            for name in ["requider_age","rating"]:
                if i in details["ratings"]:
                    if name in details['ratings'][i]:
                        return details["ratings"][i][name]
    if "required_age" in details:
        return details["required_age"]
    else:
        return "0"

            


def get_appdetails(appid: int) -> dict:
    """Obtiene todos los detalles del juego desde la API de Steam."""
    url = "https://store.steampowered.com/api/appdetails"
    try:
        r = requests.get(url, params={"appids": appid, "cc": "us", "l": "en"}, headers=HEADERS, timeout=15)
        r.raise_for_status()
        j = r.json()
        if str(appid) in j and j[str(appid)].get("success"):
            return j[str(appid)]["data"]
    except:
        pass
    return {}

def get_reviews(appid: int):
    url = f"https://store.steampowered.com/appreviews/{appid}"
    params = {
        "json": 1,
        "filter": "all",
        "language": "all",
        "num_per_page": 0
    }
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=10)
        r.raise_for_status()
        j = r.json()
        summary = j.get("query_summary", {})
        return {
            "total_positive": summary.get("total_positive"),
            "total_negative": summary.get("total_negative"),
            "total_reviews": summary.get("total_reviews")
        }
    except:
        return {
            "total_positive": None,
            "total_negative": None,
            "total_reviews": None
        }


def parse_search_html(html: str):
    """Parses HTML de la página de búsqueda de Steam."""
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for a in soup.select("a.search_result_row"):
        appid = a.get("data-ds-appid") or a.get("data-ds-packageid")
        try:
            appid = int(appid) if appid else None
        except:
            appid = None

        name_el = a.select_one(".title")
        name = name_el.text.strip() if name_el else None

        items.append({"appid": appid, "name": name})
    return items

def fetch_search_page(page: int):
    params = {
        "filter": FILTER,
        "page": page,
        "cc": "us",
        "l": "english"
    }
    r = requests.get(BASE_SEARCH_URL, params=params, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.text

def extract_fields(appid: int, name: str, details: dict, players_now: Optional[int]):
    """Convierte el JSON de Steam API al formato exacto que pediste."""

    # comprobar que se juego
    if details.get("type") != "game":
        return None
    
    # release date
    release_date = details.get("release_date", {}).get("date")

    # achievements
    achievements = details.get("achievements", {}).get("total", 0)

    # categorías
    categories_raw = details.get("categories", [])
    categories = ";".join(
        [f"{c['id']}:{c['description']}" for c in categories_raw]
    ) if categories_raw else None

    # plataformas
    platforms = details.get("platforms", {})
    windows = platforms.get("windows", False)
    mac = platforms.get("mac", False)
    linux = platforms.get("linux", False)

    # developer
    developers = details.get("developers", [])
    developer = developers[0] if developers else None

    # dlcs
    dlc_list = details.get("dlc", [])
    dlc_count = len(dlc_list) if dlc_list else 0

    # idiomas (supported_languages viene en formato HTML)
    langs = details.get("supported_languages", "")
    if langs:
        # eliminar tags <...>
        langs_clean = (
            langs.replace("<strong>", "")
                 .replace("</strong>", "")
                 .replace("<br>", "")
        )
        # separar por coma
        lang_list = [l.strip() for l in langs_clean.split(",") if l.strip()]
        languages = ";".join(lang_list)
    else:
        languages = None

    # required_age
    required_age = get_required_age(details)

    # precio
    if details.get("is_free", False):
        price = 0.0
    else:
        pov = details.get("price_overview", {})
        price = (pov.get("initial", 0) / 100) if "initial" in pov else None

    # short description
    short_description = details.get("short_description")

    # reviews 
    reviews = get_reviews(appid)

    return {
        "appid": appid,
        "name": name,
        "release_date": release_date,
        "achievements": achievements,
        "categories": categories,
        "windows": windows,
        "mac": mac,
        "linux": linux,
        "developer": developer,
        "dlc_count": dlc_count,
        "languages": languages,
        "required_age": required_age,
        "price": price,
        "short_description": short_description,
        "players_now": players_now,
        "reviews_positive": reviews["total_positive"],
        "reviews_negative": reviews["total_negative"],
    }

def main():
    all_rows = []

    print("[INFO] Descargando lista TOP…")

    for page in range(1, PAGES + 1):
        print(f"  -> Página {page}/{PAGES}")
        html = fetch_search_page(page)
        items = parse_search_html(html)

        for it in items:
            appid = it["appid"]
            name = it["name"]

            if not appid:
                continue

            print(f"    · Procesando {appid} - {name}")

            details = get_appdetails(appid)
            players_now = get_player_count(appid)

            row = extract_fields(appid, name, details, players_now)
            if row is None:
                print(f"    · [WARNING] '{name}' no es un juego")
                continue

            all_rows.append(row)

            time.sleep(0.25)  # evitar rate-limit

        time.sleep(0.6)

    df = pd.DataFrame(all_rows)
    df.to_csv("F:\\steam_games_final.csv", index=False, encoding="utf-8")

    print("\n[OK] Dataset generado: steam_games_final.csv")
    print(f"[OK] Total juegos procesados: {len(df)}")

if __name__ == "__main__":
    main()
