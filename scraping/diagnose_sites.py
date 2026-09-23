"""Diagnostic script: fetch each site's homepage, save sanitized HTML and structure to JSON.

Run directly:  python diagnose_sites.py
Or via Flask endpoint:  GET /diagnose

Uses Scrapling to render client-side pages for accurate structure analysis.
"""

import json
import os
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup, Comment

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

SITES = [
    {
        "name": "Sams Club",
        "key": "sams_club",
        "url": "https://www.samsclub.com.br",
        "offers_url": "https://www.samsclub.com.br/ofertas-plus",
    },
    {
        "name": "Cometa",
        "key": "cometa",
        "url": "https://cometasupermercados.com.br",
        "offers_url": "https://clube.cometasupermercados.com.br/home",
    },
    {
        "name": "Pinheiro",
        "key": "pinheiro",
        "url": "https://www.lojaonline.pinheirosupermercado.com.br",
        "offers_url": "https://www.lojaonline.pinheirosupermercado.com.br/produtos",
    },
    {
        "name": "Mercadinho Sao Luiz",
        "key": "mercadinho",
        "url": "https://mercadinhossaoluiz.com.br",
        "offers_url": None,  # No known offers page
    },
    {
        "name": "Pao de Acucar",
        "key": "pao_de_acucar",
        "url": "https://www.paodeacucar.com",
        "offers_url": "https://www.paodeacucar.com/meu-desconto",
    },
]

DIAG_DIR = ROOT / "diagnostics"


def sanitize_html(html: str) -> str:
    """Remove script, style, noscript, and comments from HTML."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "iframe", "svg"]):
        tag.decompose()
    # Remove comments - use Comment class from bs4, not string matching
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()
    return str(soup)


def extract_links(soup: BeautifulSoup, base_url: str) -> list:
    """Extract all links that might be relevant (offers, categories, products)."""
    keywords = ("oferta", "promo", "busca", "produto", "categoria", "departamento")
    links = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue
        # Make absolute
        if href.startswith("http"):
            full = href
        else:
            full = base_url.rstrip("/") + "/" + href.lstrip("/")
        if full in seen:
            continue
        seen.add(full)
        if any(k in href.lower() for k in keywords) or any(k in text.lower() for k in keywords):
            links.append({"href": full, "text": text[:100]})
    return links


def extract_product_elements(soup: BeautifulSoup) -> list:
    """Find elements that look like product cards."""
    selectors = [
        "div.product", "div.product-item", "div.product-card", "div.card",
        "li.product", "article.product", "div.item", "div.produto",
        "div.product-tile", "div.product-grid-item", "div.product-list-item",
        "div.product-summary", "div.product-shelf",
    ]
    found = []
    for sel in selectors:
        els = soup.select(sel)
        if els:
            el = els[0]
            found.append({
                "selector": sel,
                "count": len(els),
                "classes": el.get("class"),
                "text_preview": el.get_text(strip=True)[:200]
            })
    return found


def fetch_with_requests(url: str) -> dict:
    """Fetch a URL with requests, return status, final URL, and soup."""
    resp = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
    soup = BeautifulSoup(resp.text, "lxml")
    return {
        "status": resp.status_code,
        "final_url": resp.url,
        "redirects": [{"status": r.status_code, "url": r.url} for r in resp.history],
        "soup": soup,
        "html": resp.text,
    }


def fetch_with_scrapling(url: str, wait_seconds: int = 5) -> dict:
    """Fetch a URL using Scrapling's stealth fetcher (renders JS)."""
    try:
        from scrapling.fetchers import StealthyFetcher
    except ImportError:
        raise RuntimeError("Scrapling is not installed. Run: pip install scrapling")

    # StealthyFetcher.fetch is a classmethod; wait is in milliseconds
    page = StealthyFetcher.fetch(
        url,
        headless=True,
        wait=wait_seconds * 1000,
    )
    html = page.html_content
    soup = BeautifulSoup(html, "lxml")
    return {
        "status": 200,
        "final_url": page.url,
        "redirects": [],
        "soup": soup,
        "html": html,
    }


def diagnose_site(site: dict) -> dict:
    """Fetch a site's homepage and offers page, return diagnostic data."""
    name = site["name"]
    key = site["key"]
    url = site["url"]
    offers_url = site.get("offers_url")
    print(f"=== {name} ({key}) ===")
    result = {
        "site_name": name,
        "site_key": key,
        "requested_url": url,
        "homepage": None,
        "offers_page": None,
        "error": None
    }
    try:
        # Try Scrapling first for rendered HTML, fallback to requests
        try:
            page = fetch_with_scrapling(url, wait_seconds=5)
            rendered = True
        except Exception as exc:
            print(f"  Scrapling failed: {exc}, falling back to requests")
            page = fetch_with_requests(url)
            rendered = False

        soup = page["soup"]
        homepage = {
            "status": page["status"],
            "final_url": page["final_url"],
            "redirects": page["redirects"],
            "rendered": rendered,
            "title": soup.title.get_text(strip=True) if soup.title else None,
            "html": sanitize_html(page["html"]),
            "links": extract_links(soup, page["final_url"]),
            "product_elements": extract_product_elements(soup),
        }
        result["homepage"] = homepage
        print(f"  Homepage: {page['status']}, Title: {homepage['title']}, Rendered: {rendered}")
        print(f"  Links: {len(homepage['links'])}, Product elements: {len(homepage['product_elements'])}")

        # Fetch offers page if known
        if offers_url:
            print(f"  Offers URL: {offers_url}")
            try:
                page2 = fetch_with_scrapling(offers_url, wait_seconds=6)
                soup2 = page2["soup"]
                offers = {
                    "url": offers_url,
                    "status": page2["status"],
                    "final_url": page2["final_url"],
                    "redirects": page2["redirects"],
                    "rendered": True,
                    "title": soup2.title.get_text(strip=True) if soup2.title else None,
                    "html": sanitize_html(page2["html"]),
                    "links": extract_links(soup2, page2["final_url"]),
                    "product_elements": extract_product_elements(soup2),
                }
                result["offers_page"] = offers
                print(f"  Offers page: {page2['status']}, Title: {offers['title']}")
                print(f"  Links: {len(offers['links'])}, Product elements: {len(offers['product_elements'])}")
            except Exception as exc:
                result["offers_page"] = {"url": offers_url, "error": str(exc)}
                print(f"  Offers page ERROR: {exc}")
        else:
            print("  No offers URL specified")
    except Exception as exc:
        result["error"] = str(exc)
        print(f"  ERROR: {exc}")
    return result


def run_diagnosis() -> list:
    """Run diagnosis for all sites and save JSON files. Returns list of written files."""
    DIAG_DIR.mkdir(exist_ok=True)
    written = []
    for site in SITES:
        data = diagnose_site(site)
        filepath = DIAG_DIR / f"{site['key']}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        written.append(str(filepath))
        print(f"  Saved to {filepath}")
    return written


if __name__ == "__main__":
    files = run_diagnosis()
    print(f"Diagnosis complete. Files written: {len(files)}")
    for f in files:
        print(f"  {f}")