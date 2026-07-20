# CDE Store Scrapers

Unified price comparison tool that scrapes product data (name, price, SKU, description, image URL) from Paraguayan e-commerce stores in Ciudad del Este.

## Supported Stores

| Store | URL | Tech Stack | Scraping Method | Products | Description |
|-------|-----|-----------|----------------|----------|-------------|
| **Nissei** | nissei.com | Magento (Cloudflare) | `undetected-chromedriver` | 20 | ❌ No |
| **Cell Shop** | cellshop.com.py | Magento (SSR) | `curl_cffi` + BeautifulSoup | 33 | ✅ HTTP |
| **Shopping China** | shoppingchina.com.py | Custom (SSR) | `curl_cffi` + BeautifulSoup | 24 | ✅ HTTP |
| **Topdek** | topdekinformatica.com.br | Custom (SSR) | `curl_cffi` + BeautifulSoup | 32 | ❌ No |
| **Visaovip** | visaovip.com | Next.js (SPA) | `undetected-chromedriver` | 24 | ❌ No |
| **Atacado Connect** | atacadoconnect.com | Next.js (SPA listings, SSR details) | `undetected-chromedriver` + `curl_cffi` | 20 | ✅ HTTP |
| **New Zone** | newzone.com.py | Custom (SSR) | `curl_cffi` + BeautifulSoup | 84 | ❌ No |

**Total: 237 products** (query: "notebook")

## Requirements

- Python 3.13+
- Google Chrome / Chromium browser
- [undetected-chromedriver](https://github.com/ultrafunkamsterdam/undetected-chromedriver) (for Cloudflare/SPA stores)

### Python Dependencies

```
curl_cffi
beautifulsoup4
lxml
undetected-chromedriver
python-dotenv
pandas
supabase
```

### Chrome Binary Path

The scraper expects Chrome at:
```
%LOCALAPPDATA%\ms-playwright\chromium-1228\chrome-win64\chrome.exe
```

Edit `CHROME_PATH` in `extract_all.py` if your Chrome is elsewhere.

## Usage

```bash
# Set up virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install curl_cffi beautifulsoup4 lxml undetected-chromedriver pandas supabase python-dotenv

# Run all scrapers
python extract_all.py

# Output: json_extracted/*.json
```

### Environment Variables (optional)

Copy `.env.example` to `.env` and configure:
- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_KEY` - Supabase API key

## Output Format

Each store produces a JSON file with this schema:

```json
[
  {
    "store": "cellshop",
    "sku": "5875412",
    "name": "Lápiz Stylus Joog Pro 2 JGP-02 Compatible con iPad - White",
    "price": 184750.0,
    "description": "El lápiz Joog Pro Stylus 2 JGP-02 para iPad...",
    "image_url": "https://cellshop.com.py/media/catalog/product/...",
    "source_url": "https://cellshop.com.py/5875412-lapiz-stylus..."
  }
]
```

- `price` is always a float (Gs. for local stores, USD for USD-priced stores)
- `description` may be `null` for stores without description extraction
- `sku` is the store's product identifier

## Architecture

### Scraper Categories

**1. SSR Stores (HTTP requests)**
Cell Shop, Shopping China, Topdek, New Zone
- Simple `requests` with `curl_cffi` impersonating Chrome
- Parse HTML with BeautifulSoup
- No JavaScript execution needed

**2. Cloudflare Stores (undetected-chromedriver)**
Nissei
- Uses `undetected-chromedriver` to bypass Cloudflare "Under Attack" mode
- Injects JavaScript to extract product data from DOM

**3. Next.js SPA Stores (undetected-chromedriver)**
Visaovip, Atacado Connect
- Product listings rendered client-side (empty HTML without JS)
- Uses `undetected-chromedriver` to wait for JS rendering
- Extracts product data via `execute_script()`

### Description Extraction

Post-processing step for stores with accessible detail pages:
- **Cell Shop**: JSON-LD structured data or `.description` div
- **Shopping China**: `<meta name="description">` tag
- **Atacado Connect**: `<meta property="og:description">` tag

## Bypass Techniques

### Cloudflare "Under Attack" (Nissei)
- `undetected-chromedriver` mimics real browser behavior
- Waits for Cloudflare challenge to auto-resolve (up to 15s)
- Extracts product data from the rendered DOM
- Falls back to retry if challenge not resolved

### Next.js SPA (Visaovip, Atacado Connect)
- Browser loads the page and waits for JS to execute (8s)
- Query selectors target client-rendered React components
- Atacado Connect listing also works with UC; detail pages are SSR

## Store-Specific Details

### Nissei
- **Challenge**: Cloudflare "Under Attack" + Magento JS
- **SKU**: `data-product-id` attribute on product cards
- **Price**: Format `Gs. X.XXX.XXX` parsed via `parse_gs_price()`

### Cell Shop
- **Method**: `curl_cffi` + BeautifulSoup
- **SKU**: Numeric prefix in product URL
- **Price**: Magento price wrapper with `Gs.` or `$` format
- **Description**: JSON-LD structured data on detail page

### Shopping China
- **Method**: `curl_cffi` + BeautifulSoup
- **SKU**: Numeric suffix in product URL `/producto/.../1040416`
- **Price**: `.lightning-prod-sale` element
- **Description**: Meta description tag

### Topdek
- **Method**: `curl_cffi` + BeautifulSoup
- **SKU**: Numeric ID in URL `/324020.html`
- **Selector**: `.product` class containers
- **Note**: No product-specific descriptions available

### Visaovip
- **Challenge**: Next.js SPA (no SSR)
- **Method**: `undetected-chromedriver` with category URL
- **SKU**: `texto-cinza-200` span or URL suffix
- **Price**: `U$ X.XXX,XX` format via `parse_usd_price()`

### Atacado Connect
- **Challenge**: Next.js SPA listing, SSR detail pages
- **Method**: UC for listing, `curl_cffi` for descriptions
- **SKU**: Numeric suffix in URL
- **Price**: USD regex match from card text content
- **Description**: `og:description` meta tag

### New Zone
- **Method**: `curl_cffi` + BeautifulSoup
- **SKU**: `/producto/{id}/slug` URL pattern
- **Price**: `$X.XXX` dollar format from card text
- **Note**: 84 products, homepage SSR has product data

## Files

| File | Purpose |
|------|---------|
| `extract_all.py` | Main scraper - runs all 7 stores |
| `stores/cellshop.py` | Modular Cell Shop scraper (legacy) |
| `stores/nissei.py` | Modular Nissei scraper (legacy) |
| `stores/visaovip.py` | Modular Visaovip scraper (legacy) |
| `stores/atacado_games.py` | Modular Atacado scraper (legacy) |
| `common.py` | Shared utilities (fetch, parse, delay) |
| `json_extracted/` | Output directory for JSON results |
| `.env` | Supabase credentials (optional) |

## Notes

- Running on Windows with Python 3.13
- Chrome binary via Playwright at `%LOCALAPPDATA%\ms-playwright\chromium-1228\chrome-win64\chrome.exe`
- `undetected-chromedriver` uses `version_main=149` to match Chrome 149
- Descriptions not available on listing pages - require per-product detail page requests
