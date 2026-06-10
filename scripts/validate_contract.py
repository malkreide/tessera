#!/usr/bin/env python3
"""Vertrags-Validator fuer Tessera-Prozess-JSONs.

Prueft Prozess-JSONs gegen den Datenvertrag (docs/data-contract.md /
docs/process.schema.json). Bewusst OHNE externe Dependencies (nur stdlib),
damit der Check ueberall laeuft (lokal und CI).

Geprueft wird:
  * Struktur und Typen (Pflichtfelder, Enums, Muster).
  * Graph-Integritaet: eindeutige step_ids, existierende depends_on,
    kein Selbstbezug, mindestens ein Start-Schritt, keine Zyklen (DAG).
  * Referenz-Integritaet: eindeutige reference_ids, reference_ids in Schritten
    verweisen auf existierende references.
  * Grounding-Gate: jede Reference traegt eine nicht-leere source_quote.
  * KARDINALREGEL ("Link, don't assert"): ein Step-Label darf keine bindende
    Zahl (Frist/Gebuehr in Verbindung mit einer Einheit) enthalten. Verstoesse
    sind Fehler, kein Warnhinweis.

Hinweis: Dies ist der Entwurf-Check. Kanonisch ist das v0-Schema im Repo
maschinerie-zuerich, sobald es existiert. Bei Abweichung: stoppen und fragen.

Aufruf:
    python scripts/validate_contract.py [PFAD ...]
Ohne Pfade werden examples/*.json geprueft.
Exit-Code 0 = alles gueltig, 1 = mindestens ein Fehler.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

AUDIENCES = {"bevoelkerung", "wirtschaft", "behoerden"}
LOCALES = ("de", "en", "fr", "it", "leichte_sprache")

KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
ISO = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)

# Kardinalregel-Lint: Zahl in Verbindung mit einer bindenden Einheit.
_UNIT = r"(?:CHF|Fr\.?|Franken|%|Prozent|Tag(?:e|en)?|Woche(?:n)?|Monat(?:e|en)?|Jahr(?:e|en)?|Werktag(?:e|en)?)"
BINDING_VALUE = re.compile(
    rf"(?:\d[\d'.,]*\s*{_UNIT}\b)|(?:(?:CHF|Fr\.?)\s*\d)",
    re.IGNORECASE,
)


class Report:
    """Sammelt Fehler (lassen den Check scheitern) und Hinweise."""

    def __init__(self, path: Path):
        self.path = path
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.pending: list[str] = []  # i18n-Felder ohne Uebersetzung

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def pending_translation(self, where: str) -> None:
        self.pending.append(where)

    @property
    def ok(self) -> bool:
        return not self.errors


def _is_i18n(value: object) -> bool:
    return isinstance(value, dict) and isinstance(value.get("de"), str)


def _check_i18n(rep: Report, where: str, value: object, require_de: bool = True) -> None:
    if not isinstance(value, dict):
        rep.error(f"{where}: muss ein i18n-Objekt sein.")
        return
    unknown = set(value) - set(LOCALES)
    if unknown:
        rep.error(f"{where}: unbekannte Sprach-Schluessel {sorted(unknown)}.")
    de = value.get("de")
    if require_de and (not isinstance(de, str) or not de.strip()):
        rep.error(f"{where}: 'de' ist Pflicht und darf nicht leer sein.")
    for loc in ("en", "fr", "it", "leichte_sprache"):
        v = value.get(loc)
        if v is not None and not isinstance(v, str):
            rep.error(f"{where}.{loc}: muss ein String sein.")
        elif v is None or not v.strip():
            rep.pending_translation(f"{where}.{loc}")


def _check_iso(rep: Report, where: str, value: object) -> None:
    if not isinstance(value, str) or not ISO.match(value):
        rep.error(f"{where}: kein ISO-8601-Zeitstempel ({value!r}).")
        return
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        rep.error(f"{where}: ungueltiges Datum ({value!r}).")


def _check_url(rep: Report, where: str, value: object) -> None:
    if not isinstance(value, str) or not re.match(r"^https?://", value):
        rep.error(f"{where}: keine http(s)-URL ({value!r}).")


def _check_cardinal_rule(rep: Report, step_id: object, label: object) -> None:
    if not isinstance(label, dict):
        return
    for loc, text in label.items():
        if isinstance(text, str):
            hit = BINDING_VALUE.search(text)
            if hit:
                rep.error(
                    f"Schritt {step_id} label.{loc}: KARDINALREGEL verletzt — "
                    f"bindende Zahl {hit.group(0)!r} gehoert in eine Reference "
                    f"(Label + Link), nicht ins Step-Label: {text!r}"
                )


def _check_steps(rep: Report, steps: object) -> set[int]:
    seen: set[int] = set()
    if not isinstance(steps, list) or not steps:
        rep.error("steps: muss eine nicht-leere Liste sein.")
        return seen
    for i, step in enumerate(steps):
        where = f"steps[{i}]"
        if not isinstance(step, dict):
            rep.error(f"{where}: muss ein Objekt sein.")
            continue
        sid = step.get("step_id")
        if not isinstance(sid, int) or isinstance(sid, bool) or sid < 1:
            rep.error(f"{where}.step_id: Pflicht, integer >= 1.")
        elif sid in seen:
            rep.error(f"{where}.step_id: {sid} ist nicht eindeutig.")
        else:
            seen.add(sid)
        if not isinstance(step.get("actor"), str) or not step["actor"].strip():
            rep.error(f"{where}.actor: Pflicht, nicht-leerer String.")
        _check_i18n(rep, f"{where}.label", step.get("label"))
        _check_cardinal_rule(rep, sid, step.get("label"))
        dep = step.get("depends_on")
        if not isinstance(dep, list) or any(
            not isinstance(d, int) or isinstance(d, bool) for d in dep
        ):
            rep.error(f"{where}.depends_on: Pflicht, Liste von step_ids (leer = Start).")
        ref_ids = step.get("reference_ids", [])
        if ref_ids and (
            not isinstance(ref_ids, list)
            or any(not isinstance(r, int) or isinstance(r, bool) for r in ref_ids)
        ):
            rep.error(f"{where}.reference_ids: Liste von reference_ids.")
    return seen


def _check_graph(rep: Report, steps: list, step_ids: set[int]) -> None:
    edges: dict[int, list[int]] = {}
    starts = 0
    for step in steps:
        if not isinstance(step, dict):
            continue
        sid = step.get("step_id")
        deps = step.get("depends_on") or []
        if not isinstance(sid, int):
            continue
        edges[sid] = []
        if not deps:
            starts += 1
        for d in deps:
            if d == sid:
                rep.error(f"Schritt {sid}: depends_on darf nicht auf sich selbst zeigen.")
            elif d not in step_ids:
                rep.error(f"Schritt {sid}: depends_on {d} existiert nicht.")
            else:
                edges.setdefault(d, []).append(sid)
    if step_ids and starts == 0:
        rep.error("Graph: kein Start-Schritt (keiner mit leerem depends_on).")

    # Zyklus-Erkennung (DFS mit Faerbung).
    WHITE, GREY, BLACK = 0, 1, 2
    color = {n: WHITE for n in step_ids}

    def visit(n: int) -> bool:
        color[n] = GREY
        for m in edges.get(n, []):
            if color.get(m) == GREY or (color.get(m) == WHITE and visit(m)):
                return True
        color[n] = BLACK
        return False

    for n in step_ids:
        if color[n] == WHITE and visit(n):
            rep.error("Graph: Zyklus in depends_on (muss ein DAG sein).")
            break


def _check_references(rep: Report, refs: object) -> set[int]:
    seen: set[int] = set()
    if refs is None:
        return seen
    if not isinstance(refs, list):
        rep.error("references: muss eine Liste sein.")
        return seen
    for i, ref in enumerate(refs):
        where = f"references[{i}]"
        if not isinstance(ref, dict):
            rep.error(f"{where}: muss ein Objekt sein.")
            continue
        rid = ref.get("reference_id")
        if not isinstance(rid, int) or isinstance(rid, bool) or rid < 1:
            rep.error(f"{where}.reference_id: Pflicht, integer >= 1.")
        elif rid in seen:
            rep.error(f"{where}.reference_id: {rid} ist nicht eindeutig.")
        else:
            seen.add(rid)
        _check_i18n(rep, f"{where}.label", ref.get("label"))
        _check_url(rep, f"{where}.source_url", ref.get("source_url"))
        sq = ref.get("source_quote")
        if not isinstance(sq, str) or not sq.strip():
            rep.error(
                f"{where}.source_quote: Pflicht (Grounding-Gate) — "
                "nicht belegbare Referenzen werden verworfen, nicht ausgegeben."
            )
        _check_iso(rep, f"{where}.retrieved_at", ref.get("retrieved_at"))
    return seen


def validate(data: object, rep: Report) -> None:
    if not isinstance(data, dict):
        rep.error("Wurzel: muss ein Objekt sein.")
        return

    required = {
        "schema_version", "id", "lebenslage_ref", "title", "target_audience",
        "steps", "source_url", "retrieved_at", "disclaimer_key",
    }
    for field in sorted(required - set(data)):
        rep.error(f"Pflichtfeld fehlt: {field}")

    allowed = required | {"preconditions", "references"}
    for field in sorted(set(data) - allowed):
        rep.error(f"Unbekanntes Feld: {field}")

    if "schema_version" in data and not SEMVER.match(str(data["schema_version"])):
        rep.error(f"schema_version: kein SemVer ({data['schema_version']!r}).")

    pid = data.get("id")
    if not isinstance(pid, str) or not KEBAB.match(pid):
        rep.error(f"id: muss kebab-case sein ({pid!r}).")
    lref = data.get("lebenslage_ref")
    if not isinstance(lref, str) or not KEBAB.match(lref):
        rep.error(f"lebenslage_ref: muss kebab-case sein ({lref!r}).")
    if isinstance(pid, str) and isinstance(lref, str) and pid != lref:
        rep.error(f"id ({pid!r}) und lebenslage_ref ({lref!r}) muessen identisch sein.")

    if "title" in data:
        _check_i18n(rep, "title", data["title"])
    if data.get("target_audience") not in AUDIENCES:
        rep.error(
            f"target_audience: muss eines von {sorted(AUDIENCES)} sein "
            f"({data.get('target_audience')!r})."
        )
    if "preconditions" in data:
        pc = data["preconditions"]
        if not isinstance(pc, dict) or not isinstance(pc.get("de"), list):
            rep.error("preconditions: i18n-Liste mit 'de' als Array erwartet.")
    if "source_url" in data:
        _check_url(rep, "source_url", data["source_url"])
    if "retrieved_at" in data:
        _check_iso(rep, "retrieved_at", data["retrieved_at"])
    if not isinstance(data.get("disclaimer_key"), str) or not data.get("disclaimer_key", "").strip():
        rep.error("disclaimer_key: Pflicht, nicht-leerer String.")

    step_ids = _check_steps(rep, data.get("steps"))
    if isinstance(data.get("steps"), list):
        _check_graph(rep, data["steps"], step_ids)
    ref_ids = _check_references(rep, data.get("references"))

    # Querverweis Schritte -> references.
    if isinstance(data.get("steps"), list):
        for step in data["steps"]:
            if not isinstance(step, dict):
                continue
            for r in step.get("reference_ids", []) or []:
                if isinstance(r, int) and r not in ref_ids:
                    rep.error(
                        f"Schritt {step.get('step_id')}: reference_id {r} "
                        "existiert nicht in references."
                    )


def validate_file(path: Path) -> Report:
    rep = Report(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        rep.error("Datei nicht gefunden.")
        return rep
    except json.JSONDecodeError as exc:
        rep.error(f"Ungueltiges JSON: {exc}")
        return rep
    validate(data, rep)
    return rep


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parent.parent
    if argv:
        paths = [Path(a) for a in argv]
    else:
        paths = sorted((root / "examples").glob("*.json"))
    if not paths:
        print("Keine Prozess-JSONs gefunden.", file=sys.stderr)
        return 1

    failed = 0
    for path in paths:
        rep = validate_file(path)
        status = "OK  " if rep.ok else "FAIL"
        print(f"[{status}] {path}")
        for w in rep.warnings:
            print(f"    - Hinweis: {w}")
        if rep.pending:
            locs = sorted({p.rsplit('.', 1)[-1] for p in rep.pending})
            print(
                f"    - Hinweis: {len(rep.pending)} i18n-Feld(er) ohne Uebersetzung "
                f"({', '.join(locs)}) — ausstehend, nicht maschinell raten."
            )
        for e in rep.errors:
            print(f"    ! Fehler:  {e}")
        if not rep.ok:
            failed += 1

    total = len(paths)
    print(f"\n{total - failed}/{total} Datei(en) gueltig.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
