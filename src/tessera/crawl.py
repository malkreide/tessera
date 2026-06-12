"""Crawl: offizielle Quellseiten -> sauberes Markdown (Snapshots).

Primaer Crawl4AI (Headless-Browser); wenn das in der Umgebung nicht laeuft,
faellt der Crawler auf httpx + Trafilatura zurueck und vermerkt das im
Snapshot-Metadatensatz (der Fallback ist ein dokumentierter Befund, kein
stilles Verhalten).

Jeder Snapshot landet unter reports/raw/<id>/ mit meta.json (URL, Abrufdatum,
Extraktor, HTTP-Status). Diese Snapshots sind der EINZIGE Belegkorpus fuer
das Grounding-Gate.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from . import preflight
from .config import ROOT, ProcessSource, SourcesConfig

RAW = ROOT / "reports" / "raw"


def _slug(url: str) -> str:
    parts = urlsplit(url)
    tail = (parts.path.rstrip("/").rsplit("/", 1)[-1] or parts.netloc).removesuffix(".html")
    return re.sub(r"[^a-z0-9]+", "-", tail.lower()).strip("-") or "seite"


async def _crawl4ai_fetch(urls: list[str], ua: str, delay: float) -> list[tuple[str, str, int]]:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig  # noqa: PLC0415

    out: list[tuple[str, str, int]] = []
    browser = BrowserConfig(headless=True, user_agent=ua)
    async with AsyncWebCrawler(config=browser) as crawler:
        for u in urls:
            result = await crawler.arun(u, config=CrawlerRunConfig())
            md = str(result.markdown or "")
            status = int(getattr(result, "status_code", 0) or 0)
            out.append((u, md, status))
            await asyncio.sleep(delay)
    return out


def _trafilatura_fetch(urls: list[str], ua: str, delay: float) -> list[tuple[str, str, int]]:
    import trafilatura  # noqa: PLC0415

    out: list[tuple[str, str, int]] = []
    with httpx.Client(headers={"User-Agent": ua}, timeout=30, follow_redirects=True) as client:
        for u in urls:
            r = client.get(u)
            md = ""
            if r.status_code == 200:
                md = trafilatura.extract(
                    r.text,
                    url=u,
                    output_format="markdown",
                    include_links=True,
                    include_tables=True,
                ) or ""
            out.append((u, md, r.status_code))
            time.sleep(delay)
    return out


def crawl_process(proc: ProcessSource, cfg: SourcesConfig) -> Path:
    """Crawlt alle official_urls einer Leistung. Gibt das Snapshot-Verzeichnis zurueck."""
    preflight.require_allowed(proc)  # hartes Gate: kein Crawl ohne Preflight-Freigabe

    ua = cfg.crawler.user_agent
    delay = cfg.crawler.delay_seconds
    extractor = "crawl4ai"
    try:
        results = asyncio.run(_crawl4ai_fetch(proc.official_urls, ua, delay))
    except Exception as exc:
        extractor = f"trafilatura-fallback (crawl4ai: {exc.__class__.__name__})"
        results = _trafilatura_fetch(proc.official_urls, ua, delay)

    outdir = RAW / proc.id
    outdir.mkdir(parents=True, exist_ok=True)
    meta = []
    for i, (url, md, status) in enumerate(results, start=1):
        fname = f"{i:02d}-{_slug(url)}.md"
        (outdir / fname).write_text(md, encoding="utf-8")
        meta.append(
            {
                "url": url,
                "file": fname,
                "retrieved_at": date.today().isoformat(),
                "http_status": status,
                "extractor": extractor,
                "chars": len(md),
            }
        )
        ok = status == 200 and md.strip()
        print(f"  [{proc.id}] {url} -> {fname} ({status}, {len(md)} Zeichen){'' if ok else '  !! leer/Fehler'}")
    (outdir / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return outdir


def load_corpus(proc_id: str) -> tuple[str, list[dict]]:
    """Laedt alle Snapshots einer Leistung als einen Belegkorpus + Metadaten."""
    outdir = RAW / proc_id
    meta_path = outdir / "meta.json"
    if not meta_path.exists():
        raise SystemExit(f"[{proc_id}] Keine Snapshots — zuerst `tessera crawl` ausfuehren.")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    parts = []
    for m in meta:
        text = (outdir / m["file"]).read_text(encoding="utf-8")
        parts.append(f"\n\n<<<QUELLE {m['url']} (abgerufen {m['retrieved_at']})>>>\n\n{text}")
    return "".join(parts), meta
