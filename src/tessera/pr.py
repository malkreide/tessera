"""Human-in-the-Loop-Ausgabe: ein Draft-PR pro Leistung gegen TARGET_REPO.

Ohne GITHUB_TOKEN im ENV wird KEIN API-Call versucht; stattdessen landet das
komplette PR-Bundle (JSON + PR-Body) in out/outbox/<id>/ — der Maintainer kann
es von dort einreichen. Die Pipeline merged NIE und pusht NIE nach main.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

import httpx

from .config import ROOT, ProcessSource
from .merge import MergeConflict, MergeReport, merge_process
from .risk import (
    HIGH_RISK_DISCLAIMER_KEY,
    HIGH_RISK_RATIONALE,
    is_high_risk,
    is_high_risk_disclaimer,
)

OUTBOX = ROOT / "out" / "outbox"
DEFAULT_TARGET = "malkreide/maschinerie-zuerich"
TARGET_PATH = "stadt-zuerich-next/data/prozesse/zh"


def _bullets(items: list[str], limit: int = 12) -> list[str]:
    """Aufzaehlung fuer den PR-Body, lange Listen gekuerzt."""
    shown = [f"  - `{i}`" for i in items[:limit]]
    if len(items) > limit:
        shown.append(f"  - … und {len(items) - limit} weitere")
    return shown


def build_merge_warning(report: MergeReport, path: str) -> str:
    """Reviewer-Warnung: dieser PR ueberschreibt eine bestehende, handgepflegte
    Datei. Listet auf, welche Felder ERHALTEN (vor Verarmung geschuetzt) und
    welche ERGAENZT wurden."""
    lines = [
        "## ⚠️ Reviewer-Warnung: bestehende handgepflegte Datei",
        "",
        f"Dieser PR aendert die bereits existierende Datei `{path}` im Ziel-Repo.",
        "tessera liefert struktur-only (leere en/fr/it); deshalb wurde **nicht",
        "blind ueberschrieben**, sondern feldweise gemerged: bestehende, nicht-",
        "leere i18n-Werte (de/en/fr/it/ls) und description-Bloecke bleiben",
        "erhalten, die Extraktion fuellt nur Luecken und ergaenzt neue Struktur.",
        "",
        f"- Erhaltene Felder (gegen Leerung geschuetzt): **{len(report.preserved)}**",
    ]
    if report.preserved:
        lines += _bullets(report.preserved)
    lines.append(f"- Ergaenzte Felder / neue Schritte/References: **{len(report.added)}**")
    if report.added:
        lines += _bullets(report.added)
    lines += [
        "",
        "> Bitte den Diff gegen den Ziel-Branch genau pruefen: es darf **kein**",
        "> belegter i18n-/description-Text verloren gehen (CI-Guard "
        "`npm run check:regression`).",
        "",
    ]
    return "\n".join(lines)


def build_high_risk_warning(process: dict) -> str:
    """Prominente Reviewer-Warnung fuer reputationskritische Rechtsfaelle
    (baugesuch, sozialhilfe, veranstaltung): erhoehter Kardinalregel-Review und
    sichtbarer Hochrisiko-Disclaimer."""
    proc_id = process.get("id", "")
    rationale = HIGH_RISK_RATIONALE.get(proc_id, "Reputationskritischer Rechtsfall.")
    lines = [
        "## 🔴 HOCHRISIKO-RECHTSFALL — erhoehter Review erforderlich",
        "",
        f"`{proc_id}` zaehlt zu den reputationskritischen Rechtsfaellen: {rationale}",
        "Eine falsche Frist/Gebuehr, auf die sich jemand verlaesst, ist realer "
        "Schaden — hier gilt der Kardinalregel-/Grounding-Review **verschaerft**:",
        "",
        "- [ ] **Jede** bindende Reference ist `verifiziert` **und** woertlich belegt "
        "(`source_quote`); keine `unverifiziert`en/ungrounded Fristen/Gebuehren",
        "- [ ] Kein gerenderter Text (Label/Description/Bedingung) traegt eine "
        "bindende Zahl — Wert nur via Reference-Link",
        "- [ ] Jedes Zitat woertlich gegen die verlinkte Originalseite geprueft",
        "- [ ] Sichtbarer Hochrisiko-Disclaimer gesetzt "
        f"(`disclaimer_key`, empfohlen `{HIGH_RISK_DISCLAIMER_KEY}`)",
    ]
    if not is_high_risk_disclaimer(process.get("disclaimer_key")):
        lines.append(
            f"  - ⚠️ aktueller `disclaimer_key`: `{process.get('disclaimer_key')}` "
            "— erscheint **nicht** als Hochrisiko-Hinweis; bitte pruefen"
        )
    lines += [
        "",
        "> Governance: dieser Prozess existiert als **handmodellierter v0-Inhalt** "
        "in der Maschinerie; tessera extrahiert ihn in v1 **nicht** automatisch.",
        "",
    ]
    return "\n".join(lines)


def build_pr_body(
    proc: ProcessSource,
    process: dict,
    flags: list[str],
    crawl_meta: list[dict],
    merge_note: str | None = None,
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
    ]
    if is_high_risk(process.get("id")):
        lines += [build_high_risk_warning(process), ""]
    if merge_note:
        lines += [merge_note, ""]
    lines += [
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


def open_draft_pr(
    proc: ProcessSource,
    process: dict,
    flags: list[str],
    crawl_meta: list[dict],
) -> str | None:
    """Erzeugt Branch + Datei + Draft-PR im Ziel-Repo. None ohne GITHUB_TOKEN.

    Existiert die Zieldatei bereits (z.B. handgepflegt mit vollstaendigen
    Uebersetzungen), wird NICHT blind ueberschrieben, sondern feldweise gemerged
    (`merge.merge_process`): bestehende, belegte i18n-/description-Texte bleiben
    erhalten, die Extraktion fuellt nur Luecken. So besteht der PR den CI-Guard
    `npm run check:regression` im Ziel-Repo ohne `ALLOW_PROZESS_SHRINK`.
    """
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        body = build_pr_body(proc, process, flags, crawl_meta)
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

    import base64  # noqa: PLC0415

    with httpx.Client(headers=headers, timeout=30) as client:
        repo = client.get(api).raise_for_status().json()
        default_branch = repo["default_branch"]

        # Bestehende Zieldatei laden (wird ohnehin fuer den sha gebraucht) und
        # feldweise mergen, statt handgepflegte Daten zu verarmen.
        existing = client.get(f"{api}/contents/{path}", params={"ref": default_branch})
        existing_sha: str | None = None
        merge_note: str | None = None
        final_process = process
        if existing.status_code == 200:
            existing_sha = existing.json()["sha"]
            try:
                existing_doc = json.loads(
                    base64.b64decode(existing.json()["content"]).decode("utf-8")
                )
                final_process, report = merge_process(existing_doc, process)
            except (MergeConflict, json.JSONDecodeError, ValueError) as exc:
                # Lieber UEBERSPRINGEN als die handgepflegte Datei verarmen.
                print(
                    f"  [{proc.id}] Bestehende Datei {path} nicht sauber "
                    f"mergebar ({exc}) — UEBERSPRUNGEN, kein PR.",
                    file=sys.stderr,
                )
                return None
            merge_note = build_merge_warning(report, path)
            print(
                f"  [{proc.id}] Bestehende Datei gemerged: "
                f"{len(report.preserved)} Felder erhalten, "
                f"{len(report.added)} ergaenzt."
            )

        body = build_pr_body(proc, final_process, flags, crawl_meta, merge_note=merge_note)
        write_bundle(proc, final_process, body)  # lokales Artefakt = eingereichter Stand
        content = json.dumps(final_process, indent=2, ensure_ascii=False) + "\n"

        base_sha = (
            client.get(f"{api}/git/ref/heads/{default_branch}").raise_for_status().json()
        )["object"]["sha"]
        client.post(
            f"{api}/git/refs", json={"ref": f"refs/heads/{branch}", "sha": base_sha}
        ).raise_for_status()

        msg = f"feat(prozesse): {proc.id} — struktur-only Extraktion (tessera v1)"
        if existing_sha:
            msg = f"feat(prozesse): {proc.id} — Struktur ergaenzen (Handdaten erhalten, tessera v1)"
        put: dict = {
            "message": msg,
            "content": base64.b64encode(content.encode()).decode(),
            "branch": branch,
        }
        if existing_sha:
            put["sha"] = existing_sha
        client.put(f"{api}/contents/{path}", json=put).raise_for_status()

        pr = client.post(
            f"{api}/pulls",
            json={
                "title": f"tessera v1: {final_process['title']['de']} ({proc.id})",
                "head": branch,
                "base": default_branch,
                "body": body,
                "draft": True,
            },
        ).raise_for_status().json()
    print(f"  [{proc.id}] Draft-PR erstellt: {pr['html_url']}")
    return pr["html_url"]
