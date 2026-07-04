"""Human-in-the-Loop-Ausgabe: ein Draft-PR pro Leistung gegen TARGET_REPO.

Ohne GITHUB_TOKEN im ENV wird KEIN API-Call versucht; stattdessen landet das
komplette PR-Bundle (JSON + PR-Body) in out/outbox/<id>/ — der Maintainer kann
es von dort einreichen. Die Pipeline merged NIE und pusht NIE nach main.

Der PR-Body ist Reviewer-UI und Sicherheitsflaeche zugleich:

* **Review-Ergonomie:** Die teuerste Reviewer-Pruefung (Zitat woertlich auf der
  verlinkten Seite?) bekommt eine eigene Reference-Tabelle (Label | Deep-Link |
  Zitat | Status); alle Leichte-Sprache-Texte (`ls`) stehen gesammelt zur
  inhaltlichen Pruefung — sie sind der einzige LLM-Freitext ohne mechanisches
  Gate (nur Zahlen-Lint).
* **Markdown-Neutralisierung:** LLM-/Quelltext (Labels, Zitate, Flags) wird nie
  roh interpoliert — `_md`/`_md_code` escapen Markdown-Steuerzeichen und
  entschaerfen @-Mentions, damit extrahierter Text weder Checklisten faelschen
  noch Personen anpingen noch Review-Bots Anweisungen geben kann.
* **Body-Limit:** GitHub kappt PR-Bodies bei 65 536 Zeichen; ueber
  MAX_BODY_CHARS wird der JSON-Block durch einen Hinweis ersetzt (die Datei
  liegt ohnehin im Diff).

Modul-Importe sind reine stdlib (httpx lazy in open_draft_pr, config nur
TYPE_CHECKING), damit `build_pr_body` in der dependency-freien CI testbar ist.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # nur Typhinweise — kein Laufzeit-Import von config (pydantic/yaml)
    from .config import ProcessSource

from .merge import MergeConflict, MergeReport, merge_process
from .risk import (
    HIGH_RISK_DISCLAIMER_KEY,
    HIGH_RISK_RATIONALE,
    is_high_risk,
    is_high_risk_disclaimer,
)

# Repo-Wurzel ohne config-Import (src/tessera/pr.py -> parents[2]), damit das
# Modul stdlib-importierbar bleibt (wie verify.py/diff.py/preflight.py).
ROOT = Path(__file__).resolve().parents[2]
OUTBOX = ROOT / "out" / "outbox"
DEFAULT_TARGET = "malkreide/maschinerie-zuerich"
TARGET_PATH = "stadt-zuerich-next/data/prozesse/zh"

# GitHub kappt PR-Bodies bei 65 536 Zeichen; Puffer fuer Encoding/Anhaenge.
MAX_BODY_CHARS = 60_000

_WS_RUN = re.compile(r"\s+")
# Markdown-Steuerzeichen, die interpolierter LLM-/Quelltext nicht ausueben darf
# (Links, Checklisten, Ueberschriften, Tabellen, Code, HTML).
_MD_ESCAPE = re.compile(r"([\\`*_\[\]<>|#~])")
_BACKTICK_RUN = re.compile(r"`+")


def _md(text: object) -> str:
    """Neutralisiert LLM-/Quelltext fuer die Markdown-Interpolation:
    Whitespace/Zeilenumbrueche kollabiert (kein Ausbruch aus Listen/Tabellen),
    Steuerzeichen escaped, @-Mentions entschaerft (Word-Joiner nach dem @ —
    unsichtbar, aber GitHub parst keine Mention mehr)."""
    s = _WS_RUN.sub(" ", str(text or "")).strip()
    s = _MD_ESCAPE.sub(r"\\\1", s)
    return s.replace("@", "@\u2060")  # U+2060 WORD JOINER: unsichtbar, keine Mention


def _md_code(text: object) -> str:
    """LLM-/Quelltext als Code-Span: rendert verbatim, keine Mentions, kein
    Markdown. Delimiter laenger als der laengste Backtick-Run im Text."""
    s = _WS_RUN.sub(" ", str(text or "")).strip()
    if not s:
        return "—"
    run = max((len(m.group(0)) for m in _BACKTICK_RUN.finditer(s)), default=0)
    if run:
        fence = "`" * (run + 1)
        return f"{fence} {s} {fence}"
    return f"`{s}`"


def _bullets(items: list[str], limit: int = 12) -> list[str]:
    """Aufzaehlung fuer den PR-Body, lange Listen gekuerzt; Eintraege als
    Code-Span (neutralisiert Markdown/Mentions in LLM-Anteilen)."""
    shown = [f"  - {_md_code(i)}" for i in items[:limit]]
    if len(items) > limit:
        shown.append(f"  - … und {len(items) - limit} weitere")
    return shown


def _collect_ls(process: dict) -> list[tuple[str, str]]:
    """Sammelt alle Leichte-Sprache-Texte (`ls`) mit Fundstelle — der einzige
    LLM-Freitext ohne mechanisches Gate; der Reviewer prueft ihn gesammelt."""
    out: list[tuple[str, str]] = []

    def add(where: str, obj: object) -> None:
        if isinstance(obj, dict):
            ls = obj.get("ls")
            if isinstance(ls, str) and ls.strip():
                out.append((where, ls.strip()))

    add("title", process.get("title"))
    add("description", process.get("description"))
    for i, p in enumerate(process.get("preconditions") or []):
        add(f"preconditions[{i}]", p)
    for s in process.get("steps") or []:
        if not isinstance(s, dict):
            continue
        sid = s.get("step_id", "?")
        add(f"steps[{sid}].label", s.get("label"))
        add(f"steps[{sid}].description", s.get("description"))
        for d in s.get("depends_on") or []:
            if isinstance(d, dict):
                add(f"steps[{sid}].depends_on[{d.get('step_id')}].condition", d.get("condition"))
        for j, doc in enumerate(s.get("documents") or []):
            if isinstance(doc, dict):
                add(f"steps[{sid}].documents[{j}].label", doc.get("label"))
    for r in process.get("references") or []:
        if isinstance(r, dict):
            add(f"references[{r.get('reference_id')}].label", r.get("label"))
    return out


def _reference_table(refs: list[dict]) -> list[str]:
    """Die Kernpruefung des Reviewers als Tabelle: Zitat und Deep-Link pro
    Reference nebeneinander — Klick-und-Vergleich statt Wuehlen im JSON."""
    lines = [
        "## References — Kernpruefung: steht das Zitat woertlich auf der verlinkten Seite?",
        "",
        "| # | Label | Deep-Link | Zitat (woertlich) | Status |",
        "|---|---|---|---|---|",
    ]
    for r in refs:
        if not isinstance(r, dict):
            continue
        label = r.get("label")
        label_de = label.get("de", "?") if isinstance(label, dict) else "?"
        url = _WS_RUN.sub("", str(r.get("source_url") or "")).replace("|", "%7C")
        status = r.get("status", "verifiziert")
        icon = "✅" if status == "verifiziert" else "⚠️"
        quote = (r.get("source_quote") or "").strip()
        lines.append(
            f"| {r.get('reference_id')} | {_md(label_de)} | {url} "
            f"| {_md_code(quote)} | {icon} {status} |"
        )
    lines.append("")
    return lines


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
    if report.refreshed:
        lines.append(
            f"- Provenienz aktualisiert (frisches Crawl-Datum gewinnt): "
            f"**{len(report.refreshed)}**"
        )
        lines += _bullets(report.refreshed)
    if report.remapped_actors:
        lines.append(
            f"- Actor-Rollen auf bestehende `actors[].id` abgebildet: "
            f"**{len(report.remapped_actors)}**"
        )
        lines += _bullets(report.remapped_actors)
    if report.suspect_pairs:
        lines += [
            "",
            f"### ❌ Offen: {len(report.suspect_pairs)} verdaechtige(s) ID-Paar(e) — NICHT gemerged",
            "",
            "Extraktion und bestehende Datei tragen unter derselben step_id/",
            "reference_id semantisch fremde Labels — numerische IDs sind KEINE",
            "stabilen fachlichen Schluessel. Der bestehende Eintrag blieb",
            "unangetastet, die Extraktions-Fassung wurde verworfen. Bitte manuell",
            "abgleichen (Schritt umnummerieren oder als neuen Schritt ergaenzen):",
            "",
        ]
        lines += _bullets(report.suspect_pairs)
    if report.unmapped_actors:
        lines += [
            "",
            f"### ❌ Offen: {len(report.unmapped_actors)} Actor(en) ohne `actors[]`-Eintrag",
            "",
            "Diese Schritt-Actors liessen sich KEINER bestehenden `actors[].id`",
            "zuordnen und wurden **nicht geraten**. Bitte den passenden",
            "`actors[]`-Eintrag (inkl. `type`) ergaenzen und den Schritt darauf",
            "verweisen lassen — sonst scheitert `npm run validate:prozesse`:",
            "",
        ]
        lines += _bullets(report.unmapped_actors)
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
            f"  - ⚠️ aktueller `disclaimer_key`: {_md_code(process.get('disclaimer_key'))} "
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
        f"# tessera v1: Prozess «{_md(process['title']['de'])}» (`{proc.id}`)",
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
    lines.append("")
    if refs:
        lines += _reference_table(refs)
    ls_texts = _collect_ls(process)
    if ls_texts:
        lines += [
            "## Leichte Sprache (`ls`) — inhaltlich pruefen",
            "",
            "Die `ls`-Texte sind der einzige LLM-Freitext ohne mechanisches Gate",
            "(nur der Zahlen-Lint greift). Bitte gesammelt auf Korrektheit und",
            "wirklich einfache Sprache pruefen:",
            "",
        ]
        lines += [f"- `{where}`: {_md_code(text)}" for where, text in ls_texts]
        lines.append("")
    lines += ["## Grounding-Gate / offene Punkte", ""]
    if flags:
        # Flags tragen LLM-Anteile (Labels/Zitate) -> neutralisiert interpolieren.
        lines += [f"- ⚠️ {_md(f)}" for f in flags]
    else:
        lines.append("- Keine: alle Schritte und References sind woertlich belegt.")
    lines += [
        "",
        "## Reviewer-Checkliste",
        "",
        "- [ ] Schritte und Reihenfolge entsprechen der offiziellen Darstellung",
        "- [ ] Kein Schritt-Label enthaelt eine bindende Zahl (Frist/Gebuehr)",
        "- [ ] Jede verifizierte Reference: Zitat stimmt woertlich mit der verlinkten Seite ueberein "
        "(Tabelle oben: Klick auf den Deep-Link, Zitat vergleichen)",
        "- [ ] Unverifizierte References: pruefen, belegen oder entfernen",
        "- [ ] Leichte Sprache (`ls`) ist inhaltlich korrekt und wirklich einfach",
        "- [ ] `lebenslage_ref` verlinkt korrekt auf die bestehende Lebenslage",
        "",
        "Validierung: `scripts/validate_contract.py` (tessera) bestanden — bitte",
        "zusaetzlich `npm run validate:prozesse` im Ziel-Repo laufen lassen.",
        "",
    ]
    footer = [
        "---",
        "_Erzeugt von tessera v1 (Human-in-the-Loop: dieser PR ist ein Draft und",
        "wird ausschliesslich von Menschen gemergt)._",
    ]
    # JSON-Block: 4-Backtick-Fence, damit ein ``` in einem Zitat den Block nicht
    # sprengen kann. Ueber MAX_BODY_CHARS (GitHub-Limit 65 536) wird er durch
    # einen Hinweis ersetzt — die Datei liegt ohnehin im Diff des PRs.
    json_block = [
        "## JSON",
        "",
        "````json",
        json.dumps(process, indent=2, ensure_ascii=False),
        "````",
        "",
    ]
    body = "\n".join(lines + json_block + footer)
    if len(body) > MAX_BODY_CHARS:
        note = [
            "## JSON",
            "",
            "_(JSON hier weggelassen — PR-Body-Limit. Die vollstaendige Datei",
            f"liegt im Diff dieses PRs und im Bundle `out/outbox/{proc.id}/`.)_",
            "",
        ]
        body = "\n".join(lines + note + footer)
    return body


def validate_merged(path: Path) -> tuple[bool, str]:
    """Faehrt den Vertrags-Validator auf der TATSAECHLICH eingereichten (ggf.
    gemergten) Datei. Der lokale `tessera validate` prueft nur die struktur-only
    Extraktion (ohne actors[]); erst nach dem Merge gibt es actors[], und nur dann
    greift die Actor-Paritaet. Gate-Paritaet zur Ziel-CI: faellt das durch, wird
    KEIN PR geoeffnet."""
    import subprocess  # noqa: PLC0415

    # UTF-8 erzwingen: sonst dekodiert/encodiert der Subprozess auf Windows die
    # Pipe als cp1252 und crasht am ⚠-Hochrisiko-Hinweis (UnicodeEncodeError) —
    # was faelschlich als "Validierung fehlgeschlagen" gewertet wuerde.
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_contract.py"), str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    return result.returncode == 0, (result.stdout + result.stderr)


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

    import httpx  # noqa: PLC0415 — lazy, Modul bleibt stdlib-importierbar

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
                f"{len(report.added)} ergaenzt"
                + (f", {len(report.remapped_actors)} Actor(en) abgebildet" if report.remapped_actors else "")
                + (f", {len(report.unmapped_actors)} Actor(en) OFFEN" if report.unmapped_actors else "")
                + "."
            )

        body = build_pr_body(proc, final_process, flags, crawl_meta, merge_note=merge_note)
        bundle_dir = write_bundle(proc, final_process, body)  # lokales Artefakt = eingereichter Stand

        # Gate-Paritaet: den gemergten Stand gegen den Vertrags-Validator pruefen,
        # BEVOR ein PR aufgemacht wird. Erst hier gibt es actors[] und damit die
        # Actor-Paritaet, die die Ziel-CI ebenfalls erzwingt.
        merged_ok, validator_out = validate_merged(bundle_dir / f"{proc.id}.json")
        if not merged_ok:
            print(
                f"  [{proc.id}] Gemergter Stand besteht den Vertrags-Validator NICHT "
                f"— KEIN PR. Bundle zur Korrektur: {bundle_dir}\n{validator_out.strip()}",
                file=sys.stderr,
            )
            return None

        content = json.dumps(final_process, indent=2, ensure_ascii=False) + "\n"

        base_sha = (
            client.get(f"{api}/git/ref/heads/{default_branch}").raise_for_status().json()
        )["object"]["sha"]
        # Branch anlegen — oder, wenn er aus einem frueheren (Teil-)Lauf schon
        # existiert (der Name ist tagesdatiert), idempotent auf base zuruecksetzen,
        # statt mit 422 abzubrechen. Zurueckgesetzt wird aber NUR ein Branch,
        # dessen Head ein tessera-Commit ist: hat ein Mensch dort nachgearbeitet
        # (fremde Commit-Message), wird abgebrochen statt still ueberschrieben.
        created = client.post(
            f"{api}/git/refs", json={"ref": f"refs/heads/{branch}", "sha": base_sha}
        )
        if created.status_code == 422:
            head_msg = str(
                client.get(f"{api}/commits/{branch}").raise_for_status().json()
                .get("commit", {}).get("message", "")
            )
            if not head_msg.startswith("feat(prozesse):"):
                first_line = head_msg.splitlines()[0] if head_msg else "?"
                print(
                    f"  [{proc.id}] Branch {branch} existiert mit fremden Commits "
                    f"(Head: {first_line!r}) — NICHT zurueckgesetzt, KEIN PR. "
                    "Bitte manuell klaeren (Branch loeschen oder umbenennen).",
                    file=sys.stderr,
                )
                return None
            client.patch(
                f"{api}/git/refs/heads/{branch}", json={"sha": base_sha, "force": True}
            ).raise_for_status()
        else:
            created.raise_for_status()

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

        created_pr = client.post(
            f"{api}/pulls",
            json={
                # Titel ist Plaintext (kein Markdown/Mentions) — nur Whitespace
                # kollabieren, damit ein mehrzeiliges LLM-title nicht bricht.
                "title": f"tessera v1: {_WS_RUN.sub(' ', final_process['title']['de']).strip()} ({proc.id})",
                "head": branch,
                "base": default_branch,
                "body": body,
                "draft": True,
            },
        )
        if created_pr.status_code == 422:
            # Fuer diesen Branch existiert bereits ein PR (Re-Run) — den Branch
            # haben wir oben aktualisiert, also den bestehenden PR melden statt
            # abzubrechen.
            owner = target.split("/", 1)[0]
            existing = client.get(
                f"{api}/pulls", params={"head": f"{owner}:{branch}", "state": "open"}
            ).raise_for_status().json()
            if existing:
                url = existing[0]["html_url"]
                print(f"  [{proc.id}] Bestehender Draft-PR aktualisiert: {url}")
                return url
            created_pr.raise_for_status()  # 422 aus anderem Grund -> echter Fehler
        pr = created_pr.raise_for_status().json()
    print(f"  [{proc.id}] Draft-PR erstellt: {pr['html_url']}")
    return pr["html_url"]
