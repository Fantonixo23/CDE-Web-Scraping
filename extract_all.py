import sys
import os
import time
import random
import json
import re
from urllib.parse import quote_plus, urlparse
from dotenv import load_dotenv
from curl_cffi import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "es-PY,es;q=0.9",
}
TIMEOUT = 20
MAX_RETRIES = 3
QUERY = "notebook"

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

OUT_DIR = os.path.join(os.path.dirname(__file__), "json_extracted")
os.makedirs(OUT_DIR, exist_ok=True)


def fetch_html(url: str) -> str | None:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=HEADERS, impersonate="chrome124", timeout=TIMEOUT)
            if resp.status_code == 200:
                return resp.text
        except:
            pass
        if attempt < MAX_RETRIES:
            time.sleep(random.uniform(1, 2))
    return None


def parse_gs_price(text: str | None) -> float | None:
    if not text:
        return None
    gs_match = re.search(r"Gs\.?\s*([\d.]+)", text)
    if gs_match:
        num = gs_match.group(1)
        if len(num) > 2 and re.search(r"\d", num):
            digits = re.sub(r"[^\d]", "", num)
            return float(digits) if digits else None
    pre_gs = re.search(r"([\d.]+)\s*Gs\.?", text)
    if pre_gs:
        num = pre_gs.group(1)
        if len(num) > 2 and re.search(r"\d", num):
            digits = re.sub(r"[^\d]", "", num)
            return float(digits) if digits else None
    dollar_match = re.search(r"\$\s*([\d.,]+)", text)
    if dollar_match:
        return float(dollar_match.group(1).replace(",", ""))
    digits = re.sub(r"[^\d]", "", text)
    return float(digits) if digits else None


def extract_sku(url: str, store: str) -> str | None:
    path = urlparse(url).path
    if store == "cellshop":
        m = re.match(r"/(\d+)", path)
        if m:
            return m.group(1)
        m = re.search(r"/id/(\d+)", path)
        return m.group(1) if m else None
    elif store == "shopping_china":
        m = re.search(r"(\d+)$", path.rstrip("/"))
        return m.group(1) if m else None
    elif store == "topdek":
        m = re.search(r"/(\d+)\.html", path)
        return m.group(1) if m else None
    elif store == "new_zone":
        m = re.search(r"/producto/(\d+)", path)
        return m.group(1) if m else None
    elif store == "nissei":
        m = re.search(r"/product/(\d+)", path)
        return m.group(1) if m else None
    elif store == "visaovip":
        m = re.search(r"/(\d+)/?$", path.rstrip("/"))
        return m.group(1) if m else None
    elif store == "atacado_connect":
        m = re.search(r"/(\d+)$", path.rstrip("/"))
        return m.group(1) if m else None
    return None


def parse_usd_price(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r"U?\$\s*([\d.]+),(\d{2})", text)
    if m:
        num = m.group(1).replace(".", "") + "." + m.group(2)
        return float(num)
    m2 = re.search(r"U?\$\s*([\d.,]+)", text)
    if m2:
        cleaned = m2.group(1).replace(".", "").replace(",", ".")
        return float(cleaned)
    return None


# ─── SUPABASE IMAGE UPLOAD ──────────────────────────────────────────────────

def _get_supabase():
    try:
        from supabase import create_client
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if url and key:
            return create_client(url, key)
    except ImportError:
        pass
    return None


def _upload_to_supabase(supabase, product: dict, image_data: bytes) -> str | None:
    from storage3.types import FileOptions

    store = product["store"]
    sku = product["sku"]
    ext = "jpg"
    path = f"{store}/{sku}.{ext}"

    try:
        opts = FileOptions({"content-type": "image/jpeg", "upsert": "true"})
        supabase.storage.from_("product-images").upload(path, image_data, opts)
        public_url = supabase.storage.from_("product-images").get_public_url(path)
        return public_url
    except Exception as e:
        print(f"      Supabase upload error: {e}")
        return None


def download_nissei_images(products: list[dict]) -> list[dict]:
    """Download Nissei product images via UC (Cloudflare bypass) and upload to Supabase Storage."""
    import base64

    supabase = _get_supabase()
    if not supabase:
        print("    Supabase no configurado, saltando descarga de imagenes")
        return products

    try:
        import undetected_chromedriver as uc
    except ImportError:
        return products

    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    options.binary_location = r"C:\Users\juamp\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe"

    driver = None
    try:
        driver = uc.Chrome(options=options, version_main=149)
        driver.set_page_load_timeout(30)

        # Bypass Cloudflare by visiting a known-working search page
        driver.get("https://www.nissei.com/py/catalogsearch/result/?q=notebook")
        time.sleep(5)
        for _ in range(6):
            title = driver.title.lower()
            if "momento" in title or "just a moment" in title:
                print("    Cloudflare...", end="", flush=True)
                time.sleep(5)
            else:
                break
        print()

        for i, p in enumerate(products):
            img_url = p.get("image_url")
            if not img_url:
                continue
            print(f"    Imagen {i+1}/{len(products)}...", end=" ", flush=True)

            try:
                b64data = driver.execute_async_script("""
                    const url = arguments[0];
                    const cb = arguments[arguments.length - 1];
                    fetch(url, {credentials: 'include'})
                        .then(r => {
                            if (!r.ok) return null;
                            return r.blob().then(b => new Promise(res => {
                                const reader = new FileReader();
                                reader.onload = () => res(reader.result);
                                reader.readAsDataURL(b);
                            }));
                        })
                        .catch(() => null)
                        .then(cb);
                """, img_url)

                if b64data and "," in b64data:
                    raw = base64.b64decode(b64data.split(",", 1)[1])
                    new_url = _upload_to_supabase(supabase, p, raw)
                    if new_url:
                        p["image_url"] = new_url
                        print("OK")
                    else:
                        print("upload fail")
                else:
                    print("no data")
            except Exception as e:
                print(f"err: {e}")

    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
    return products


def fetch_description(source_url: str, store: str) -> str | None:
    html = fetch_html(source_url)
    if not html:
        return None
    soup = BeautifulSoup(html, "lxml")

    if store == "cellshop":
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.get_text(strip=True))
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if isinstance(item, dict) and item.get("description"):
                        return item["description"]
            except:
                pass
        desc_el = soup.select_one(".description")
        if desc_el:
            return desc_el.get_text(strip=True)

    elif store == "shopping_china":
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            return meta["content"]
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.get_text(strip=True))
                if isinstance(data, dict) and data.get("description"):
                    return data["description"]
            except:
                pass

    elif store == "atacado_connect":
        for prop in ["og:description", "twitter:description"]:
            meta = soup.find("meta", property=prop)
            if meta and meta.get("content"):
                return meta["content"]
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            return meta["content"]

    return None


def enrich_descriptions(products: list[dict], store: str) -> list[dict]:
    enriched = []
    for i, p in enumerate(products):
        desc = p.get("description")
        if not desc and p.get("source_url"):
            print(f"    Desc {i+1}/{len(products)}...", end=" ")
            desc = fetch_description(p["source_url"], store)
            print("OK" if desc else "-")
        p["description"] = desc
        enriched.append(p)
        if i > 0 and i % 5 == 0:
            time.sleep(0.5)
    return enriched


def enrich_with_uc(products: list[dict], store_key: str) -> list[dict]:
    try:
        import undetected_chromedriver as uc
    except ImportError:
        return products

    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    options.binary_location = r"C:\Users\juamp\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe"

    driver = None
    try:
        driver = uc.Chrome(options=options, version_main=149)
        driver.set_page_load_timeout(30)
        for i, p in enumerate(products):
            if p.get("description"):
                continue
            url = p.get("source_url", "")
            if not url:
                continue
            print(f"    UC desc {i+1}/{len(products)}...", end=" ")
            try:
                driver.get(url)
                time.sleep(5)

                if store_key == "nissei":
                    if "momento" in driver.title.lower() or "just a moment" in driver.title.lower():
                        time.sleep(10)
                    desc = driver.execute_script("""
                        const el = document.querySelector('[class*="description"], [class*="descricao"], #description, .product-description, .value');
                        return el ? el.textContent.trim().substring(0, 1000) : null;
                    """)
                elif store_key == "visaovip":
                    desc = driver.execute_script("""
                        const el = document.querySelector('[class*="description"], [class*="descricao"], [itemprop="description"], .product-description');
                        return el ? el.textContent.trim().substring(0, 1000) : null;
                    """)
                    if not desc:
                        desc = driver.execute_script("""
                            const nd = document.getElementById('__NEXT_DATA__');
                            if (!nd) return null;
                            try {
                                const data = JSON.parse(nd.textContent);
                                const p = data.props.pageProps.product || data.props.pageProps.data || {};
                                return p.description || p.desc || null;
                            } catch(e) { return null; }
                        """)
                else:
                    desc = None

                if desc:
                    p["description"] = desc
                    print("OK")
                else:
                    print("-")
            except Exception as e:
                print(f"ERR: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
    return products


def save_results(store_name: str, products: list[dict]):
    filename = f"{store_name.lower().replace(' ', '_')}.json"
    filepath = os.path.join(OUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    print(f"  -> {len(products)} productos guardados en {filepath}")


# ─── SCRAPERS SIN CLOUDFLARE (requests + BeautifulSoup) ─────────────────

def scrape_cellshop(query: str) -> list[dict]:
    url = f"https://www.cellshop.com.py/busca?q={quote_plus(query)}"
    html = fetch_html(url)
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    products = []
    for card in soup.select(".product-item-info"):
        name_el = card.select_one(".product-item-link")
        price_el = card.select_one(".price-wrapper .price, .normal-price .price, .price")
        img_el = card.select_one("img")
        link_el = card.select_one("a[href]")
        if not name_el or not link_el:
            continue
        href = link_el.get("href", "")
        full_url = href if href.startswith("http") else f"https://www.cellshop.com.py{href}"
        products.append({
            "store": "cellshop",
            "sku": extract_sku(full_url, "cellshop"),
            "name": name_el.get_text(strip=True),
            "price": parse_gs_price(price_el.get_text(strip=True) if price_el else None),
            "description": None,
            "image_url": img_el.get("src") if img_el and img_el.has_attr("src") else None,
            "source_url": full_url,
        })
    return products


def scrape_shopping_china(query: str) -> list[dict]:
    url = f"https://www.shoppingchina.com.py/site/search?query={quote_plus(query)}"
    html = fetch_html(url)
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    products = []
    for card in soup.select(".product-item"):
        name_el = card.select_one(".lightning-prod-desc")
        price_el = card.select_one(".lightning-prod-sale")
        img_el = card.select_one("img.card-img-top")
        link_el = card.select_one("a[href]")
        if not name_el or not link_el:
            continue
        href = link_el.get("href", "")
        full_url = href if href.startswith("http") else f"https://www.shoppingchina.com.py{href}"
        products.append({
            "store": "shopping_china",
            "sku": extract_sku(full_url, "shopping_china"),
            "name": name_el.get_text(strip=True),
            "price": parse_gs_price(price_el.get_text(strip=True) if price_el else None),
            "description": None,
            "image_url": img_el.get("src") if img_el and img_el.has_attr("src") else None,
            "source_url": full_url,
        })
    return products


def scrape_topdek(query: str) -> list[dict]:
    url = f"https://www.topdekinformatica.com.br/busca/{quote_plus(query)}"
    html = fetch_html(url)
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    products = []
    BASE = "https://www.topdekinformatica.com.br"
    for card in soup.select(".product"):
        name_el = card.select_one(".name, .product-name, .nome, .title, .prod-title, h2, h3")
        price_el = card.select_one(".price, .preco, .product-price, .precio, .prod-price")
        img_el = card.select_one("img")
        link_el = card.select_one("a[href]")
        if not name_el or not link_el:
            continue
        href = link_el.get("href", "")
        if href.startswith("/"):
            href = BASE + href
        elif not href.startswith("http"):
            href = BASE + "/" + href
        img_src = img_el.get("src") if img_el and img_el.has_attr("src") else None
        if img_src and not img_src.startswith("http"):
            img_src = BASE + ("/" if not img_src.startswith("/") else "") + img_src
        products.append({
            "store": "topdek",
            "sku": extract_sku(href, "topdek"),
            "name": name_el.get_text(strip=True),
            "price": parse_gs_price(price_el.get_text(strip=True) if price_el else None),
            "description": None,
            "image_url": img_src,
            "source_url": href,
        })
    return products


def scrape_visaovip(query: str) -> list[dict]:
    url = f"https://www.visaovip.com/busca/{quote_plus(query)}"
    html = fetch_html(url)
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    next_data = soup.find("script", id="__NEXT_DATA__")
    if next_data:
        try:
            data = json.loads(next_data.get_text(strip=True))
            props = data.get("props", {}).get("pageProps", {})
            results = props.get("searchResults", props.get("products", props.get("results", [])))
            if results:
                products = []
                for item in results[:20]:
                    products.append({
                        "store": "visaovip",
                        "sku": item.get("sku") or item.get("id"),
                        "name": item.get("name", ""),
                        "price": item.get("price", {}).get("amount", item.get("price")),
                        "description": item.get("description"),
                        "image_url": item.get("image", ""),
                        "source_url": f"https://www.visaovip.com/produto/{item.get('slug', item.get('id', ''))}",
                    })
                return products
        except:
            pass
    return []


def scrape_atacado_connect(query: str) -> list[dict]:
    url = f"https://atacadoconnect.com/busca?q={quote_plus(query)}"
    html = fetch_html(url)
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    for script in soup.find_all("script"):
        text = script.get_text(strip=True)
        if "self.__next_f" in text or "__NEXT_DATA__" in text:
            try:
                matches = re.findall(r'\{"name":\s*"[^"]+",\s*"price":\s*[\d.]+[^}]+}', text)
                if matches:
                    products = []
                    for m in matches[:20]:
                        try:
                            item = json.loads(m)
                            products.append({
                                "store": "atacado_connect",
                                "sku": item.get("sku") or item.get("id"),
                                "name": item.get("name", ""),
                                "price": item.get("price"),
                                "description": item.get("description"),
                                "image_url": item.get("image", item.get("imageUrl", "")),
                                "source_url": item.get("url", item.get("slug", "")),
                            })
                        except:
                            pass
                    return products
            except:
                pass
    return []


def scrape_new_zone(query: str) -> list[dict]:
    url = "https://www.newzone.com.py/"
    html = fetch_html(url)
    if not html:
        url2 = f"https://www.newzone.com.py/buscar?q={quote_plus(query)}"
        html2 = fetch_html(url2)
        if not html2:
            return []
        html = html2
    soup = BeautifulSoup(html, "lxml")
    products = []
    for card in soup.select(".product-card-modern, .SlideProductView2"):
        body = card.select_one(".card-body")
        link_el = card.select_one("a[href]")
        img_el = card.select_one("img")
        if not body or not link_el:
            continue
        text = body.get_text(strip=True)
        href = link_el.get("href", "")
        price = None
        price_match = re.search(r"\$([\d.,]+)", text)
        if price_match:
            price = float(price_match.group(1).replace(",", ""))
        full_url = href if href.startswith("http") else f"https://www.newzone.com.py{href}"
        products.append({
            "store": "new_zone",
            "sku": extract_sku(full_url, "new_zone"),
            "name": text,
            "price": price,
            "description": None,
            "image_url": img_el.get("src") if img_el and img_el.has_attr("src") else None,
            "source_url": full_url,
        })
    return products


# ─── NISSEI (Cloudflare -> undetected-chromedriver) ────────────────────────

def scrape_nissei_uc(query: str) -> list[dict]:
    try:
        import undetected_chromedriver as uc
        from selenium.webdriver.common.by import By
    except ImportError:
        return []

    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")
    options.binary_location = r"C:\Users\juamp\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe"

    url = f"https://www.nissei.com/py/catalogsearch/result/?q={quote_plus(query)}"

    for attempt in range(3):
        driver = None
        try:
            driver = uc.Chrome(options=options, version_main=149)
            driver.set_page_load_timeout(30)
            driver.get(url)
            time.sleep(5)

            if "momento" in driver.title.lower() or "just a moment" in driver.title.lower():
                print("  Cloudflare, esperando...", end="")
                time.sleep(12)
                print(" recheck")

            if "momento" in driver.title.lower() or "just a moment" in driver.title.lower():
                print("  -> Cloudflare no resuelto, reintentando...")
                driver.quit()
                continue

            # Try extracting from the search or redirected category page
            products = driver.execute_script("""
                const items = document.querySelectorAll('.product-item');
                if (items.length === 0) return [];
                return Array.from(items).map(card => {
                    const nameEl = card.querySelector('.product-item-link');
                    const priceEl = card.querySelector('.price');
                    const imgEl = card.querySelector('.product-image-photo, img');
                    const linkEl = card.querySelector('.product-item-link');
                    // Try to extract product ID from data-mfp-src or data-post
                    const mfpEl = card.querySelector('[data-mfp-src]');
                    const postEl = card.querySelector('[data-post]');
                    let productId = null;
                    if (postEl) {
                        try {
                            const post = JSON.parse(postEl.getAttribute('data-post'));
                            productId = post.data ? post.data.product : null;
                        } catch(e) {}
                    }
                    if (!productId && mfpEl) {
                        const m = mfpEl.getAttribute('data-mfp-src').match(/\\/id\\/(\\d+)/);
                        if (m) productId = m[1];
                    }
                    return {
                        name: nameEl ? nameEl.textContent.replace(/\\s+/g, ' ').trim() : null,
                        price: priceEl ? priceEl.textContent.replace(/\\s+/g, ' ').trim() : null,
                        image: imgEl ? imgEl.getAttribute('src') : null,
                        url: linkEl ? linkEl.getAttribute('href') : null,
                        productId: productId,
                    };
                }).filter(p => p.name || p.price);
            """)

            if not products:
                print("  -> 0 productos con selectores actuales, debugueando...")
                html_preview = driver.execute_script("return document.body.innerHTML.substring(0, 2000)")
                print(f"  HTML: {html_preview[:300]}")
                continue

            parsed = []
            for p in products:
                href = p.get("url", "") or ""
                name = (p.get("name") or "").strip()
                if not name:
                    continue
                full_url = href if href.startswith("http") else f"https://www.nissei.com{href}"
                sku = p.get("productId") or extract_sku(full_url, "nissei")
                parsed.append({
                    "store": "nissei",
                    "sku": sku,
                    "name": name,
                    "price": parse_gs_price(p.get("price")),
                    "description": None,
                    "image_url": p.get("image"),
                    "source_url": full_url,
                })
            return parsed

        except Exception as e:
            print(f"  Error: {e}")
            if attempt < 2:
                print("  Reintentando...")
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass

    return []


# ─── VISAOVIP (Next.js SPA -> undetected-chromedriver) ───────────────────

def scrape_visaovip_uc(query: str) -> list[dict]:
    try:
        import undetected_chromedriver as uc
    except ImportError:
        return []

    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    options.binary_location = r"C:\Users\juamp\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe"

    # Map query to category
    cat_map = {"notebook": "20-03"}
    cat = cat_map.get(query.lower(), "")

    url = f"https://www.visaovip.com/busca/categoria/{quote_plus(query)}/{cat}/" if cat else f"https://www.visaovip.com/busca/{quote_plus(query)}"

    for attempt in range(2):
        driver = None
        try:
            driver = uc.Chrome(options=options, version_main=149)
            driver.set_page_load_timeout(30)
            driver.get(url)
            time.sleep(8)

            if "momento" in driver.title.lower():
                time.sleep(12)

            products = driver.execute_script("""
                const cards = document.querySelectorAll('[class*="col-6"][class*="md:col-4"]');
                const results = [];
                cards.forEach(card => {
                    const link = card.querySelector('a[href*="/es/prod/"], a[href*="/prod/"]');
                    const nameEl = card.querySelector('[class*="productCards"]');
                    const priceEl = card.querySelector('.PrecoDestacado');
                    const imgEl = card.querySelector('img');
                    const codeEl = card.querySelector('span[class*="texto-cinza-200"]');
                    if (!link || !nameEl) return;
                    const name = nameEl.textContent.trim();
                    const price = priceEl ? priceEl.textContent.trim() : '';
                    const img = imgEl ? imgEl.getAttribute('src') : '';
                    const url = link.getAttribute('href');
                    const sku = codeEl ? codeEl.textContent.trim() : '';
                    if (name) results.push({ name, price, img, url, sku });
                });
                return results;
            """)

            if not products:
                continue

            parsed = []
            for p in products:
                href = p.get("url", "") or ""
                full_url = href if href.startswith("http") else f"https://www.visaovip.com{href}"
                price = parse_usd_price(p.get("price"))
                if not price:
                    price = parse_gs_price(p.get("price"))
                sku = p.get("sku") or extract_sku(full_url, "visaovip")
                parsed.append({
                    "store": "visaovip",
                    "sku": sku,
                    "name": p.get("name", ""),
                    "price": price,
                    "description": None,
                    "image_url": p.get("img"),
                    "source_url": full_url,
                })
            return parsed

        except Exception as e:
            if attempt < 1:
                pass
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
    return []


# ─── ATACADO CONNECT (Next.js SPA -> undetected-chromedriver) ────────────

def scrape_atacado_connect_uc(query: str) -> list[dict]:
    try:
        import undetected_chromedriver as uc
    except ImportError:
        return []

    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    options.binary_location = r"C:\Users\juamp\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe"

    url = f"https://atacadoconnect.com/busca?q={quote_plus(query)}"

    for attempt in range(2):
        driver = None
        try:
            driver = uc.Chrome(options=options, version_main=149)
            driver.set_page_load_timeout(30)
            driver.get(url)
            time.sleep(8)

            products = driver.execute_script("""
                const grid = document.querySelector('.grid.grid-cols-2');
                if (!grid) return [];
                const cards = grid.querySelectorAll('a');
                const results = [];
                cards.forEach(a => {
                    const nameEl = a.querySelector('h3');
                    const imgEl = a.querySelector('img');
                    if (!nameEl || !a.getAttribute('href')) return;
                    const name = nameEl.textContent.trim();
                    const img = imgEl ? imgEl.getAttribute('src') : '';
                    const url = a.getAttribute('href');
                    const skuMatch = url.match(/\\/(\\d+)$/);
                    const sku = skuMatch ? skuMatch[1] : '';
                    // Extract USD price - look for U$ pattern
                    const priceMatch = a.textContent.match(/U[$]\\s*([\\d.]+),?(\\d{0,2})/);
                    const price = priceMatch ? ('U$ ' + priceMatch[1] + ',' + (priceMatch[2] || '00')) : '';
                    if (name) results.push({ name, price, img, url, sku });
                });
                return results;
            """)

            if not products:
                continue

            parsed = []
            for p in products:
                href = p.get("url", "") or ""
                full_url = href if href.startswith("http") else f"https://atacadoconnect.com{href}"
                price = parse_usd_price(p.get("price"))
                if not price:
                    price = parse_gs_price(p.get("price"))
                sku = p.get("sku") or extract_sku(full_url, "atacado_connect")
                parsed.append({
                    "store": "atacado_connect",
                    "sku": sku,
                    "name": p.get("name", ""),
                    "price": price,
                    "description": None,
                    "image_url": p.get("img"),
                    "source_url": full_url,
                })
            return parsed

        except Exception as e:
            if attempt < 1:
                pass
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
    return []


# ─── MAIN ───────────────────────────────────────────────────────────────────

SCRAPERS = [
    ("Nissei", scrape_nissei_uc),
    ("Cell Shop", scrape_cellshop),
    ("Shopping China", scrape_shopping_china),
    ("Topdek", scrape_topdek),
    ("Visaovip", scrape_visaovip_uc),
    ("Atacado Connect", scrape_atacado_connect_uc),
    ("New Zone", scrape_new_zone),
]

STORE_KEYS = {
    "Nissei": "nissei",
    "Cell Shop": "cellshop",
    "Shopping China": "shopping_china",
    "Topdek": "topdek",
    "Visaovip": "visaovip",
    "Atacado Connect": "atacado_connect",
    "New Zone": "new_zone",
}

HTTP_DESC_STORES = {"cellshop", "shopping_china", "atacado_connect"}
UC_DESC_STORES = {"nissei", "visaovip"}


def main():
    print("=" * 60)
    print(f"EXTRACCION DE PRODUCTOS - Query: '{QUERY}'")
    print(f"Output: {OUT_DIR}")
    print("=" * 60)

    all_results = {}

    for name, scraper_fn in SCRAPERS:
        print(f"\n>> {name}...", end=" ")
        sys.stdout.flush()
        try:
            products = scraper_fn(QUERY)
            if products:
                store_key = STORE_KEYS.get(name, "")
                print(f"OK ({len(products)} productos)")
                p = products[0]
                price_str = ""
                if p["price"]:
                    price_str = f"Gs. {p['price']:,.0f}" if p["price"] > 10000 else f"USD {p['price']:,.2f}"
                sku_str = p.get("sku") or "-"
                print(f"     SKU: {sku_str} | {p['name'][:60]} | {price_str}")

                if store_key in HTTP_DESC_STORES:
                    print(f"    Descripciones via HTTP...")
                    products = enrich_descriptions(products, store_key)

                all_results[name] = (products, store_key)
                save_results(name, products)
            else:
                print("SIN RESULTADOS")
        except Exception as e:
            print(f"ERROR: {e}")

    # UC descriptions for SPA stores
    for name, store_key in [("Nissei", "nissei"), ("Visaovip", "visaovip")]:
        if name in all_results:
            products, _ = all_results[name]
            print(f"\n>> {name} descripciones via UC...")
            enrich_with_uc(products, store_key)
            save_results(name, products)

    # Download Nissei images via UC and upload to Supabase Storage
    if "Nissei" in all_results:
        products, _ = all_results["Nissei"]
        print(f"\n>> Nissei descarga de imagenes (Cloudflare bypass)...")
        products = download_nissei_images(products)
        save_results("Nissei", products)

    print(f"\nListo. Archivos en: {OUT_DIR}")


if __name__ == "__main__":
    main()
