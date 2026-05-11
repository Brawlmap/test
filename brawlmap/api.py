import os
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.brawlstars.com/v1"
API_KEY = os.getenv("BRAWL_STARS_API_KEY")


def _headers():
    if not API_KEY:
        raise ValueError("BRAWL_STARS_API_KEY not set in .env file")
    return {"Authorization": f"Bearer {API_KEY}"}


def get_player(tag: str) -> dict:
    """Fetch player profile by tag (e.g. '#ABC123')."""
    encoded_tag = tag.lstrip("#")
    url = f"{BASE_URL}/players/%23{encoded_tag}"
    response = requests.get(url, headers=_headers())
    response.raise_for_status()
    return response.json()


def get_battlelog(tag: str) -> dict:
    """Fetch player battlelog by tag."""
    encoded_tag = tag.lstrip("#")
    url = f"{BASE_URL}/players/%23{encoded_tag}/battlelog"
    response = requests.get(url, headers=_headers())
    response.raise_for_status()
    return response.json()
