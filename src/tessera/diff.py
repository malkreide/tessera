"""v2 Aenderungs-Diff: erkennt, wenn sich eine Quellseite seit dem zuletzt
committeten Fingerprint inhaltlich geaendert hat — damit ein Mensch weiss, dass
eine Re-Extraktion noetig sein koennte.

Baseline: reports/fingerprints/<id>.json (committet) — je Quell-URL ein SHA-256
ueber den NORMALISIERTEN Seitentext (grounding.normalize) plus Zeichenzahl.
Normalisierung heisst: rein kosmetische Aenderungen (Whitespace, Typografie,
Markdown-Deko, unsichtbare Zeichen) loesen KEINEN Treffer aus — nur inhaltliche.

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

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from . import reach
from .config import ROOT, ProcessSource
from .grounding import normalize

FINGERPRINTS = ROOT / "reports" / "fingerprints"


def _norm(md: str) -> str:
    return normalize(md)


def _sha(md: str) -> str:
    return hashlib.sha256(_norm(md).encode("utf-8")).hexdigest()


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
        out.append(entry)
    return out


def write_fingerprints(proc_id: str, entries: list[dict], retrieved_at: str) -> Path:
    """Committet die Baseline. Nur erreichbare URLs (mit sha256) werden gespeichert
    — Umgebungsbefunde (Block/Netzfehler) frieren wir bewusst nicht ein."""
    FINGERPRINTS.mkdir(parents=True, exist_ok=True)
    usable = [e for e in entries if "sha256" in e]
    doc = {
        "id": proc_id,
        "retrieved_at": retrieved_at,
        "urls": [
            {"url": e["url"], "sha256": e["sha256"], "chars": e["chars"]} for e in usable
        ],
    }
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
    no_baseline: bool = False

    @property
    def data_problem(self) -> bool:
        return bool(self.changed or self.dead)

    @property
    def touched(self) -> bool:
        return bool(
            self.changed or self.dead or self.env or self.new or self.removed
        )


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
        elif state == reach.DEAD:
            rep.dead.append(url)
        else:
            rep.env.append(f"{url} ({state})")
    return rep
