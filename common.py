import os
import re
import time
import random
from curl_cffi import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

HEADERS = {
    "Accept-Language": "es-PY,es;q=0.9",
}


def fetch_html(url: str, timeout: int = 15) -> BeautifulSoup:
    resp = requests.get(url, headers=HEADERS, impersonate="chrome124", timeout=timeout)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "lxml")


def parse_price(text: str | None) -> float | None:
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    return float(digits) if digits else None


def polite_delay(min_s: float = 1.5, max_s: float = 4.0):
    time.sleep(random.uniform(min_s, max_s))
