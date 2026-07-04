"""v2 Aenderungs-Diff: erkennt, wenn sich eine Quellseite seit dem zuletzt
committeten Fingerprint inhaltlich geaendert hat — damit ein Mensch weiss, dass
eine Re-Extraktion noetig sein koennte.

Baseline: reports/fingerprints/<id>.json (committet) — je Quell-URL ein SHA-256
ueber den NORMALISIERTEN Seitentext (grounding.normalize) plus Zeichenzahl.
Normalisierung heisst: rein kosmetische Aenderungen (Whitespace, Typografie,
Markdown-Deko, unsichtbare Zeichen) loesen KEINEN Treffer aus — nur inhaltliche.

Zusaetzlich (v2, 6b) legt `fingerprint` je URL den normalisierten Seitentext
ZEILENWEISE als committete Textdatei ab (reports/fingerprints/<id>/NN-slug.txt).
Meldet `diff` eine Aenderung, liefert er daraus einen unified-diff-AUSZUG
(baseline vs. live) mit — das source-change-Issue zeigt dann, WAS sich
geaendert hat, nicht nur WO. Der Hash bleibt unveraendert ueber den
Gesamt-Normaltext berechnet (bestehende Baselines bleiben gueltig); alte
Baselines ohne Textdatei liefern schlicht keinen Auszug.

Zwei Befehle:
  * `tessera fingerprint`  schreibt/aktualisiert die Baseline (nach einem Lauf).
  * `tessera diff`         vergleicht die Live-Seiten gegen die Baseline.

Beide sind netzgebunden, aber KEY-frei. Tri-state-Erreichbarkeit wie in verify:
tot (404/410) ist ein Datenproblem, blockiert/netzfehler/SPA/anders sind
Umgebungsbefunde (nicht-fatal). Der HTTP-Abruf ist injizierbar, damit die Logik
ohne httpx (dependency-frei) getestet werden kann.

Dieses Modul ergaenzt `tessera verify`: verify prueft Link-Rot und Drift der
EINZELNEN verifizierten Zitate; diff erkennt JEDE inhaltliche Seitenaenderung —
auch eine, die (noch) kein zitiertes Element beruehrt (z.B. ein neuer Schritt).
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from . import reach
from .grounding import normalize

if TYPE_CHECKING:  # nur fuer Typhinweise — kein Laufzeit-Import von config (pydantic),
    from .config import ProcessSource  # damit diff/Tests dependency-frei laufen (stdlib-CI).

# Repo-Wurzel ohne config-Import ableiten (src/tessera/diff.py -> parents[2]).
ROOT = Path(__file__).resolve().parents[2]
FINGERPRINTS = ROOT / "reports" / "fingerprints"


def _norm(md: str) -> str:
    return normalize(md)


def _sha(md: str) -> str:
    return hashlib.sha256(_norm(md).encode("utf-8")).hexdigest()


# Diff-Auszug: hoechstens so viele unified-diff-Zeilen, Zeilen gekappt — das
# Issue soll zeigen, WAS sich geaendert hat, nicht die ganze Seite tragen.
MAX_EXCERPT_LINES = 20
MAX_LINE_CHARS = 200

# Dateiname je URL (stdlib-Kopie von crawl._slug — crawl importiert httpx auf
# Modulebene und ist damit fuer den dependency-freien diff nicht importierbar).
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(url: str) -> str:
    parts = urlsplit(url)
    tail = (parts.path.rstrip("/").rsplit("/", 1)[-1] or parts.netloc).removesuffix(".html")
    return _SLUG_RE.sub("-", tail.lower()).strip("-") or "seite"


def _norm_lines(md: str) -> str:
    """ZEILENWEISE normalisierter Seitentext — nur fuer menschliche Diffs.

    Der Hash laeuft weiter ueber `_norm` (Gesamttext, zeilenlos) — bestehende
    Baselines bleiben gueltig; diese Fassung erhaelt die Zeilenstruktur, damit
    unified_diff brauchbare Ausschnitte liefert.
    """
    lines = (normalize(line) for line in md.splitlines())
    return "\n".join(line for line in lines if line)


def _excerpt(old_text: str, new_text: str) -> str:
    """Unified-Diff-Auszug baseline vs. live (gekappt, fuer Issue/CLI)."""
    old = [line[:MAX_LINE_CHARS] for line in old_text.splitlines()]
    new = [line[:MAX_LINE_CHARS] for line in new_text.splitlines()]
    delta = list(
        difflib.unified_diff(old, new, fromfile="baseline", tofile="live", lineterm="", n=1)
    )
    if len(delta) > MAX_EXCERPT_LINES:
        rest = len(delta) - MAX_EXCERPT_LINES
        delta = delta[:MAX_EXCERPT_LINES] + [f"… ({rest} weitere Diff-Zeilen gekappt)"]
    return "\n".join(delta)


def fp_path(proc_id: str) -> Path:
    return FINGERPRINTS / f"{proc_id}.json"


def load_fingerprints(proc_id: str) -> dict[str, dict]:
    """Baseline als {url: {sha256, chars}}. Leer, wenn keine Baseline existiert."""
    p = fp_path(proc_id)
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return {e["url"]: e for e in data.get("urls", [])}


def build_entries(proc: ProcessSource, fetch, retrieved_at: str) -> list[dict]:
    """Fingerprint-Eintraege bauen. fetch(url) -> (md, state).

    Nur erreichbare URLs mit nicht-leerem Text bekommen sha256/chars; sonst nur
    state (Umgebungsbefund — wird nicht in die Baseline eingefroren)."""
    out: list[dict] = []
    for url in proc.official_urls:
        md, state = fetch(url)
        entry: dict = {"url": url, "state": state, "retrieved_at": retrieved_at}
        if state == reach.OK and md.strip():
            entry["sha256"] = _sha(md)
            entry["chars"] = len(_norm(md))
            entry["text"] = _norm_lines(md)  # fuer die committete Diff-Basis
        out.append(entry)
    return out


def write_fingerprints(proc_id: str, entries: list[dict], retrieved_at: str) -> Path:
    """Committet die Baseline. Nur erreichbare URLs (mit sha256) werden gespeichert
    — Umgebungsbefunde (Block/Netzfehler) frieren wir bewusst nicht ein.

    Je URL wird zusaetzlich der zeilenweise normalisierte Seitentext als
    Textdatei abgelegt (reports/fingerprints/<id>/NN-slug.txt, committet) —
    die Basis fuer Diff-Auszuege. Nicht mehr gefuehrte Textdateien werden
    entfernt (das Verzeichnis gehoert vollstaendig dem Fingerprint)."""
    FINGERPRINTS.mkdir(parents=True, exist_ok=True)
    usable = [e for e in entries if "sha256" in e]

    textdir = FINGERPRINTS / proc_id
    textdir.mkdir(parents=True, exist_ok=True)
    wanted: set[str] = set()
    urls_doc: list[dict] = []
    for i, e in enumerate(usable, start=1):
        entry_doc: dict = {"url": e["url"], "sha256": e["sha256"], "chars": e["chars"]}
        if "text" in e:
            fname = f"{i:02d}-{_slug(e['url'])}.txt"
            wanted.add(fname)
            (textdir / fname).write_text(e["text"] + "\n", encoding="utf-8")
            entry_doc["text_file"] = f"{proc_id}/{fname}"
        urls_doc.append(entry_doc)
    for stale in textdir.glob("*.txt"):
        if stale.name not in wanted:
            stale.unlink()

    doc = {"id": proc_id, "retrieved_at": retrieved_at, "urls": urls_doc}
    p = fp_path(proc_id)
    p.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


@dataclass
class DiffReport:
    """Befund je Leistung. data_problem (geaendert/tot) kann einen Lauf scheitern
    lassen; Umgebungsbefunde (env) und new/removed sind Hinweise."""

    proc_id: str
    changed: list[str] = field(default_factory=list)    # inhaltliche Aenderung
    dead: list[str] = field(default_factory=list)       # 404/410 (Datenproblem)
    env: list[str] = field(default_factory=list)        # blockiert/netzfehler/anders
    new: list[str] = field(default_factory=list)        # in sources, nicht in baseline
    removed: list[str] = field(default_factory=list)    # in baseline, nicht in sources
    unchanged: list[str] = field(default_factory=list)
    # Je geaenderter URL ein unified-diff-Auszug baseline vs. live (nur wenn die
    # Baseline eine Textdatei traegt; alte Baselines liefern keinen Auszug).
    excerpts: dict[str, str] = field(default_factory=dict)
    no_baseline: bool = False

    @property
    def data_problem(self) -> bool:
        return bool(self.changed or self.dead)

    @property
    def touched(self) -> bool:
        return bool(
            self.changed or self.dead or self.env or self.new or self.removed
        )


def report_to_dict(rep: DiffReport) -> dict:
    """Maschinenlesbare Fassung eines DiffReports (fuer `diff --json` -> Cron/Issue)."""
    return {
        "id": rep.proc_id,
        "no_baseline": rep.no_baseline,
        "changed": rep.changed,
        "dead": rep.dead,
        "env": rep.env,
        "new": rep.new,
        "removed": rep.removed,
        "unchanged": rep.unchanged,
        "excerpts": rep.excerpts,
        "data_problem": rep.data_problem,
    }


def diff_process(proc: ProcessSource, fetch) -> DiffReport:
    """Vergleicht die Live-Seiten gegen die committete Baseline. fetch(url) ->
    (md, state). Ohne Baseline: no_baseline=True (kein Vergleich moeglich)."""
    rep = DiffReport(proc_id=proc.id)
    baseline = load_fingerprints(proc.id)
    if not baseline:
        rep.no_baseline = True
        return rep

    source_urls = list(dict.fromkeys(proc.official_urls))  # Reihenfolge, dedupe
    rep.new = [u for u in source_urls if u not in baseline]
    rep.removed = sorted(set(baseline) - set(source_urls))

    for url in source_urls:
        if url not in baseline:
            continue  # neu -> kein Vergleichswert
        md, state = fetch(url)
        if state == reach.OK and md.strip():
            if _sha(md) == baseline[url]["sha256"]:
                rep.unchanged.append(url)
            else:
                rep.changed.append(url)
                # Auszug nur, wenn die Baseline den Text traegt (neuere
                # Fingerprints); alte Hash-only-Baselines bleiben gueltig.
                text_file = baseline[url].get("text_file")
                if text_file:
                    p = FINGERPRINTS / text_file
                    if p.exists():
                        rep.excerpts[url] = _excerpt(
                            p.read_text(encoding="utf-8"), _norm_lines(md)
                        )
        elif state == reach.DEAD:
            rep.dead.append(url)
        else:
            rep.env.append(f"{url} ({state})")
    return rep
