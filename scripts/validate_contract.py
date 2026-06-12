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
  * Grounding-Gate (statusabhaengig): status 'verifiziert' (Default) verlangt eine
    nicht-leere source_quote (Fehler); 'unverifiziert' darf leer sein (Hinweis).
  * KARDINALREGEL ("Link, don't assert"): kein gerenderter Text darf eine
    bindende Zahl (Wert + Einheit) enthalten. Gelintet werden die kanonischen
    Felder: title, description, preconditions[], steps[].label/.description,
    steps[].documents[].label, depends_on[].condition, references[].label und
    die reife-Freitexte. Verstoesse sind Fehler, kein Warnhinweis. Bindende
    Werte leben ausschliesslich im source_quote einer Reference.
  * Additive kanonische Felder (optional): city, description, actors, legal_basis,
    sources, reife, meta; Step type/description/documents/source_id/loops_back_to;
    Reference status. Damit validiert der Check reale kanonische Dateien 1:1.

Hinweis: Dieser Check ist auf das kanonische v0-Schema in maschinerie-zuerich
abgeglichen (Locale-Key 'ls', depends_on-Objektvariante, tagesgenaues Datum). Er
ist nicht kanonisch; bei Abweichung gilt maschinerie-zuerich — stoppen und fragen.

Aufruf:
    python scripts/validate_contract.py [PFAD ...]
Ohne Pfade werden examples/*.json geprueft.
Exit-Code 0 = alles gueltig, 1 = mindestens ein Fehler.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

AUDIENCES = {"bevoelkerung", "wirtschaft", "behoerden"}
# Locale-Schluessel: kanonisch ist 'ls' (Leichte Sprache) im Repo maschinerie-zuerich.
LOCALES = ("de", "en", "fr", "it", "ls")

# Additive kanonische Erweiterungen (maschinerie-zuerich, docs/process-data-contract.md).
STEP_TYPES = {"start", "input", "prozess", "entscheidung", "loop", "warten", "ende"}
ACTOR_TYPES = {"antragsteller", "behoerde", "fachstelle", "gericht", "dritte"}
REF_STATUS = {"verifiziert", "unverifiziert"}

KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
# ISO 8601: Tagesgenaues Datum (kanonisch, z.B. 2026-06-06) ODER voller Zeitstempel.
ISO = re.compile(
    r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2}))?$"
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
    for loc in ("en", "fr", "it", "ls"):
        v = value.get(loc)
        if v is not None and not isinstance(v, str):
            rep.error(f"{where}.{loc}: muss ein String sein.")
        elif v is None or not v.strip():
            rep.pending_translation(f"{where}.{loc}")


def _check_iso(rep: Report, where: str, value: object) -> None:
    if not isinstance(value, str) or not ISO.match(value):
        rep.error(f"{where}: kein ISO-8601-Datum/-Zeitstempel ({value!r}).")
        return
    try:
        if "T" in value:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            date.fromisoformat(value)
    except ValueError:
        rep.error(f"{where}: ungueltiges Datum ({value!r}).")


def _check_url(rep: Report, where: str, value: object) -> None:
    if not isinstance(value, str) or not re.match(r"^https?://", value):
        rep.error(f"{where}: keine http(s)-URL ({value!r}).")


def _dep_step_id(dep: object) -> int | None:
    """Normalisiert einen depends_on-Eintrag auf seine step_id.

    Erlaubt sind die kanonischen Varianten: ein integer ODER ein Objekt
    {step_id, condition?} (bedingte Kante). Gibt None zurueck, wenn der
    Eintrag keine gueltige step_id traegt.
    """
    if isinstance(dep, bool):
        return None
    if isinstance(dep, int):
        return dep
    if isinstance(dep, dict):
        sid = dep.get("step_id")
        if isinstance(sid, int) and not isinstance(sid, bool):
            return sid
    return None


def _lint_binding(rep: Report, where: str, i18n: object) -> None:
    """Kardinalregel: keine bindende Zahl (Wert + Einheit) in gerendertem Text.

    Gilt fuer jeden gerenderten i18n-Text (Step-Label, Step-/Prozess-Description).
    Bindende Werte leben ausschliesslich in references (Label + Link + source_quote).
    """
    if not isinstance(i18n, dict):
        return
    for loc, text in i18n.items():
        if isinstance(text, str):
            hit = BINDING_VALUE.search(text)
            if hit:
                rep.error(
                    f"{where}.{loc}: KARDINALREGEL verletzt — bindende Zahl "
                    f"{hit.group(0)!r} gehoert in eine Reference (Label + Link), "
                    f"nicht in gerenderten Text: {text!r}"
                )


def _lint_reife(rep: Report, reife: dict) -> None:
    """Kardinalregel auf den reife-Freitexten (kanonische Liste); das Objekt
    bleibt ansonsten Passthrough (experimentell)."""
    _lint_binding(rep, "reife.onceOnlyPotenzial", reife.get("onceOnlyPotenzial"))
    for key in ("nutzergruppen", "painPoints", "improvementIdeas"):
        items = reife.get(key)
        if isinstance(items, list):
            for i, item in enumerate(items):
                _lint_binding(rep, f"reife.{key}[{i}]", item)
    kpis = reife.get("wirkungKpi")
    if isinstance(kpis, list):
        for i, kpi in enumerate(kpis):
            if not isinstance(kpi, dict):
                continue
            _lint_binding(rep, f"reife.wirkungKpi[{i}].label", kpi.get("label"))
            wert = kpi.get("wert")
            if isinstance(wert, str):
                hit = BINDING_VALUE.search(wert)
                if hit:
                    rep.error(
                        f"reife.wirkungKpi[{i}].wert: KARDINALREGEL verletzt — "
                        f"bindende Zahl {hit.group(0)!r} gehoert in eine Reference: {wert!r}"
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
        allowed_step = {
            "step_id", "actor", "label", "depends_on", "reference_ids",
            # additive kanonische Erweiterungen:
            "type", "description", "documents", "source_id", "loops_back_to",
        }
        for f in sorted(set(step) - allowed_step):
            rep.error(f"{where}: unbekanntes Feld {f!r}.")
        if not isinstance(step.get("actor"), str) or not step["actor"].strip():
            rep.error(f"{where}.actor: Pflicht, nicht-leerer String.")
        _check_i18n(rep, f"{where}.label", step.get("label"))
        _lint_binding(rep, f"{where}.label", step.get("label"))
        # additive: type, description, documents, source_id, loops_back_to
        if "type" in step and step["type"] not in STEP_TYPES:
            rep.error(f"{where}.type: muss eines von {sorted(STEP_TYPES)} sein ({step['type']!r}).")
        if "description" in step:
            _check_i18n(rep, f"{where}.description", step["description"])
            _lint_binding(rep, f"{where}.description", step["description"])
        if "documents" in step:
            _check_documents(rep, f"{where}.documents", step["documents"])
        if "source_id" in step and not isinstance(step["source_id"], str):
            rep.error(f"{where}.source_id: muss ein String sein.")
        if "loops_back_to" in step:
            lbt = step["loops_back_to"]
            if not isinstance(lbt, list) or any(
                not isinstance(x, int) or isinstance(x, bool) for x in lbt
            ):
                rep.error(f"{where}.loops_back_to: Liste von step_ids erwartet.")
            elif step.get("type") != "loop":
                rep.warn(f"{where}.loops_back_to: nur auf type 'loop' vorgesehen.")
        dep = step.get("depends_on")
        if not isinstance(dep, list):
            rep.error(f"{where}.depends_on: Pflicht, Liste (leer = Start).")
        else:
            for j, d in enumerate(dep):
                if _dep_step_id(d) is None:
                    rep.error(
                        f"{where}.depends_on[{j}]: muss eine step_id (integer) "
                        "oder ein Objekt {step_id, condition?} sein."
                    )
                elif isinstance(d, dict):
                    extra = set(d) - {"step_id", "condition"}
                    if extra:
                        rep.error(f"{where}.depends_on[{j}]: unbekannte Felder {sorted(extra)}.")
                    cond = d.get("condition")
                    if "condition" in d and (
                        not isinstance(cond, dict)
                        or not isinstance(cond.get("de"), str)
                        or not cond["de"].strip()
                    ):
                        rep.error(f"{where}.depends_on[{j}].condition: i18n-Objekt mit 'de' erwartet.")
                    _lint_binding(rep, f"{where}.depends_on[{j}].condition", cond)
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
        for raw in deps:
            d = _dep_step_id(raw)
            if d is None:
                continue  # Typfehler wurde bereits in _check_steps gemeldet
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
        for f in sorted(set(ref) - {
            "reference_id", "label", "source_url", "source_quote",
            "retrieved_at", "status",
        }):
            rep.error(f"{where}: unbekanntes Feld {f!r}.")
        _check_i18n(rep, f"{where}.label", ref.get("label"))
        # Kardinalregel: das Label benennt den Wert, traegt aber nie die Zahl.
        _lint_binding(rep, f"{where}.label", ref.get("label"))
        _check_url(rep, f"{where}.source_url", ref.get("source_url"))

        status = ref.get("status", "verifiziert")  # default kanonisch: verifiziert
        if status not in REF_STATUS:
            rep.error(f"{where}.status: muss eines von {sorted(REF_STATUS)} sein ({status!r}).")
        sq = ref.get("source_quote")
        has_quote = isinstance(sq, str) and sq.strip()
        if sq is not None and not isinstance(sq, str):
            rep.error(f"{where}.source_quote: muss ein String sein.")
        elif status == "verifiziert" and not has_quote:
            # Grounding-Gate: ein verifizierter Beleg braucht ein woertliches Zitat.
            rep.error(
                f"{where}.source_quote: Pflicht bei status 'verifiziert' "
                "(Grounding-Gate) — woertliche Belegstelle erforderlich."
            )
        elif status == "unverifiziert" and not has_quote:
            # Erlaubt: UI rendert nur Label + Link; fuer Reviewer markiert.
            rep.warn(f"{where}: status 'unverifiziert' ohne source_quote — fuer Review offen.")
        _check_iso(rep, f"{where}.retrieved_at", ref.get("retrieved_at"))
    return seen


def _check_documents(rep: Report, where: str, docs: object) -> None:
    if not isinstance(docs, list):
        rep.error(f"{where}: muss eine Liste sein.")
        return
    for i, d in enumerate(docs):
        w = f"{where}[{i}]"
        if not isinstance(d, dict):
            rep.error(f"{w}: muss ein Objekt sein.")
            continue
        for f in sorted(set(d) - {"label", "url", "required"}):
            rep.error(f"{w}: unbekanntes Feld {f!r}.")
        _check_i18n(rep, f"{w}.label", d.get("label"))
        _lint_binding(rep, f"{w}.label", d.get("label"))
        if "url" in d:
            _check_url(rep, f"{w}.url", d["url"])
        if "required" in d and not isinstance(d["required"], bool):
            rep.error(f"{w}.required: muss boolean sein.")


def _check_actors(rep: Report, actors: object) -> set[str]:
    ids: set[str] = set()
    if not isinstance(actors, list):
        rep.error("actors: muss eine Liste sein.")
        return ids
    for i, a in enumerate(actors):
        w = f"actors[{i}]"
        if not isinstance(a, dict):
            rep.error(f"{w}: muss ein Objekt sein.")
            continue
        for f in sorted(set(a) - {"id", "label", "type", "einheit_ref"}):
            rep.error(f"{w}: unbekanntes Feld {f!r}.")
        aid = a.get("id")
        if not isinstance(aid, str) or not aid.strip():
            rep.error(f"{w}.id: Pflicht, nicht-leerer String.")
        elif aid in ids:
            rep.error(f"{w}.id: {aid!r} ist nicht eindeutig.")
        else:
            ids.add(aid)
        _check_i18n(rep, f"{w}.label", a.get("label"))
        if a.get("type") not in ACTOR_TYPES:
            rep.error(f"{w}.type: muss eines von {sorted(ACTOR_TYPES)} sein ({a.get('type')!r}).")
        if "einheit_ref" in a and not isinstance(a["einheit_ref"], str):
            rep.error(f"{w}.einheit_ref: muss ein String sein.")
    return ids


def _check_sources(rep: Report, sources: object) -> set[str]:
    ids: set[str] = set()
    if not isinstance(sources, list):
        rep.error("sources: muss eine Liste sein.")
        return ids
    for i, s in enumerate(sources):
        w = f"sources[{i}]"
        if not isinstance(s, dict):
            rep.error(f"{w}: muss ein Objekt sein.")
            continue
        for f in sorted(set(s) - {"id", "title", "url", "retrieved_at"}):
            rep.error(f"{w}: unbekanntes Feld {f!r}.")
        sid = s.get("id")
        if not isinstance(sid, str) or not sid.strip():
            rep.error(f"{w}.id: Pflicht, nicht-leerer String.")
        elif sid in ids:
            rep.error(f"{w}.id: {sid!r} ist nicht eindeutig.")
        else:
            ids.add(sid)
        if not isinstance(s.get("title"), str) or not s.get("title", "").strip():
            rep.error(f"{w}.title: Pflicht, nicht-leerer String.")
        _check_url(rep, f"{w}.url", s.get("url"))
        _check_iso(rep, f"{w}.retrieved_at", s.get("retrieved_at"))
    return ids


def _check_legal_basis(rep: Report, lb: object) -> None:
    if not isinstance(lb, list):
        rep.error("legal_basis: muss eine Liste sein.")
        return
    for i, e in enumerate(lb):
        w = f"legal_basis[{i}]"
        if not isinstance(e, dict):
            rep.error(f"{w}: muss ein Objekt sein.")
            continue
        for f in sorted(set(e) - {"label", "url"}):
            rep.error(f"{w}: unbekanntes Feld {f!r}.")
        if not isinstance(e.get("label"), str) or not e.get("label", "").strip():
            rep.error(f"{w}.label: Pflicht, nicht-leerer String.")
        if "url" in e:
            _check_url(rep, f"{w}.url", e["url"])


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

    allowed = required | {
        "$schema", "preconditions", "references",
        # additive kanonische Erweiterungen (maschinerie-zuerich):
        "city", "description", "actors", "legal_basis", "sources", "reife", "meta",
    }
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
        _lint_binding(rep, "title", data["title"])
    if data.get("target_audience") not in AUDIENCES:
        rep.error(
            f"target_audience: muss eines von {sorted(AUDIENCES)} sein "
            f"({data.get('target_audience')!r})."
        )
    if "preconditions" in data:
        pc = data["preconditions"]
        if not isinstance(pc, list):
            rep.error("preconditions: Liste von i18n-Objekten erwartet.")
        else:
            for i, item in enumerate(pc):
                _check_i18n(rep, f"preconditions[{i}]", item)
                _lint_binding(rep, f"preconditions[{i}]", item)
    if "source_url" in data:
        _check_url(rep, "source_url", data["source_url"])
    if "retrieved_at" in data:
        _check_iso(rep, "retrieved_at", data["retrieved_at"])
    if not isinstance(data.get("disclaimer_key"), str) or not data.get("disclaimer_key", "").strip():
        rep.error("disclaimer_key: Pflicht, nicht-leerer String.")

    # --- Additive kanonische Erweiterungen (alle optional) ---
    if "city" in data and (not isinstance(data["city"], str) or not data["city"].strip()):
        rep.error("city: muss ein nicht-leerer String sein.")
    if "description" in data:
        _check_i18n(rep, "description", data["description"])
        _lint_binding(rep, "description", data["description"])
    actor_ids = _check_actors(rep, data["actors"]) if "actors" in data else set()
    if "legal_basis" in data:
        _check_legal_basis(rep, data["legal_basis"])
    source_ids = _check_sources(rep, data["sources"]) if "sources" in data else set()
    if "reife" in data:
        if not isinstance(data["reife"], dict):
            rep.error("reife: muss ein Objekt sein.")
        else:
            _lint_reife(rep, data["reife"])
    if "meta" in data:
        meta = data["meta"]
        if not isinstance(meta, dict):
            rep.error("meta: muss ein Objekt sein.")
        else:
            for f in sorted(set(meta) - {"erstellt", "aktualisiert", "maintainer", "lizenz"}):
                rep.error(f"meta: unbekanntes Feld {f!r}.")

    step_ids = _check_steps(rep, data.get("steps"))
    if isinstance(data.get("steps"), list):
        _check_graph(rep, data["steps"], step_ids)
    ref_ids = _check_references(rep, data.get("references"))

    # Querverweise Schritte -> references / sources / actors / loops_back_to.
    if isinstance(data.get("steps"), list):
        for step in data["steps"]:
            if not isinstance(step, dict):
                continue
            sid = step.get("step_id")
            for r in step.get("reference_ids", []) or []:
                if isinstance(r, int) and r not in ref_ids:
                    rep.error(f"Schritt {sid}: reference_id {r} existiert nicht in references.")
            src = step.get("source_id")
            if isinstance(src, str) and source_ids and src not in source_ids:
                rep.error(f"Schritt {sid}: source_id {src!r} existiert nicht in sources.")
            actor = step.get("actor")
            if actor_ids and isinstance(actor, str) and actor not in actor_ids:
                # Wenn actors[] vorhanden ist, sollte step.actor eine actors[].id sein.
                rep.warn(f"Schritt {sid}: actor {actor!r} ist keine actors[].id.")
            for t in step.get("loops_back_to", []) or []:
                if isinstance(t, int) and t not in step_ids:
                    rep.error(f"Schritt {sid}: loops_back_to {t} existiert nicht.")


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
