"""Human-in-the-Loop-Ausgabe: ein Draft-PR pro Leistung gegen TARGET_REPO.

Ohne GITHUB_TOKEN im ENV wird KEIN API-Call versucht; stattdessen landet das
komplette PR-Bundle (JSON + PR-Body) in out/outbox/<id>/ — der Maintainer kann
es von dort einreichen. Die Pipeline merged NIE und pusht NIE nach main.
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import httpx

from .config import ROOT, ProcessSource

OUTBOX = ROOT / "out" / "outbox"
DEFAULT_TARGET = "malkreide/maschinerie-zuerich"
TARGET_PATH = "stadt-zuerich-next/data/prozesse/zh"


def build_pr_body(
    proc: ProcessSource,
    process: dict,
    flags: list[str],
    crawl_meta: list[dict],
) -> str:
    refs = process.get("references", [])
    verified = [r for r in refs if r.get("status", "verifiziert") == "verifiziert"]
    open_refs = [r for r in refs if r.get("status") == "unverifiziert"]

    lines = [
        f"# tessera v1: Prozess «{process['title']['de']}» (`{proc.id}`)",
        "",
        "Automatisch extrahierte **Prozess-Struktur** (struktur-only) aus den",
        "offiziellen Quellseiten. Rechtlich bindende Werte (Fristen, Gebuehren)",
        "sind ausschliesslich als `references` mit Deep-Link und woertlicher",
        "Belegstelle enthalten — nie als Wert im Schritt-Label (Kardinalregel).",
        "",
        "## Zusammenfassung",
        "",
        f"- Schritte: {len(process['steps'])}, References: {len(refs)} "
        f"({len(verified)} belegt, {len(open_refs)} offen)",
        f"- Quellen (abgerufen {process['retrieved_at']}):",
    ]
    for m in crawl_meta:
        lines.append(f"  - {m['url']} (HTTP {m['http_status']}, Extraktor: {m['extractor']})")
    lines += ["", "## Grounding-Gate / offene Punkte", ""]
    if flags:
        lines += [f"- ⚠️ {f}" for f in flags]
    else:
        lines.append("- Keine: alle Schritte und References sind woertlich belegt.")
    lines += [
        "",
        "## Reviewer-Checkliste",
        "",
        "- [ ] Schritte und Reihenfolge entsprechen der offiziellen Darstellung",
        "- [ ] Kein Schritt-Label enthaelt eine bindende Zahl (Frist/Gebuehr)",
        "- [ ] Jede verifizierte Reference: Zitat stimmt woertlich mit der verlinkten Seite ueberein",
        "- [ ] Unverifizierte References: pruefen, belegen oder entfernen",
        "- [ ] Leichte Sprache (`ls`) ist inhaltlich korrekt und wirklich einfach",
        "- [ ] `lebenslage_ref` verlinkt korrekt auf die bestehende Lebenslage",
        "",
        "Validierung: `scripts/validate_contract.py` (tessera) bestanden — bitte",
        "zusaetzlich `npm run validate:prozesse` im Ziel-Repo laufen lassen.",
        "",
        "## JSON",
        "",
        "```json",
        json.dumps(process, indent=2, ensure_ascii=False),
        "```",
        "",
        "---",
        "_Erzeugt von tessera v1 (Human-in-the-Loop: dieser PR ist ein Draft und",
        "wird ausschliesslich von Menschen gemergt)._",
    ]
    return "\n".join(lines)


def write_bundle(proc: ProcessSource, process: dict, body: str) -> Path:
    outdir = OUTBOX / proc.id
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / f"{proc.id}.json").write_text(
        json.dumps(process, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (outdir / "PR_BODY.md").write_text(body, encoding="utf-8")
    return outdir


def open_draft_pr(proc: ProcessSource, process: dict, body: str) -> str | None:
    """Erzeugt Branch + Datei + Draft-PR im Ziel-Repo. None ohne GITHUB_TOKEN."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print(
            f"  [{proc.id}] Kein GITHUB_TOKEN im ENV — PR-Bundle liegt in "
            f"{write_bundle(proc, process, body)} (manuell einreichen)."
        )
        return None

    target = os.environ.get("TARGET_REPO", DEFAULT_TARGET)
    api = f"https://api.github.com/repos/{target}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "tessera/0.1",
    }
    branch = f"tessera/{proc.id}-{date.today().isoformat()}"
    path = f"{TARGET_PATH}/{proc.id}.json"
    content = json.dumps(process, indent=2, ensure_ascii=False) + "\n"

    import base64  # noqa: PLC0415

    with httpx.Client(headers=headers, timeout=30) as client:
        repo = client.get(api).raise_for_status().json()
        default_branch = repo["default_branch"]
        base_sha = (
            client.get(f"{api}/git/ref/heads/{default_branch}").raise_for_status().json()
        )["object"]["sha"]
        client.post(
            f"{api}/git/refs", json={"ref": f"refs/heads/{branch}", "sha": base_sha}
        ).raise_for_status()

        put: dict = {
            "message": f"feat(prozesse): {proc.id} — struktur-only Extraktion (tessera v1)",
            "content": base64.b64encode(content.encode()).decode(),
            "branch": branch,
        }
        existing = client.get(f"{api}/contents/{path}", params={"ref": default_branch})
        if existing.status_code == 200:
            put["sha"] = existing.json()["sha"]
        client.put(f"{api}/contents/{path}", json=put).raise_for_status()

        pr = client.post(
            f"{api}/pulls",
            json={
                "title": f"tessera v1: {process['title']['de']} ({proc.id})",
                "head": branch,
                "base": default_branch,
                "body": body,
                "draft": True,
            },
        ).raise_for_status().json()
    print(f"  [{proc.id}] Draft-PR erstellt: {pr['html_url']}")
    return pr["html_url"]
