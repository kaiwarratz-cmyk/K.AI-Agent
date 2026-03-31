"""
web_toolkit.py – K.AI Core Web Toolkit
Stabile, getestete Web-Funktionen als Core-Tool.
KEIN LLM-generierter Code – direkt eingebunden.

Funktionen:
  fetch_text(url, ...)          → sauberer Text einer Webseite (statisch via requests)
  fetch_text_js(url, ...)       → sauberer Text via Playwright (für JS-gerenderte Seiten)
  fetch_json(url, ...)          → JSON-Antwort einer API
  fetch_html(url, ...)          → roher HTML-Quellcode
  extract_links(url/html, ...)  → alle Links von einer Seite
  extract_text(html)            → sauberer Text aus HTML-String
  download_file(url, dest, ...) → Datei herunterladen
  search_web(query, ...)        → DuckDuckGo-Suche via ddgs-Paket
  fetch_public_data(kind, ...)  → kostenlose Daten ohne API-Key (Wetter etc.)
  post_form(url, data, ...)     → HTTP POST mit Formulardaten

Aliases: web_fetch, web_fetch_js, web_search, web_public_data
"""

from __future__ import annotations

import os
import re
import json
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

_ROOT_DIR = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# HTTP-Hilfsfunktion – immer mit Retry und vernünftigem User-Agent
# ---------------------------------------------------------------------------
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _get_requests():
    try:
        import requests as _r
        return _r
    except ImportError:
        raise ImportError("requests nicht installiert – pip install requests")


def _http_get(url: str, timeout: int = 15, headers: Optional[Dict] = None,
              retries: int = 2, allow_redirects: bool = True) -> Any:
    """
    Robuster HTTP-GET mit Retry-Logik und SSL-Fallback.
    Nutzt curl_cffi (Chrome-Impersonation, umgeht Cloudflare/Bot-Detection) wenn verfügbar,
    fällt sonst auf requests zurück.
    """
    hdrs = {**_DEFAULT_HEADERS, **(headers or {})}
    last_err = None

    # curl_cffi bevorzugen: impersoniert echten Chrome-Browser auf TLS-Ebene
    try:
        from curl_cffi import requests as cffi_req
        for attempt in range(retries + 1):
            try:
                resp = cffi_req.get(
                    url, headers=hdrs, timeout=timeout,
                    allow_redirects=allow_redirects,
                    impersonate="chrome120",
                )
                resp.raise_for_status()
                return resp
            except Exception as e:
                last_err = e
                if attempt < retries:
                    time.sleep(1.0)
        raise last_err
    except ImportError:
        pass

    # Fallback: standard requests
    req = _get_requests()
    for attempt in range(retries + 1):
        try:
            verify = attempt < 1
            resp = req.get(url, headers=hdrs, timeout=timeout,
                           allow_redirects=allow_redirects, verify=verify)
            resp.raise_for_status()
            return resp
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(1.0)
    raise last_err


def _parse_html(html: str):
    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "html.parser")
    except ImportError:
        raise ImportError("beautifulsoup4 nicht installiert – pip install beautifulsoup4")


def _extract_text_trafilatura(html: str, url: str = "") -> Optional[str]:
    """
    Nutzt trafilatura für saubere Artikel-/Content-Extraktion.
    Deutlich besser als BS4 für Boilerplate-Entfernung.
    Gibt None zurück wenn trafilatura nicht verfügbar oder kein Content erkannt.
    """
    try:
        import trafilatura
        text = trafilatura.extract(
            html,
            url=url or None,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
            favor_recall=True,
        )
        return text
    except ImportError:
        return None
    except Exception:
        return None


def _clean_text(soup, html: str = "", url: str = "") -> str:
    """
    Entfernt Boilerplate (nav, header, footer, ads) und liefert sauberen Text.
    Nutzt trafilatura wenn verfügbar (deutlich besser), sonst BS4-Fallback.
    """
    # trafilatura ist die beste kostenlose Lösung für Content-Extraktion
    if html:
        extracted = _extract_text_trafilatura(html, url=url)
        if extracted and len(extracted.strip()) > 100:
            return extracted

    # BS4-Fallback
    for tag in soup.find_all(["nav", "header", "footer", "script", "style",
                               "noscript", "aside", "form", "button",
                               "iframe", "img", "svg"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [l.strip() for l in text.splitlines()]
    lines = [l for l in lines if len(l) > 2]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------------

def fetch_text(url: str, timeout: int = 15, max_chars: int = 20000,
               selector: str = "", _allow_smart_fallback: bool = True) -> Dict[str, Any]:
    """
    Lädt eine Webseite und liefert sauberen Text (ohne Navigation/Werbung).
    Nutzt curl_cffi (Chrome-Impersonation) + trafilatura (beste Content-Extraktion).
    Fällt bei JS-gerenderten Seiten automatisch auf fetch_smart (Crawl4AI) zurück.
    selector: optional CSS-Selektor für gezielten Bereich (z.B. 'article', '#content')
    """
    try:
        resp = _http_get(url, timeout=timeout)
        html_raw = resp.text

        # trafilatura: beste kostenlose Content-Extraktion (kein Selektor nötig)
        if not selector:
            extracted = _extract_text_trafilatura(html_raw, url=str(resp.url))
            if extracted and len(extracted.strip()) > 100:
                soup = _parse_html(html_raw)
                title = ""
                title_tag = soup.find("title")
                if title_tag:
                    title = title_tag.get_text(strip=True)[:200]
                return {
                    "ok": True,
                    "url": str(resp.url),
                    "title": title,
                    "text": extracted[:max_chars],
                    "chars": len(extracted),
                    "truncated": len(extracted) > max_chars,
                    "extractor": "trafilatura",
                }

        # BS4-Fallback (mit Selektor oder wenn trafilatura keinen Content findet)
        soup = _parse_html(html_raw)
        if selector:
            node = soup.select_one(selector)
            if node:
                soup = node
        text = _clean_text(soup, html=html_raw, url=str(resp.url))
        title = ""
        title_tag = soup.find("title") if hasattr(soup, "find") else None
        if title_tag:
            title = title_tag.get_text(strip=True)[:200]

        # Automatischer Fallback: wenn Text zu dünn → Seite ist wahrscheinlich JS-gerendert
        if _allow_smart_fallback and len(text.strip()) < 300 and not selector:
            smart = fetch_smart(url, delay=2.0, max_chars=max_chars)
            if smart.get("ok") and len(smart.get("markdown", "").strip()) > len(text.strip()):
                smart["text"] = smart.pop("markdown", "")
                smart["fallback_used"] = "fetch_smart"
                return smart

        return {
            "ok": True,
            "url": str(resp.url),
            "title": title,
            "text": text[:max_chars],
            "chars": len(text),
            "truncated": len(text) > max_chars,
            "extractor": "bs4",
        }
    except Exception as e:
        # Bei HTTP-Fehler auch direkt fetch_smart versuchen
        if _allow_smart_fallback:
            try:
                smart = fetch_smart(url, delay=2.0, max_chars=max_chars)
                if smart.get("ok"):
                    smart["text"] = smart.pop("markdown", "")
                    smart["fallback_used"] = "fetch_smart"
                    return smart
            except Exception:
                pass
        return {"ok": False, "error": str(e), "traceback": traceback.format_exc()}


def fetch_html(url: str, timeout: int = 15) -> Dict[str, Any]:
    """Liefert den rohen HTML-Quellcode einer URL."""
    try:
        resp = _http_get(url, timeout=timeout)
        return {"ok": True, "url": str(resp.url), "html": resp.text, "status": resp.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e), "traceback": traceback.format_exc()}


def fetch_json(url: str, timeout: int = 15, params: Optional[Dict] = None,
               headers: Optional[Dict] = None) -> Dict[str, Any]:
    """Ruft eine JSON-API ab und liefert das geparste Objekt."""
    try:
        req = _get_requests()
        hdrs = {**_DEFAULT_HEADERS, "Accept": "application/json", **(headers or {})}
        resp = req.get(url, headers=hdrs, params=params or {}, timeout=timeout)
        resp.raise_for_status()
        return {"ok": True, "url": str(resp.url), "data": resp.json()}
    except Exception as e:
        return {"ok": False, "error": str(e), "traceback": traceback.format_exc()}


def extract_links(source: str, base_url: str = "", filter_pattern: str = "",
                  same_domain: bool = False, timeout: int = 15) -> Dict[str, Any]:
    """
    Extrahiert alle Links von einer URL oder aus einem HTML-String.
    source: URL oder HTML-String
    filter_pattern: Regex-Filter auf den href (z.B. r'/wiki/')
    same_domain: nur Links zur gleichen Domain
    """
    try:
        if source.startswith("http://") or source.startswith("https://"):
            resp = _http_get(source, timeout=timeout)
            html = resp.text
            base_url = base_url or str(resp.url)
        else:
            html = source

        soup = _parse_html(html)
        parsed_base = urlparse(base_url)
        links: List[Dict[str, str]] = []
        seen = set()

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue
            full = urljoin(base_url, href) if base_url else href
            if full in seen:
                continue
            seen.add(full)

            if same_domain and base_url:
                if urlparse(full).netloc != parsed_base.netloc:
                    continue
            if filter_pattern and not re.search(filter_pattern, full):
                continue

            links.append({
                "text": a.get_text(strip=True)[:120],
                "href": full,
            })

        return {"ok": True, "count": len(links), "links": links}
    except Exception as e:
        return {"ok": False, "error": str(e), "traceback": traceback.format_exc()}


def extract_text(html: str, selector: str = "", max_chars: int = 20000) -> Dict[str, Any]:
    """Extrahiert sauberen Text aus einem HTML-String."""
    try:
        soup = _parse_html(html)
        if selector:
            node = soup.select_one(selector)
            if node:
                soup = node
        text = _clean_text(soup)
        return {"ok": True, "text": text[:max_chars], "chars": len(text)}
    except Exception as e:
        return {"ok": False, "error": str(e), "traceback": traceback.format_exc()}


def download_file(url: str, dest_path: str = "", timeout: int = 300, max_mb: int = 20480,
                  progress_cb=None) -> Dict[str, Any]:
    """
    Lädt eine Datei herunter.
    dest_path: Zielpfad (default: data/workspace/downloads/<dateiname>)
    max_mb: Maximale Dateigröße in MB (default: 20480 = 20 GB). 0 = kein Limit.
    progress_cb: Optionaler Callback(pct: int, mb_done: float, mb_total: float) für Fortschrittsanzeige.
    """
    import time as _time
    try:
        # curl_cffi bevorzugen: umgeht Cloudflare/Bot-Protection (TLS-Fingerprint-Spoofing)
        try:
            from curl_cffi import requests as _cffi
            resp = _cffi.get(url, headers=_DEFAULT_HEADERS, timeout=timeout,
                             stream=True, allow_redirects=True, impersonate="chrome120")
        except ImportError:
            req = _get_requests()
            resp = req.get(url, headers=_DEFAULT_HEADERS, timeout=timeout,
                           stream=True, allow_redirects=True)
        resp.raise_for_status()

        # Content-Type Check: HTML statt Datei = Redirect/Landingpage, nicht die echte Datei
        content_type = resp.headers.get("Content-Type", "").lower().split(";")[0].strip()
        if content_type in ("text/html", "application/xhtml+xml"):
            return {"ok": False, "error": (
                f"URL liefert HTML statt einer Datei (Content-Type: {content_type}). "
                "Die URL zeigt wahrscheinlich auf eine Download-Landingpage. "
                "Bitte den direkten Datei-Link verwenden (z.B. aus Content-Disposition oder CDN-URL)."
            )}

        # Größencheck via Content-Length Header (falls vorhanden)
        if max_mb > 0:
            content_length = resp.headers.get("Content-Length")
            if content_length:
                size_mb = int(content_length) / 1024 / 1024
                if size_mb > max_mb:
                    return {"ok": False, "error": f"Datei zu groß: {size_mb:.0f} MB > Limit {max_mb} MB. Erhöhe max_mb."}

        # Dateiname: immer aus URL oder Content-Disposition ableiten, nie aus dest_path übernehmen
        cd_header = resp.headers.get("Content-Disposition", "")
        cd_match = __import__("re").search(r'filename\*?=["\']?(?:UTF-8\'\')?([^"\';\s]+)', cd_header, __import__("re").IGNORECASE)
        url_filename = url.split("/")[-1].split("?")[0].strip() or "download"
        filename = cd_match.group(1).strip() if cd_match else url_filename

        # Extension ergänzen wenn URL keinen Dateityp enthält (z.B. Unsplash-Links)
        if "." not in filename or len(filename.rsplit(".", 1)[-1]) > 5:
            _mime_ext_map = {
                "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
                "image/webp": ".webp", "image/bmp": ".bmp", "image/svg+xml": ".svg",
                "application/pdf": ".pdf", "application/zip": ".zip",
                "video/mp4": ".mp4", "video/webm": ".webm",
                "audio/mpeg": ".mp3", "audio/ogg": ".ogg",
                "text/plain": ".txt", "text/html": ".html",
                "application/json": ".json",
            }
            _ct_base = content_type.split(";")[0].strip()
            _ext = _mime_ext_map.get(_ct_base, "")
            if _ext:
                filename = filename + _ext

        if not dest_path:
            dl_dir = _ROOT_DIR / "data" / "workspace" / "downloads"
            dl_dir.mkdir(parents=True, exist_ok=True)
            dest_path = str(dl_dir / filename)
        else:
            # dest_path darf nur ein Verzeichnis angeben – Dateiname kommt immer aus der URL
            dp = Path(dest_path)
            if dp.suffix and dp.suffix.lower() != Path(filename).suffix.lower():
                # LLM hat eigenen Dateinamen halluziniert → ignorieren, Verzeichnis behalten
                dp = dp.parent
            if not dp.suffix:
                # dest_path ist ein Verzeichnis
                dp.mkdir(parents=True, exist_ok=True)
                dest_path = str(dp / filename)
            else:
                dest_path = str(dp)

        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)

        max_bytes = max_mb * 1024 * 1024 if max_mb > 0 else float("inf")
        total = 0
        total_mb = int(resp.headers.get("Content-Length", 0)) / 1024 / 1024
        _last_report_t = _time.monotonic() - 3.0  # erste Meldung schon nach 2s
        _last_pct = -1

        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    total += len(chunk)
                    if total > max_bytes:
                        dest.unlink(missing_ok=True)
                        return {"ok": False, "error": f"Download abgebrochen: Datei überschreitet {max_mb} MB Limit. Erhöhe max_mb."}
                    f.write(chunk)
                    if progress_cb:
                        now = _time.monotonic()
                        mb_done = total / 1024 / 1024
                        if total_mb > 0:
                            pct = min(99, int(mb_done / total_mb * 100))
                        else:
                            pct = -1  # unbekannte Gesamtgröße
                        # Fortschritt alle 2s senden (egal ob Content-Length bekannt)
                        if pct != _last_pct and (now - _last_report_t) >= 2.0:
                            _last_pct = pct
                            _last_report_t = now
                            try:
                                progress_cb(pct, mb_done, total_mb)
                            except Exception:
                                pass

        # Abschlussmeldung (100%)
        if progress_cb:
            try:
                mb_final = total / 1024 / 1024
                progress_cb(100, mb_final, mb_final)
            except Exception:
                pass

        return {"ok": True, "path": str(dest), "bytes": total,
                "mb": round(total / 1024 / 1024, 2)}
    except Exception as e:
        return {"ok": False, "error": str(e), "traceback": traceback.format_exc()}


def search_web(query: str, max_results: int = 10,
               region: str = "de-de") -> Dict[str, Any]:
    """
    DuckDuckGo-Websuche via ddgs-Paket.
    Gibt Liste von {title, href, body} zurück.
    """
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        if not query or not query.strip():
            return {"ok": False, "error": "Leere Suchanfrage"}

        with DDGS() as ddgs:
            raw = list(ddgs.text(query.strip(), max_results=max_results, region=region))

        if not raw:
            # Zweiter Versuch mit engl. Region
            with DDGS() as ddgs:
                raw = list(ddgs.text(query.strip(), max_results=max_results, region="en-us"))

        if not raw:
            return {
                "ok": False,
                "rate_limited": True,
                "error": "Keine Suchergebnisse – DuckDuckGo-Rate-Limit aktiv. Alternativen: direkt URL abrufen oder gecachte Daten nutzen.",
                "results": [],
            }

        return {"ok": True, "count": len(raw), "results": raw}
    except Exception as e:
        return {"ok": False, "error": str(e), "traceback": traceback.format_exc()}


def fetch_public_data(kind: str, location: str = "", **kwargs) -> Dict[str, Any]:
    """
    Ruft öffentlich verfügbare Daten ohne API-Key ab.
    kind: 'weather' | 'weather_full' | 'ip' | 'exchange_rate' | 'wikipedia'
    location: Stadt, ISO-Code, etc.
    """
    try:
        req = _get_requests()

        if kind in ("weather", "weather_full"):
            city = (location or kwargs.get("city", "")).strip()
            if not city:
                return {"ok": False, "error": "location/city erforderlich"}
            fmt = "j1" if kind == "weather_full" else "3"
            url = f"https://wttr.in/{city}?format={fmt}"
            resp = req.get(url, headers=_DEFAULT_HEADERS, timeout=10)
            if kind == "weather_full":
                return {"ok": True, "data": resp.json()}
            return {"ok": True, "text": resp.text.strip(), "city": city}

        elif kind == "ip":
            resp = req.get("https://ipinfo.io/json", timeout=8)
            return {"ok": True, "data": resp.json()}

        elif kind == "exchange_rate":
            base = kwargs.get("base", "EUR").upper()
            target = kwargs.get("target", "USD").upper()
            resp = req.get(
                f"https://api.frankfurter.app/latest?from={base}&to={target}",
                timeout=8,
            )
            data = resp.json()
            rate = data.get("rates", {}).get(target)
            return {"ok": True, "base": base, "target": target, "rate": rate, "raw": data}

        elif kind == "wikipedia":
            title = (location or kwargs.get("title", "")).replace(" ", "_")
            lang = kwargs.get("lang", "de")
            from urllib.parse import quote
            title_encoded = quote(title, safe="")
            resp = req.get(
                f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title_encoded}",
                timeout=10,
                headers={**_DEFAULT_HEADERS, "Accept": "application/json"},
            )
            data = resp.json()
            return {
                "ok": True,
                "title": data.get("title"),
                "extract": data.get("extract", ""),
                "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
            }

        else:
            return {"ok": False, "error": f"Unbekannter kind: '{kind}'. Verfügbar: weather, weather_full, ip, exchange_rate, wikipedia"}

    except Exception as e:
        return {"ok": False, "error": str(e), "traceback": traceback.format_exc()}


def post_form(url: str, data: Dict[str, Any], timeout: int = 15,
              as_json: bool = False, headers: Optional[Dict] = None) -> Dict[str, Any]:
    """HTTP POST – Formulardaten oder JSON."""
    try:
        req = _get_requests()
        hdrs = {**_DEFAULT_HEADERS, **(headers or {})}
        if as_json:
            resp = req.post(url, json=data, headers=hdrs, timeout=timeout)
        else:
            resp = req.post(url, data=data, headers=hdrs, timeout=timeout)
        resp.raise_for_status()
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return {"ok": True, "status": resp.status_code, "body": body}
    except Exception as e:
        return {"ok": False, "error": str(e), "traceback": traceback.format_exc()}


def fetch_text_js(url: str, timeout: int = 30, max_chars: int = 20000,
                  selector: str = "", wait_selector: str = "",
                  wait_ms: int = 2000) -> Dict[str, Any]:
    """
    Lädt eine JavaScript-gerenderte Webseite via Playwright (Headless Chromium).
    Nutze diese Funktion für Seiten, die per JS dynamisch Inhalte nachladen
    (z.B. Printables.com, SPAs, React/Vue/Angular-Apps).

    selector:      CSS-Selektor für gezielten Bereich (optional)
    wait_selector: CSS-Selektor auf den gewartet wird bevor Inhalt gelesen wird (optional)
    wait_ms:       Zusätzliche Wartezeit nach dem Laden in Millisekunden (default: 2000)
    """
    import concurrent.futures

    def _run_playwright() -> Dict[str, Any]:
        try:
            import asyncio
            # sync_playwright benötigt einen sauberen Event-Loop im Thread.
            # Verhindert: 'PlaywrightContextManager' object has no attribute '_playwright'
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    asyncio.set_event_loop(asyncio.new_event_loop())
            except RuntimeError:
                asyncio.set_event_loop(asyncio.new_event_loop())

            from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                try:
                    ctx = browser.new_context(
                        user_agent=_DEFAULT_HEADERS["User-Agent"],
                        locale="de-DE",
                    )
                    page = ctx.new_page()
                    page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
                    if wait_selector:
                        try:
                            page.wait_for_selector(wait_selector, timeout=timeout * 1000)
                        except PWTimeout:
                            pass
                    if wait_ms > 0:
                        page.wait_for_timeout(wait_ms)
                    final_url = page.url
                    title = page.title()
                    html = page.content()
                finally:
                    browser.close()

            soup = _parse_html(html)
            if selector:
                node = soup.select_one(selector)
                if node:
                    soup = node
            text = _clean_text(soup)
            return {
                "ok": True,
                "url": final_url,
                "title": title[:200],
                "text": text[:max_chars],
                "chars": len(text),
                "truncated": len(text) > max_chars,
                "js_rendered": True,
            }
        except ImportError:
            return {"ok": False, "error": "playwright nicht installiert – pip install playwright && playwright install chromium"}
        except Exception as e:
            return {"ok": False, "error": str(e), "traceback": traceback.format_exc()}

    # Playwright's sync_api verträgt sich nicht mit asyncio-Event-Loops.
    # Daher immer in einem eigenen Thread ausführen.
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_run_playwright)
            return future.result(timeout=timeout + 15)
    except concurrent.futures.TimeoutError:
        return {"ok": False, "error": f"web_fetch_js Timeout nach {timeout + 15}s"}
    except Exception as e:
        return {"ok": False, "error": str(e), "traceback": traceback.format_exc()}


def _github_url_to_raw(url: str) -> Optional[str]:
    """Wandelt github.com-URLs in abrufbare Raw-Inhalte um (kein Playwright nötig)."""
    import re as _re
    # blob-URL: github.com/owner/repo/blob/branch/path/file → raw.githubusercontent.com
    m = _re.match(r'https?://github\.com/([^/]+/[^/]+)/blob/([^/]+)/(.+)', url)
    if m:
        return f"https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}/{m.group(3)}"
    return None


def _github_fetch_readme(owner: str, repo: str, max_chars: int) -> Optional[Dict[str, Any]]:
    """Holt README via GitHub API (kein Auth nötig für öffentliche Repos)."""
    try:
        req = _get_requests()
        api_url = f"https://api.github.com/repos/{owner}/{repo}/readme"
        resp = req.get(api_url,
                       headers={**_DEFAULT_HEADERS, "Accept": "application/vnd.github.v3.raw"},
                       timeout=15)
        if resp.status_code == 200:
            content = resp.text
            return {
                "ok": True,
                "url": f"https://github.com/{owner}/{repo}",
                "title": f"{owner}/{repo} README",
                "markdown": content[:max_chars],
                "chars": len(content),
                "truncated": len(content) > max_chars,
                "links": [], "links_count": 0,
                "metadata": {}, "js_rendered": False,
            }
    except Exception:
        pass
    return None


def fetch_smart(url: str, delay: float = 3.0, max_chars: int = 50000,
                scroll: bool = True, js_code: str = "",
                filter_links: str = "") -> Dict[str, Any]:
    """
    Intelligenter Web-Fetch via Crawl4AI (Headless Chromium + Markdown-Extraktion).

    Gegenüber fetch_text_js bietet fetch_smart:
    - Sauberes **Markdown** statt rohem HTML (kompakter, direkt für LLM lesbar)
    - Automatisches Warten auf JS-Rendering (delay Sekunden nach Seitenload)
    - Scroll-Trigger für Lazy-Loading (scroll=True)
    - Eigenen JS-Code ausführen (z.B. Buttons klicken, Formulare füllen)
    - Vollständige Link-Extraktion mit Text + href
    - Metadaten (title, description, og:image …)

    Nutze **fetch_smart** statt fetch_text_js für:
    - JS-SPAs (React, Vue, Angular): Thingiverse, Printables, Cults3D …
    - Seiten mit Lazy Loading / Infinite Scroll
    - Seiten mit verzögertem Content (Timer, Skeleton-Loading)
    - Überall wo fetch_text keinen Inhalt liefert

    Parameter:
      url          URL der Seite
      delay        Sekunden nach Seitenload warten bevor Inhalt gelesen wird (default: 3.0)
      max_chars    Maximale Zeichen im Markdown-Output (default: 50000)
      scroll       Scroll nach unten um Lazy Loading zu triggern (default: True)
      js_code      Optionaler JavaScript-Code der auf der Seite ausgeführt wird
      filter_links Regex-Filter auf Link-hrefs (z.B. '/thing:' oder '/model/')
    """
    import concurrent.futures
    import asyncio
    import re as _re

    # GitHub blob-URLs → raw.githubusercontent.com (kein Playwright, kein Rate-Limit)
    raw_url = _github_url_to_raw(url)
    if raw_url:
        return fetch_text(raw_url, timeout=20, max_chars=max_chars, _allow_smart_fallback=False)

    # GitHub Repo-Hauptseite → README via GitHub API holen
    gh_repo = _re.match(r'https?://github\.com/([^/]+)/([^/?#]+)(?:[/?#].*)?$', url)
    if gh_repo:
        result = _github_fetch_readme(gh_repo.group(1), gh_repo.group(2), max_chars)
        if result:
            return result

    async def _run() -> Dict[str, Any]:
        try:
            from crawl4ai import (AsyncWebCrawler, CrawlerRunConfig, BrowserConfig,
                                  CacheMode, AsyncLoggerBase)
        except ImportError:
            return {"ok": False, "error": "crawl4ai nicht installiert – pip install crawl4ai"}
        try:
            # Null-Logger: verhindert Rich-Console-Ausgabe (Windows-Encoding-Probleme)
            class _NullLogger(AsyncLoggerBase):
                def debug(self, *a, **kw): pass
                def info(self, *a, **kw): pass
                def success(self, *a, **kw): pass
                def warning(self, *a, **kw): pass
                def error(self, *a, **kw): pass
                def url_status(self, *a, **kw): pass
                def error_status(self, *a, **kw): pass

            cfg = BrowserConfig(headless=True, verbose=False)
            run_cfg = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                wait_for="body",
                page_timeout=30000,
                delay_before_return_html=float(delay),
                js_code=js_code or ("window.scrollTo(0, document.body.scrollHeight / 2);" if scroll else ""),
            )
            async with AsyncWebCrawler(config=cfg, logger=_NullLogger()) as crawler:
                result = await crawler.arun(url, config=run_cfg)

            if not result.success:
                return {"ok": False, "error": result.error_message or "Unbekannter Fehler"}

            md = result.markdown or ""

            # Rate-limit / bot-block erkannt → Fallback auf plain HTTP
            title_low = (((result.metadata or {}).get("title") or "") + md[:200]).lower()
            if any(x in title_low for x in ("too many requests", "rate limit", "access denied",
                                             "403 forbidden", "captcha", "just a moment")):
                fallback = fetch_text(url, timeout=20, max_chars=max_chars, _allow_smart_fallback=False)
                if fallback.get("ok") and fallback.get("text", "").strip():
                    fallback["markdown"] = fallback.pop("text")
                    fallback["js_rendered"] = False
                    return fallback

            # Links zusammenstellen
            raw_links = result.links or {}
            all_links = raw_links.get("internal", []) + raw_links.get("external", [])
            if filter_links:
                import re as _re
                all_links = [l for l in all_links if _re.search(filter_links, l.get("href", ""))]

            link_lines = [
                f"{l.get('text', '')[:80] or '(kein Text)'} → {l.get('href', '')}"
                for l in all_links[:300]
            ]

            return {
                "ok": True,
                "url": result.url,
                "title": ((result.metadata or {}).get("title") or "")[:200],
                "markdown": md[:max_chars],
                "chars": len(md),
                "truncated": len(md) > max_chars,
                "links_count": len(all_links),
                "links": link_lines,
                "metadata": result.metadata or {},
                "js_rendered": True,
                "crawl4ai": True,
            }
        except Exception as e:
            return {"ok": False, "error": str(e), "traceback": traceback.format_exc()}

    def _thread_run() -> Dict[str, Any]:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(_thread_run).result(timeout=60)
    except concurrent.futures.TimeoutError:
        return {"ok": False, "error": "fetch_smart Timeout nach 60s"}
    except Exception as e:
        return {"ok": False, "error": str(e), "traceback": traceback.format_exc()}


# ── Aliases für Dynamic Tools ──────────────────────────────────────────────
# In dynamic tool code: from app.tools.web_toolkit import web_public_data, web_search, web_fetch
web_public_data  = fetch_public_data
web_search       = search_web
web_fetch        = fetch_text
web_fetch_js     = fetch_text_js
web_fetch_smart  = fetch_smart
