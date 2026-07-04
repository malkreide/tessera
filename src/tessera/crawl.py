"""Crawl: offizielle Quellseiten -> sauberes Markdown (Snapshots).

Multi-modaler Fetch mit Auto-Erkennung, in der richtigen Reihenfolge:

1. **SSR zuerst** (httpx + Trafilatura). Die meisten Quellseiten (stadt-zuerich.ch,
   zh.ch) sind serverseitig gerendert — ein HTTP-Abruf genuegt und ist robust:
   `curl`/httpx gehen durch Proxys, ein Headless-Browser oft nicht.
2. **SPA nur als Fallback** (Crawl4AI/Headless). Erst wenn die Seite als echte
   JS-SPA erkannt wird (App-Shell-Marker oder verdaechtig wenig Text), wird ein
   Browser-Rendering versucht — und NUR fuer diese eine URL.
3. **Ehrliche Degradation.** Ist der Browser in dieser Umgebung nicht verfuegbar
   (kein Chromium, Proxy tunnelt ihn nicht), wird das im Snapshot vermerkt und die
   App-Shell behalten — nie faken. Der Befund landet in meta.json.

Jeder Snapshot landet unter reports/raw/<id>/ mit meta.json (URL, Abrufdatum,
Extraktor, HTTP-Status, tri-state Erreichbarkeit, SPA-Verdacht). Diese Snapshots
sind der EINZIGE Belegkorpus fuer das Grounding-Gate.
"""
from __future__ import annotations

import json
import re
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from . import preflight, reach
from .config import ROOT, ProcessSource, SourcesConfig
from .verify import looks_like_spa

RAW = ROOT / "reports" / "raw"


def _slug(url: str) -> str:
    parts = urlsplit(url)
    tail = (parts.path.rstrip("/").rsplit("/", 1)[-1] or parts.netloc).removesuffix(".html")
    return re.sub(r"[^a-z0-9]+", "-", tail.lower()).strip("-") or "seite"


# Backoff bei transienten Fehlern (Netzfehler, 5xx): 3 Versuche mit 2s/4s
# Pause — das ist die in reports/scraping-compliance.md zugesagte Hoeflichkeit.
# Definitive Antworten (2xx/4xx) werden NICHT wiederholt.
_RETRY_ATTEMPTS = 3
_RETRY_BASE_DELAY = 2.0


def _ssr_fetch(
    client: httpx.Client, url: str, *, sleep=time.sleep
) -> tuple[str, int, str, str]:
    """Ein SSR-Abruf: (markdown, http_status, raw_html, tri_state).

    http_status 0 + state netzfehler, wenn der Request gar nicht durchkommt.
    Transiente Fehler (Verbindung/Timeout, 5xx) werden mit exponentiellem
    Backoff wiederholt; nach dem letzten Versuch wird der Befund ehrlich
    zurueckgegeben (kein Faken).
    """
    import trafilatura  # noqa: PLC0415

    last: tuple[str, int, str, str] = ("", 0, "", reach.NETERROR)
    for attempt in range(_RETRY_ATTEMPTS):
        if attempt:
            sleep(_RETRY_BASE_DELAY * 2 ** (attempt - 1))
        try:
            r = client.get(url)
        except httpx.HTTPError:
            last = ("", 0, "", reach.NETERROR)
            continue
        state = reach.classify_status(r.status_code)
        if 500 <= r.status_code < 600:
            last = ("", r.status_code, "", state)
            continue
        md = ""
        raw = ""
        if state == reach.OK:
            raw = r.text
            md = trafilatura.extract(
                raw, url=url, output_format="markdown", include_links=True, include_tables=True
            ) or ""
        return md, r.status_code, raw, state
    return last


def _browser_fetch(url: str, ua: str) -> tuple[str, int] | None:
    """Headless-Rendering einer SINGLE URL (SPA-Fallback). None, wenn der Browser
    in dieser Umgebung nicht verfuegbar/funktionsfaehig ist (ehrliche Degradation)."""
    import asyncio  # noqa: PLC0415

    async def _run() -> tuple[str, int]:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig  # noqa: PLC0415

        browser = BrowserConfig(headless=True, user_agent=ua)
        async with AsyncWebCrawler(config=browser) as crawler:
            result = await crawler.arun(url, config=CrawlerRunConfig())
            return str(result.markdown or ""), int(getattr(result, "status_code", 0) or 0)

    try:
        return asyncio.run(_run())
    except Exception:
        return None


def crawl_process(proc: ProcessSource, cfg: SourcesConfig) -> Path:
    """Crawlt alle official_urls einer Leistung. Gibt das Snapshot-Verzeichnis zurueck."""
    preflight.require_allowed(proc)  # hartes Gate: kein Crawl ohne Preflight-Freigabe

    ua = cfg.crawler.user_agent
    delay = cfg.crawler.delay_seconds

    outdir = RAW / proc.id
    outdir.mkdir(parents=True, exist_ok=True)
    meta = []
    with httpx.Client(headers={"User-Agent": ua}, timeout=30, follow_redirects=True) as client:
        for i, url in enumerate(proc.official_urls, start=1):
            md, status, raw, state = _ssr_fetch(client, url)
            extractor = "httpx+trafilatura"
            spa = state == reach.OK and looks_like_spa(raw, md)
            if spa:
                # Echte SPA: SSR liefert nur die App-Shell -> Browser-Fallback.
                browser = _browser_fetch(url, ua)
                if browser and browser[0].strip():
                    md, status = browser
                    extractor = "crawl4ai (SPA-Fallback)"
                    spa = False
                else:
                    extractor = "httpx+trafilatura (SPA — Browser n/v, App-Shell)"

            fname = f"{i:02d}-{_slug(url)}.md"
            (outdir / fname).write_text(md, encoding="utf-8")
            meta.append(
                {
                    "url": url,
                    "file": fname,
                    "retrieved_at": date.today().isoformat(),
                    "http_status": status,
                    "state": state,
                    "spa_suspected": spa,
                    "extractor": extractor,
                    "chars": len(md),
                }
            )
            ok = state == reach.OK and md.strip() and not spa
            note = "" if ok else f"  !! {state}" + (" / SPA-App-Shell" if spa else "")
            print(f"  [{proc.id}] {url} -> {fname} ({status}/{state}, {len(md)} Zeichen){note}")
            time.sleep(delay)
    (outdir / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return outdir


def load_corpus(proc_id: str) -> tuple[str, list[dict], dict[str, str]]:
    """Laedt alle Snapshots einer Leistung: (Gesamt-Korpus, Metadaten, Text je URL).

    Der Gesamt-Korpus belegt Schritte/Dokumente (tragen keine URL); die
    per-URL-Texte speisen das per-URL-Grounding der References (das Zitat muss
    auf der Seite der angegebenen source_url stehen, siehe grounding.apply_gate).
    """
    outdir = RAW / proc_id
    meta_path = outdir / "meta.json"
    if not meta_path.exists():
        raise SystemExit(f"[{proc_id}] Keine Snapshots — zuerst `tessera crawl` ausfuehren.")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    parts = []
    url_texts: dict[str, str] = {}
    for m in meta:
        text = (outdir / m["file"]).read_text(encoding="utf-8")
        parts.append(f"\n\n<<<QUELLE {m['url']} (abgerufen {m['retrieved_at']})>>>\n\n{text}")
        url = m["url"]
        url_texts[url] = f"{url_texts[url]}\n\n{text}" if url in url_texts else text
    return "".join(parts), meta, url_texts
