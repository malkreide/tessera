"""Human-in-the-Loop-Ausgabe: ein Draft-PR pro Leistung gegen TARGET_REPO.

Ohne GITHUB_TOKEN im ENV wird nichts geschrieben: tessera liest nur die
(oeffentliche) Zieldatei, gleicht ab und legt das komplette PR-Bundle (JSON +
PR-Body) in out/outbox/<id>/ — der Maintainer kann es von dort einreichen. Gibt
es die Leistung im Ziel-Repo schon, ist sie kanonisch: Abgleich statt Merge
(`merge.sync_existing`). Die Pipeline merged NIE und pusht NIE nach main.

Der PR-Body ist Reviewer-UI und Sicherheitsflaeche zugleich:

* **Review-Ergonomie:** Die teuerste Reviewer-Pruefung (Zitat woertlich auf der
  verlinkten Seite?) bekommt eine eigene Reference-Tabelle (Label | Deep-Link |
  Zitat | Status).
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

from .grounding import BRIDGE_FLAG_PREFIX
from .merge import AbgleichReport, MergeConflict, apply_herkunft, sync_existing
from .plausibility import ACTOR_FLAG_PREFIX, ORDER_FLAG_PREFIX
from .risk import (
    HIGH_RISK_DISCLAIMER_KEY,
    HIGH_RISK_RATIONALE,
    is_high_risk,
    is_high_risk_disclaimer,
)
from .screening import FLAG_PREFIX as INJECTION_FLAG_PREFIX

# Repo-Wurzel ohne config-Import (src/tessera/pr.py -> parents[2]), damit das
# Modul stdlib-importierbar bleibt (wie verify.py/diff.py/preflight.py).
ROOT = Path(__file__).resolve().parents[2]
OUTBOX = ROOT / "out" / "outbox"
DEFAULT_TARGET = "malkreide/maschinerie-zuerich"
TARGET_PATH = "stadt-zuerich-next/data/prozesse/zh"
# Label im Ziel-Repo (.github/labels.yml): markiert PRs aus tessera, deren
# Nummer in meta.herkunft.tessera_prs gehoert.
SOURCE_LABEL = "quelle:tessera"

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
            f"| {r.get('reference_id')} | {_md(label_de)} | {url} | {_md_code(quote)} | {icon} {status} |"
        )
    lines.append("")
    return lines


def _id_list(items: list[tuple[object, str]]) -> str:
    return ", ".join(f"#{i} «{_md(label)}»" for i, label in items) or "—"


def build_abgleich_report(report: AbgleichReport, path: str) -> str:
    """Abgleich-Bericht fuer eine bestehende, handgepflegte Datei.

    Der PR aendert an der Datei nur `retrieved_at` (Prozess und wiedergefundene
    Belege). Alles, was die Extraktion darueber hinaus findet, steht hier als
    Vorschlag — uebernehmen tut ein Mensch, samt Nummerierung. LLM-Text ist
    neutralisiert (`_md`)."""
    lines = [
        "## 🔎 Abgleich mit der bestehenden Handdatei",
        "",
        f"Fuer diese Leistung gibt es bereits `{path}`. Sie ist kanonisch. tessera hat",
        "die Extraktion **nicht eingespielt**: `step_id`/`reference_id` vergibt das",
        "Modell bei jedem Lauf neu und taugen nicht als Schluessel. Dieser PR",
        "frischt nur `retrieved_at` auf — fuer den Prozess und fuer jede Reference,",
        "deren Zitat die Extraktion auf derselben Seite woertlich wiedergefunden",
        "hat. Schritte, Akteure, Texte, Status und `meta.herkunft` bleiben unveraendert.",
        "",
        f"- Aufgefrischt: **{len(report.refreshed)}**",
    ]
    lines += _bullets(report.refreshed)
    lines += [
        f"- Belege woertlich wiedergefunden: **{len(report.refs_confirmed)}**",
    ]
    if report.refs_confirmed:
        lines.append(f"  - {_id_list(report.refs_confirmed)}")
    if report.refs_confirmed_unverified:
        lines += [
            f"- ⚠️ Davon in der Handdatei `unverifiziert`: **{len(report.refs_confirmed_unverified)}** — "
            "Zitat steht woertlich auf der Seite; Status bitte von Hand pruefen und setzen "
            "(tessera aendert ihn nicht)",
            f"  - {_id_list(report.refs_confirmed_unverified)}",
        ]
    if report.refs_not_found:
        lines += [
            f"- ⚠️ Belege der Handdatei NICHT wiedergefunden: **{len(report.refs_not_found)}** — "
            "die Extraktion hat dieses Zitat nicht geliefert; das heisst nicht, dass es fehlt. "
            "`tessera verify --online` prueft es gezielt",
            f"  - {_id_list(report.refs_not_found)}",
        ]
    if report.refs_without_quote:
        lines += [
            f"- Belege ohne Zitat (nicht abgleichbar): **{len(report.refs_without_quote)}**",
            f"  - {_id_list(report.refs_without_quote)}",
        ]
    if report.pairing_note:
        lines += ["", f"Paarung: {report.pairing_note}"]  # eigener Text, kein LLM-Anteil
    if report.step_pairs:
        lines += [
            "",
            "### Zuordnung Extraktion ↔ Handdatei (bestaetigte Paarung)",
            "",
            "| Extraktion | Handdatei |",
            "|---|---|",
        ]
        for ext, can in report.step_pairs:
            lines.append(f"| {_id_list(ext)} | {_id_list(can)} |")
    if report.step_proposals:
        lines += [
            "",
            f"### Vorschlaege: {len(report.step_proposals)} Schritt(e) der Extraktion ohne Partner",
            "",
            "Nicht eingespielt. Pruefen, ob der Schritt in der Handdatei fehlt; wenn ja,",
            "dort von Hand ergaenzen (eigene Nummer, Kanten, Akteur aus `actors[]`).",
            "Nummern hier sind die der **Extraktion**.",
            "",
            "| # | Schritt | Akteur | nach | Belege |",
            "|---|---|---|---|---|",
        ]
        for st in report.step_proposals:
            after = "; ".join(_md(v) for v in st["vorgaenger"]) or "—"
            refs = "; ".join(_md(v) for v in st["belege"]) or "—"
            lines.append(f"| {st['step_id']} | {_md(st['label'])} | {_md(st['actor'])} | {after} | {refs} |")
    if report.ref_proposals:
        lines += [
            "",
            f"### Vorschlaege: {len(report.ref_proposals)} Belegstelle(n) ohne Gegenstueck in der Handdatei",
            "",
            "Nicht eingespielt. Gegen die Seite pruefen und bei Bedarf als Reference",
            "von Hand ergaenzen:",
            "",
        ]
        lines += _reference_table(report.ref_proposals)[2:]
    lines += [
        "",
        "> Bitte den Diff pruefen: er darf **nur** `retrieved_at`-Werte aendern.",
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
    # Ein tessera-PR entsteht nur fuer eine in sources.yaml freigeschaltete
    # Leistung — die Fassung hier ist also IMMER automatisch extrahiert.
    lines += [
        "",
        "> Governance: dieser Prozess existiert zusaetzlich als **handmodellierter "
        "v0-Inhalt** in der Maschinerie. Die Fassung in diesem PR ist **automatisch "
        "extrahiert** — eine bewusste Hochrisiko-Ausnahme (`sources.yaml`); Merge "
        "ausschliesslich durch einen Menschen.",
        "",
    ]
    return "\n".join(lines)


def build_pr_body(
    proc: ProcessSource,
    process: dict,
    flags: list[str],
    crawl_meta: list[dict],
    abgleich: str | None = None,
) -> str:
    """PR-Body. `process` ist immer die Extraktion. Mit `abgleich` (gerenderter
    `build_abgleich_report`) ist es ein Abgleich-PR gegen eine bestehende
    Handdatei: die Extraktion ist dann nicht eingespielt, sondern Vorschlag."""
    refs = process.get("references", [])
    verified = [r for r in refs if r.get("status", "verifiziert") == "verifiziert"]
    open_refs = [r for r in refs if r.get("status") == "unverifiziert"]

    kind = "Abgleich" if abgleich else "Prozess"
    lines = [
        f"# tessera v1: {kind} «{_md(process['title']['de'])}» (`{proc.id}`)",
        "",
        "Automatisch extrahierte **Prozess-Struktur** (struktur-only) aus den",
        "offiziellen Quellseiten. Rechtlich bindende Werte (Fristen, Gebuehren)",
        "sind ausschliesslich als `references` mit Deep-Link und woertlicher",
        "Belegstelle enthalten — nie als Wert im Schritt-Label (Kardinalregel).",
        "",
    ]
    if is_high_risk(process.get("id")):
        lines += [build_high_risk_warning(process), ""]
    if abgleich:
        lines += [abgleich, ""]
    lines += [
        "## Zusammenfassung" + (" der Extraktion (nicht eingespielt)" if abgleich else ""),
        "",
        f"- Schritte: {len(process['steps'])}, References: {len(refs)} "
        f"({len(verified)} belegt, {len(open_refs)} offen)",
        f"- Quellen (abgerufen {process['retrieved_at']}):",
    ]
    for m in crawl_meta:
        lines.append(f"  - {m['url']} (HTTP {m['http_status']}, Extraktor: {m['extractor']})")
    lines.append("")
    if refs and not abgleich:
        lines += _reference_table(refs)
    bridges = [f for f in flags if str(f).startswith(BRIDGE_FLAG_PREFIX)]
    other_flags = [f for f in flags if not str(f).startswith(BRIDGE_FLAG_PREFIX)]
    if bridges:
        lines += [
            "## ❌ Ueberbrueckte Kanten — Graph pruefen",
            "",
            "Das Grounding-Gate hat Schritte verworfen; deren Nachfolger haben die",
            "Vorgaenger geerbt. Die folgenden Kanten zeigen damit eine Direktabfolge,",
            "die die Quelle **nicht** belegt. Bitte gegen die Originalseite pruefen:",
            "Schritt belegen und ergaenzen oder die Kante korrigieren.",
            "",
        ]
        lines += [f"- {_md(f)}" for f in bridges]
        lines.append("")
    lines += ["## Grounding-Gate / offene Punkte", ""]
    if other_flags:
        # Flags tragen LLM-Anteile (Labels/Zitate) -> neutralisiert interpolieren.
        lines += [f"- ⚠️ {_md(f)}" for f in other_flags]
    else:
        lines.append("- Keine: alle Schritte und References sind woertlich belegt.")
    review_notes = " ".join((getattr(proc, "review_notes", "") or "").split())
    if review_notes:
        # Kuratierte Hinweise fuer Menschen (sources.yaml, review_notes) — gingen
        # bewusst NICHT in den Extraktions-Prompt.
        lines += ["", "## Hinweise fuer Reviewer (kuratiert, nicht im Prompt)", "", _md(review_notes)]
    lines += [
        "",
        "## Reviewer-Checkliste",
        "",
    ]
    if any(str(f).startswith(INJECTION_FLAG_PREFIX) for f in flags):
        lines.append(
            "- [ ] **INJECTION-Verdacht geprueft**: Die geflaggten Quelltext-Stellen "
            "(oben) enthalten keine Anweisungen, die die Extraktion gesteuert haben "
            "koennten; Schritte/References gegen die Originalseite plausibilisiert"
        )
    if bridges:
        lines.append(
            "- [ ] **Ueberbrueckte Kanten geprueft**: jede oben gelistete Kante entspricht "
            "der offiziellen Abfolge oder wurde korrigiert"
        )
    if any(str(f).startswith((ORDER_FLAG_PREFIX, ACTOR_FLAG_PREFIX)) for f in flags):
        lines.append(
            "- [ ] **Reihenfolge-/Akteur-Hinweise geprueft**: geflaggte Kanten und Rollen "
            "(oben) gegen die Originalseite plausibilisiert"
        )
    if abgleich:
        lines += [
            "- [ ] Der Diff aendert **nur** `retrieved_at` (Prozess und wiedergefundene Belege)",
            "- [ ] Vorschlaege (Schritte, Belegstellen) geprueft: fehlendes in der Handdatei "
            "von Hand ergaenzt (eigener PR oder hier) oder bewusst verworfen",
            "- [ ] Nicht wiedergefundene Belege geprueft (`tessera verify --online`)",
            "- [ ] `unverifiziert`-Hinweise geprueft; Status nur von Hand setzen",
            "- [ ] `meta.herkunft` bleibt unveraendert (der Abgleich aendert keine Inhalte); "
            "wer Vorschlaege von Hand uebernimmt, fuehrt sie nach",
            "",
        ]
    else:
        lines += [
            "- [ ] Schritte und Reihenfolge entsprechen der offiziellen Darstellung",
            "- [ ] Kein Schritt-Label enthaelt eine bindende Zahl (Frist/Gebuehr)",
            "- [ ] Jede verifizierte Reference: Zitat stimmt woertlich mit der verlinkten Seite ueberein "
            "(Tabelle oben: Klick auf den Deep-Link, Zitat vergleichen)",
            "- [ ] Unverifizierte References: pruefen, belegen oder entfernen",
            "- [ ] `lebenslage_ref` verlinkt korrekt auf die bestehende Lebenslage",
            "- [ ] `meta.herkunft` stimmt: ein Folge-Commit setzt `tessera` und die Nummer "
            "dieses PRs (fehlt er, von Hand nachtragen)",
            "",
        ]
    lines += [
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
    json_title = "## Extraktion (JSON, nicht eingespielt)" if abgleich else "## JSON"
    json_block = [
        json_title,
        "",
        "````json",
        json.dumps(process, indent=2, ensure_ascii=False),
        "````",
        "",
    ]
    body = "\n".join(lines + json_block + footer)
    if len(body) > MAX_BODY_CHARS:
        where = (
            f"`out/{proc.id}.json`"
            if abgleich
            else f"im Diff dieses PRs und im Bundle `out/outbox/{proc.id}/`"
        )
        note = [
            json_title,
            "",
            "_(JSON hier weggelassen — PR-Body-Limit. Die vollstaendige Datei",
            f"liegt {where}.)_",
            "",
        ]
        body = "\n".join(lines + note + footer)
    return body


def validate_merged(path: Path) -> tuple[bool, str]:
    """Faehrt den Vertrags-Validator auf der TATSAECHLICH eingereichten Datei
    (neue Extraktion oder abgeglichene Handdatei). Gate-Paritaet zur Ziel-CI:
    faellt das durch, wird KEIN PR geoeffnet."""
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


def load_pairing(
    proc_id: str, extracted: dict, canonical: dict
) -> tuple[list[tuple[list, list]] | None, str]:
    """Bestaetigte, aktuelle Paarung aus reports/eval/<id>.pairs.yaml fuer den
    Abgleich-Bericht. Rueckgabe: (Gruppen als (Extraktion-IDs, Hand-IDs), Hinweis).

    Nur `status: bestaetigt` und nur, wenn die Datei zu den aktuellen Labels
    passt (`evaluate.parse_pairing`). Sonst None — der Bericht listet dann alle
    Extraktionsschritte als Vorschlag. Die Paarung ist Lesehilfe, kein Gate.
    """
    from . import evaluate  # noqa: PLC0415

    path = evaluate.pairing_path(proc_id)
    rel = f"reports/eval/{path.name}"
    if not path.exists():
        return None, f"keine Paarungsdatei `{rel}` — alle Extraktionsschritte als Vorschlag"
    try:
        import yaml  # noqa: PLC0415

        data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
        groups, status = evaluate.parse_pairing(data, extracted, canonical)
    except evaluate.PairingError as exc:
        return None, (
            f"`{rel}` passt nicht zu dieser Extraktion ({len(exc.problems)} Befund(e), z.B. neuer Lauf) "
            "— nicht verwendet"
        )
    except Exception as exc:  # noqa: BLE001 — Lesehilfe, darf den PR nie verhindern
        return None, f"`{rel}` nicht lesbar ({exc.__class__.__name__}) — nicht verwendet"
    if status != "bestaetigt":
        return None, f"`{rel}` ist erst `{status}` — nicht verwendet"
    pairs = [([i for i, _ in g.ext], [i for i, _ in g.can]) for g in groups]
    return pairs, f"bestaetigte Paarung `{rel}` verwendet"


def open_draft_pr(
    proc: ProcessSource,
    process: dict,
    flags: list[str],
    crawl_meta: list[dict],
) -> str | None:
    """Erzeugt Branch + Datei + Draft-PR im Ziel-Repo; schreibt in jedem Fall
    das Bundle nach out/outbox/<id>/ (eingereichter Stand + PR-Body).

    Existiert die Zieldatei bereits, ist sie kanonisch: kein Merge, sondern
    Abgleich (`merge.sync_existing`). Der PR frischt nur `retrieved_at` auf und
    traegt alles Weitere als Vorschlag im Body; `meta.herkunft` bleibt, es gibt
    keinen Folge-Commit und kein Label. Aendert der Abgleich nichts, wird kein PR
    geoeffnet. Ohne GITHUB_TOKEN wird die (oeffentliche) Zieldatei trotzdem
    gelesen, damit das Bundle den Abgleich zeigt statt die Handdatei zu
    ueberschreiben — aber nichts geschrieben. Rueckgabe: PR-URL oder None.
    """
    token = os.environ.get("GITHUB_TOKEN")
    import httpx  # noqa: PLC0415 — lazy, Modul bleibt stdlib-importierbar

    target = os.environ.get("TARGET_REPO", DEFAULT_TARGET)
    api = f"https://api.github.com/repos/{target}"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "tessera/0.1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    branch = f"tessera/{proc.id}-{date.today().isoformat()}"
    path = f"{TARGET_PATH}/{proc.id}.json"

    import base64  # noqa: PLC0415

    with httpx.Client(headers=headers, timeout=30) as client:
        default_branch: str | None = None
        try:
            if token:
                default_branch = client.get(api).raise_for_status().json()["default_branch"]
            params = {"ref": default_branch} if default_branch else None
            existing = client.get(f"{api}/contents/{path}", params=params)
        except httpx.HTTPError as exc:
            if token:
                raise
            # Ohne Wissen, ob es eine Handdatei gibt, kein einreichbares Bundle:
            # die rohe Extraktion koennte sie beim Einreichen ueberschreiben.
            print(
                f"  [{proc.id}] Kein GITHUB_TOKEN; Zieldatei nicht abrufbar ({exc.__class__.__name__}) "
                "— kein Abgleich moeglich, KEIN Bundle. Netz pruefen und erneut ausfuehren.",
                file=sys.stderr,
            )
            return None
        if existing.status_code not in (200, 404):
            # 401/403/429: Rechte, Policy oder Rate-Limit. Ohne Wissen, ob es eine
            # Handdatei gibt, nichts einreichen (sie koennte ueberschrieben werden).
            print(
                f"  [{proc.id}] Zieldatei {path}: HTTP {existing.status_code} — unklar, ob es eine "
                "Handdatei gibt. KEIN PR, kein Bundle.",
                file=sys.stderr,
            )
            return None

        existing_sha: str | None = None
        abgleich: AbgleichReport | None = None
        final_process = process
        if existing.status_code == 200:
            existing_sha = existing.json()["sha"]
            try:
                existing_doc = json.loads(base64.b64decode(existing.json()["content"]).decode("utf-8"))
                pairing, pairing_note = load_pairing(proc.id, process, existing_doc)
                final_process, abgleich = sync_existing(
                    existing_doc, process, pairing=pairing, pairing_note=pairing_note
                )
            except (MergeConflict, json.JSONDecodeError, ValueError) as exc:
                print(
                    f"  [{proc.id}] Bestehende Datei {path} nicht abgleichbar ({exc}) — UEBERSPRUNGEN, kein PR.",
                    file=sys.stderr,
                )
                return None
            print(
                f"  [{proc.id}] Abgleich mit {path}: {len(abgleich.refreshed)} aufgefrischt, "
                f"{len(abgleich.refs_confirmed)} Beleg(e) wiedergefunden, "
                f"{len(abgleich.refs_not_found)} nicht, {len(abgleich.step_proposals)} Schritt- und "
                f"{len(abgleich.ref_proposals)} Beleg-Vorschlag/-Vorschlaege."
            )

        body = build_pr_body(
            proc,
            process,
            flags,
            crawl_meta,
            abgleich=build_abgleich_report(abgleich, path) if abgleich else None,
        )
        bundle_dir = write_bundle(proc, final_process, body)  # lokales Artefakt = eingereichter Stand

        if abgleich is not None and not abgleich.changed:
            print(f"  [{proc.id}] Abgleich ohne Aenderung an {path} — KEIN PR. Bericht: {bundle_dir}")
            return None

        # Gate-Paritaet: den einzureichenden Stand gegen den Vertrags-Validator
        # pruefen, BEVOR ein PR aufgemacht wird — auch fuers Bundle ohne Token,
        # dessen Body «bestanden» sagt.
        merged_ok, validator_out = validate_merged(bundle_dir / f"{proc.id}.json")
        if not merged_ok:
            print(
                f"  [{proc.id}] Einzureichender Stand besteht den Vertrags-Validator NICHT "
                f"— KEIN PR. Bundle zur Korrektur: {bundle_dir}\n{validator_out.strip()}",
                file=sys.stderr,
            )
            return None
        if not token:
            print(
                f"  [{proc.id}] Kein GITHUB_TOKEN im ENV — PR-Bundle liegt in {bundle_dir} (manuell einreichen)."
            )
            return None

        content = json.dumps(final_process, indent=2, ensure_ascii=False) + "\n"

        base_sha = (client.get(f"{api}/git/ref/heads/{default_branch}").raise_for_status().json())["object"][
            "sha"
        ]
        # Branch anlegen — oder, wenn er aus einem frueheren (Teil-)Lauf schon
        # existiert (der Name ist tagesdatiert), idempotent auf base zuruecksetzen,
        # statt mit 422 abzubrechen. Zurueckgesetzt wird aber NUR ein Branch,
        # dessen Head ein tessera-Commit ist: hat ein Mensch dort nachgearbeitet
        # (fremde Commit-Message), wird abgebrochen statt still ueberschrieben.
        created = client.post(f"{api}/git/refs", json={"ref": f"refs/heads/{branch}", "sha": base_sha})
        if created.status_code == 422:
            head_msg = str(
                client.get(f"{api}/commits/{branch}")
                .raise_for_status()
                .json()
                .get("commit", {})
                .get("message", "")
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
            msg = f"feat(prozesse): {proc.id} — Abgleich, Belege aufgefrischt (tessera v1)"
        put: dict = {
            "message": msg,
            "content": base64.b64encode(content.encode()).decode(),
            "branch": branch,
        }
        if existing_sha:
            put["sha"] = existing_sha
        file_sha = client.put(f"{api}/contents/{path}", json=put).raise_for_status().json()["content"]["sha"]

        created_pr = client.post(
            f"{api}/pulls",
            json={
                # Titel ist Plaintext (kein Markdown/Mentions) — nur Whitespace
                # kollabieren, damit ein mehrzeiliges LLM-title nicht bricht.
                "title": f"tessera v1: {'Abgleich ' if existing_sha else ''}"
                f"{_WS_RUN.sub(' ', final_process['title']['de']).strip()} ({proc.id})",
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
            existing = (
                client.get(f"{api}/pulls", params={"head": f"{owner}:{branch}", "state": "open"})
                .raise_for_status()
                .json()
            )
            if existing:
                url = existing[0]["html_url"]
                print(f"  [{proc.id}] Bestehender Draft-PR aktualisiert: {url}")
                if existing_sha is None:  # Abgleich-PR: meta.herkunft bleibt, kein Label
                    _folge_commit_herkunft(
                        client,
                        api,
                        proc,
                        path,
                        branch,
                        final_process,
                        existing[0]["number"],
                        file_sha,
                        body,
                        neu=True,
                        http_error=httpx.HTTPError,
                    )
                return url
            created_pr.raise_for_status()  # 422 aus anderem Grund -> echter Fehler
        pr = created_pr.raise_for_status().json()
        print(f"  [{proc.id}] Draft-PR erstellt: {pr['html_url']}")
        if existing_sha is None:  # Abgleich-PR: meta.herkunft bleibt, kein Label
            _folge_commit_herkunft(
                client,
                api,
                proc,
                path,
                branch,
                final_process,
                pr["number"],
                file_sha,
                body,
                neu=True,
                http_error=httpx.HTTPError,
            )
    return pr["html_url"]


def _folge_commit_herkunft(
    client,  # httpx.Client (oder ein Test-Double mit put/post)
    api: str,
    proc: ProcessSource,
    path: str,
    branch: str,
    process: dict,
    pr_number: int,
    file_sha: str,
    body: str,
    *,
    neu: bool,
    http_error: type[Exception],
) -> None:
    """Folge-Commit: die eigene PR-Nummer in meta.herkunft (Vertrag 0.2.0).

    Die Nummer steht erst nach dem Oeffnen des PRs fest, deshalb ein zweiter
    Commit auf denselben Branch. Best effort: scheitert er, bleibt der PR mit
    dem ersten (gueltigen) Stand stehen, und die Reviewer-Checkliste verlangt
    das Nachtragen von Hand. Die Commit-Message beginnt mit 'feat(prozesse):',
    damit ein Re-Run den Branch weiterhin als tessera-eigen erkennt.
    `http_error` ist die Fehlerklasse des Clients (httpx.HTTPError) — als
    Parameter, damit das Modul und seine Tests stdlib-rein bleiben.
    """
    import base64  # noqa: PLC0415

    updated, note = apply_herkunft(process, pr_number, neu=neu)
    if note:
        print(f"  [{proc.id}] {note}", file=sys.stderr)
    if updated != process:
        bundle_dir = write_bundle(proc, updated, body)
        ok, validator_out = validate_merged(bundle_dir / f"{proc.id}.json")
        if not ok:
            print(
                f"  [{proc.id}] Stand mit meta.herkunft besteht den Vertrags-Validator NICHT "
                f"— kein Folge-Commit, bitte im Review nachtragen.\n{validator_out.strip()}",
                file=sys.stderr,
            )
            write_bundle(proc, process, body)  # Bundle = tatsaechlich eingereichter Stand
            return
        content = json.dumps(updated, indent=2, ensure_ascii=False) + "\n"
        try:
            client.put(
                f"{api}/contents/{path}",
                json={
                    "message": f"feat(prozesse): {proc.id} — meta.herkunft mit PR #{pr_number} (tessera v1)",
                    "content": base64.b64encode(content.encode()).decode(),
                    "branch": branch,
                    "sha": file_sha,
                },
            ).raise_for_status()
            print(f"  [{proc.id}] meta.herkunft mit PR #{pr_number} nachgetragen (Folge-Commit).")
        except http_error as exc:
            write_bundle(proc, process, body)
            print(
                f"  [{proc.id}] Folge-Commit fuer meta.herkunft fehlgeschlagen ({exc}) "
                "— bitte im Review nachtragen.",
                file=sys.stderr,
            )
    try:
        client.post(f"{api}/issues/{pr_number}/labels", json={"labels": [SOURCE_LABEL]}).raise_for_status()
    except http_error as exc:
        print(f"  [{proc.id}] Label {SOURCE_LABEL!r} nicht gesetzt ({exc}).", file=sys.stderr)
