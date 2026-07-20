from common import fetch_html, parse_price, polite_delay

STORE_ID = "nissei"
BASE_URL = "https://www.nissei.com"

def scrape(query: str) -> list[dict]:
    url = f"{BASE_URL}/py/catalogsearch/result/?q={query}"
    soup = fetch_html(url)

    products = []
    for card in soup.select(".product-item"):
        name_el = card.select_one(".product-item-link")
        price_el = card.select_one(".price")
        img_el = card.select_one("img")
        link_el = card.select_one("a.product-item-link")

        if not name_el or not link_el:
            continue

        href = link_el["href"]
        products.append({
            "name": name_el.get_text(strip=True),
            "price": parse_price(price_el.get_text(strip=True) if price_el else None),
            "image_url": img_el["src"] if img_el and img_el.has_attr("src") else None,
            "source_url": href if href.startswith("http") else BASE_URL + href,
            "external_id": href.split("/")[-1],
            "store_origin": STORE_ID,
        })

    polite_delay()
    return products
