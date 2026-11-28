"""Schutz der Ausgabe-Kette gegen Abbrueche und veraltete Extraktionen (stdlib).

Anlass (Lauf L5, 2026-11-27): Ein abgelaufener API-Key liess `extract` beim
ersten Request mit HTTP 401 abbrechen — fuer alle Leistungen, mit Traceback. In
einem frueheren Versuch liefen `validate`, `eval` und `pr` danach still auf den
`out/<id>.json` eines alten Laufs weiter. Drei Regeln:

  * Anmeldung abgelehnt (401/403) oder Key fehlt -> der ganze Lauf endet sofort
    mit klarer Meldung; jede weitere Leistung scheiterte am selben Key.
  * Jeder andere Fehler beendet nur DIESE Leistung; die Schleife laeuft weiter.
  * Vor jedem Versuch wird die vorige Ausgabe nach `*.prev` verschoben. Scheitert
    der Versuch, gibt es keine `out/<id>.json` — die Folgeschritte melden «fehlt»
    statt auf altem Stand zu arbeiten. Zusaetzlich gilt eine Ausgabe, die aelter
    ist als der letzte Crawl, als veraltet (`stale_reason`).

Keine Fehlermeldung gibt Request-Inhalte oder Header aus — nur Typ, HTTP-Status
und eine gekuerzte Meldung des Anbieters (die keinen Key enthaelt).
"""

from __future__ import annotations

from pathlib import Path

AUTH_STATUS = frozenset({401, 403})
PREV_SUFFIX = ".prev"
_MAX_DETAIL = 300


class MissingKeyError(SystemExit):
    """Der LLM-Key fehlt im ENV — gilt fuer jede Leistung, darum Abbruch des Laufs.

    Unterklasse von SystemExit: ausserhalb von `extract` bleibt das Verhalten
    (Abbruch mit Meldung) wie bisher."""


def auth_status(exc: BaseException) -> int | None:
    """HTTP-Status 401/403, wenn `exc` (oder eine Ursache in der Kette) eine
    abgelehnte Anmeldung beim LLM-Anbieter ist; sonst None.

    Liest nur das Attribut `status_code` (pydantic-ai `ModelHTTPError`,
    anthropic `APIStatusError`) — kein Import der Anbieter-Pakete."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        status = getattr(current, "status_code", None)
        if isinstance(status, int) and status in AUTH_STATUS:
            return status
        current = current.__cause__ or current.__context__
    return None


def describe(exc: BaseException) -> str:
    """Kurze, einzeilige Beschreibung eines Fehlers fuer die Konsole."""
    status = getattr(exc, "status_code", None)
    head = type(exc).__name__ + (f" (HTTP {status})" if isinstance(status, int) else "")
    detail = " ".join(str(exc).split())
    if len(detail) > _MAX_DETAIL:
        detail = detail[: _MAX_DETAIL - 1] + "…"
    return f"{head}: {detail}" if detail else head


def retire_previous(paths: list[Path]) -> list[Path]:
    """Verschiebt vorhandene Ausgaben nach `<name>.prev` (ein alter `.prev` wird
    ersetzt) und gibt die neuen Pfade zurueck. Nichts wird geloescht: die vorige
    Extraktion bleibt zum Vergleich oder Zurueckholen liegen."""
    moved = []
    for path in paths:
        if path.exists():
            target = path.with_name(path.name + PREV_SUFFIX)
            path.replace(target)
            moved.append(target)
    return moved


def stale_reason(out_json: Path, crawl_meta: Path) -> str:
    """Leer, wenn `out_json` mindestens so neu ist wie der letzte Crawl; sonst
    der Grund. Ohne Crawl-Metadaten (z.B. Fixture) gilt die Ausgabe nicht als
    veraltet — dann fehlt der Vergleichspunkt, nicht die Frische."""
    if not crawl_meta.exists() or not out_json.exists():
        return ""
    if crawl_meta.stat().st_mtime > out_json.stat().st_mtime:
        return (
            f"{out_json.name} ist aelter als der letzte Crawl ({crawl_meta.parent.name}/"
            f"{crawl_meta.name}) — veraltete Extraktion, zuerst `tessera extract`."
        )
    return ""
