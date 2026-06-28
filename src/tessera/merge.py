"""Feldweises Mergen gegen bestehende, handgepflegte Zieldateien.

Hintergrund: tessera extrahiert *struktur-only* (de-Text plus leere en/fr/it).
Im Ziel-Repo existieren fuer manche Leistungen bereits von Hand angereicherte
Dateien mit vollstaendigen Uebersetzungen (de/en/fr/it/ls) und description-
Bloecken. Ein blindes PUT-mit-sha wuerde diese reicheren Handdaten durch die
aermere Extraktion ersetzen — Uebersetzungs- und Beschreibungs-Regression.

Dieses Modul merged stattdessen FELDWEISE und VERLUSTFREI:

* Bestehende, nicht-leere i18n-Locale-Werte (de/en/fr/it/ls) gewinnen IMMER
  gegen leere/fehlende Werte aus der Extraktion — sie werden nie geleert.
* Bestehende description-/Freitext-Bloecke werden nie auf leer zurueckgesetzt.
* Nur fehlende Felder werden ergaenzt; neue Schritte/References hinzugefuegt.
* Gemerged wird ueber fachliche Schluessel (step_id, reference_id, actor.id),
  nicht ueber Array-Index — Reihenfolgeaenderungen zerstoeren nichts.
* Konfliktregel pro Feld: bestehender nicht-leerer Wert gewinnt; die Extraktion
  fuellt nur Luecken (leer/None/fehlend).

Laesst sich ein Fall nicht sauber mergen (kaputtes JSON, id-Mismatch, doppelte
fachliche Schluessel), wird `MergeConflict` geworfen — der Aufrufer ueberspringt
die Datei dann lieber, als sie zu verarmen.

Reine stdlib (kein pydantic), damit die Tests ohne Dependency-Install in der CI
laufen — wie `tests/test_grounding.py`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Locale-Keys des Datenvertrags. 'ls' = Leichte Sprache (kanonisch).
LOCALE_KEYS = ("de", "en", "fr", "it", "ls")
# Im tessera-Entwurf evtl. als 'leichte_sprache' gefuehrt -> auf 'ls' mappen.
LS_ALIAS = "leichte_sprache"

# i18n-/Freitext-Felder, die feldweise (pro Locale) gemerged werden.
PROCESS_I18N_FIELDS = ("title", "description")
STEP_I18N_FIELDS = ("label", "description")
REFERENCE_I18N_FIELDS = ("label",)
ACTOR_I18N_FIELDS = ("label",)


class MergeConflict(Exception):
    """Feldweises Mergen ist fuer diesen Fall nicht sauber moeglich.

    Der Aufrufer soll die Datei UEBERSPRINGEN (nicht verarmen) und das loggen.
    """


@dataclass
class MergeReport:
    """Was beim Merge erhalten (vor Verarmung geschuetzt) und ergaenzt wurde."""

    # Bestehende nicht-leere Werte, die gegen leere Extraktion geschuetzt wurden.
    preserved: list[str] = field(default_factory=list)
    # Vom Merge ergaenzte Luecken / neue Schritte / neue References.
    added: list[str] = field(default_factory=list)
    # Schritt-Actors, die (gender-neutral, exakt) auf eine bestehende
    # actors[].id abgebildet wurden, z.B. "Halter:in" -> "halter".
    remapped_actors: list[str] = field(default_factory=list)
    # Schritt-Actors, die sich KEINER actors[].id zuordnen lassen — geflaggt,
    # nicht geraten. Der Reviewer ergaenzt den fehlenden actors[]-Eintrag
    # (inkl. type) von Hand. Solange offen: kanonische CI wuerde scheitern.
    unmapped_actors: list[str] = field(default_factory=list)

    @property
    def touched_existing(self) -> bool:
        return bool(self.preserved or self.added or self.remapped_actors)


def _is_blank(value: object) -> bool:
    """Luecke = None, leerer/whitespace-String. Leere Listen/Dicts zaehlen NICHT
    als Luecke: ein leeres `depends_on` (Start-Schritt) ist bedeutungstragend."""
    if value is None:
        return True
    return isinstance(value, str) and not value.strip()


def normalize_i18n(obj: dict) -> dict:
    """i18n-Objekt der Extraktion fuer den Merge normalisieren.

    Bildet `leichte_sprache` auf `ls` ab. Aendert nichts an den Werten.
    """
    if not isinstance(obj, dict):
        return obj
    out = dict(obj)
    if LS_ALIAS in out:
        # 'ls' gewinnt, falls beide vorhanden und 'ls' nicht-leer; sonst Alias.
        alias_val = out.pop(LS_ALIAS)
        if _is_blank(out.get("ls")) and not _is_blank(alias_val):
            out["ls"] = alias_val
    return out


def merge_i18n(existing: dict, incoming: dict, *, path: str, report: MergeReport) -> dict:
    """Mergt zwei i18n-Objekte. Bestehender nicht-leerer Locale-Wert gewinnt;
    die Extraktion fuellt nur leere/fehlende Locales."""
    existing = normalize_i18n(existing) if isinstance(existing, dict) else {}
    incoming = normalize_i18n(incoming) if isinstance(incoming, dict) else {}
    out = dict(existing)

    for key in sorted({*existing.keys(), *incoming.keys(), *LOCALE_KEYS}):
        ex_val = existing.get(key)
        in_val = incoming.get(key)
        if not _is_blank(ex_val):
            # Bestehender Wert bleibt. Schutzfall: Extraktion wuerde leeren.
            out[key] = ex_val
            if _is_blank(in_val) and key in LOCALE_KEYS and key != "de":
                report.preserved.append(f"{path}.{key}")
        elif not _is_blank(in_val):
            out[key] = in_val
            report.added.append(f"{path}.{key}")
        elif key in existing:
            out[key] = ex_val  # leere Locale-Form erhalten (z.B. en: "")
    return out


def _merge_i18n_fields(
    existing: dict, incoming: dict, fields: tuple[str, ...], *, path: str, report: MergeReport
) -> dict:
    """Basis = bestehendes Objekt; i18n-Felder feldweise mergen, restliche
    Felder nur ergaenzen (Luecke fuellen, bestehend gewinnt)."""
    out = dict(existing)

    for f in fields:
        ex_has = isinstance(existing.get(f), dict)
        in_has = isinstance(incoming.get(f), dict)
        if ex_has and in_has:
            out[f] = merge_i18n(existing[f], incoming[f], path=f"{path}.{f}", report=report)
        elif in_has and not ex_has:
            out[f] = normalize_i18n(incoming[f])
            report.added.append(f"{path}.{f}")
        # nur bestehend vorhanden -> erhalten (steckt bereits in out)

    for key, in_val in incoming.items():
        if key in fields:
            continue
        if key not in out or _is_blank(out.get(key)):
            out[key] = in_val
            if key not in existing:
                report.added.append(f"{path}.{key}")
    return out


def _index_by(items: list, key: str, *, what: str) -> dict:
    """Liste nach fachlichem Schluessel indizieren; doppelte Schluessel sind ein
    Konflikt (Merge nicht eindeutig moeglich)."""
    out: dict = {}
    for item in items:
        if not isinstance(item, dict) or key not in item:
            raise MergeConflict(f"{what}: Eintrag ohne Schluessel {key!r}")
        k = item[key]
        if k in out:
            raise MergeConflict(f"{what}: doppelter Schluessel {key}={k!r}")
        out[k] = item
    return out


def _merge_keyed_list(
    existing_list: list,
    incoming_list: list,
    *,
    key: str,
    i18n_fields: tuple[str, ...],
    name: str,
    report: MergeReport,
) -> list:
    """Listen ueber fachlichen Schluessel mergen (stabil, index-unabhaengig).

    Reihenfolge der bestehenden Liste bleibt erhalten; neue Eintraege der
    Extraktion werden hinten angehaengt. Eintraege, die nur bestehen, bleiben.
    """
    existing_by_key = _index_by(existing_list, key, what=name)
    incoming_by_key = _index_by(incoming_list, key, what=f"{name} (Extraktion)")

    out: list = []
    for item in existing_list:
        k = item[key]
        if k in incoming_by_key:
            out.append(
                _merge_i18n_fields(
                    item, incoming_by_key[k], i18n_fields, path=f"{name}[{k}]", report=report
                )
            )
        else:
            out.append(item)  # nur bestehend -> erhalten

    for item in incoming_list:
        k = item[key]
        if k not in existing_by_key:
            out.append(item)
            report.added.append(f"{name}[{k}] (neu)")
    return out


def _merge_preconditions(existing_list: list, incoming_list: list, *, report: MergeReport) -> list:
    """preconditions haben keinen fachlichen Schluessel -> positionsweise i18n
    mergen (bestehend gewinnt), ueberzaehlige Extraktions-Eintraege anhaengen."""
    out: list = []
    for idx, ex in enumerate(existing_list):
        if idx < len(incoming_list) and isinstance(ex, dict) and isinstance(incoming_list[idx], dict):
            out.append(merge_i18n(ex, incoming_list[idx], path=f"preconditions[{idx}]", report=report))
        else:
            out.append(ex)
    for idx in range(len(existing_list), len(incoming_list)):
        out.append(incoming_list[idx])
        report.added.append(f"preconditions[{idx}] (neu)")
    return out


_GENDER_SUFFIX = re.compile(r"(?::|/|\*|_)innen?$|(?::|/|\*|_)in$", re.IGNORECASE)
# Umlaut-/ß-Transliteration: die kanonischen actors[].id sind ASCII (z.B.
# "fundbuero"), das LLM liefert die Originalschreibweise ("Fundbüro"). Ohne
# Transliteration faellt das 'ü' beim Strippen weg ("fundbro") und matcht die id
# nicht. Das ist Standard-CH-Deutsch-Aequivalenz (ue=ü), kein Fuzzy-Matching.
_UMLAUT_MAP = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def _norm_actor(value: object) -> str:
    """Konservative, gender-neutrale Normalform fuer den Actor-Abgleich.

    Entfernt Gender-Suffixe (:in, /in, *in, _in, :innen), transliteriert Umlaute
    (ü→ue, ä→ae, ö→oe, ß→ss) und wirft alles Nicht-Alphanumerische weg, lowercase.
    KEIN Fuzzy-Matching — nur exakte Gleichheit nach dieser Normalisierung gilt
    als Treffer ("Halter:in"/id "halter" → "halter"; "Fundbüro"/id "fundbuero" →
    "fundbuero"). Bleibt etwas ungleich, wird geflaggt.
    """
    if not isinstance(value, str):
        return ""
    s = _GENDER_SUFFIX.sub("", value.strip()).lower().translate(_UMLAUT_MAP)
    return re.sub(r"[^a-z0-9]", "", s)


def _reconcile_step_actors(out: dict, report: MergeReport) -> None:
    """Gleicht steps[].actor gegen actors[].id ab, wenn actors[] vorhanden ist.

    Das Ziel-Repo verlangt, dass jeder steps[].actor eine actors[].id ist.
    Die Extraktion liefert aber Freitext-Rollen ("Halter:in"). Hier werden
    nur EXAKTE Normalform-Treffer (id ODER label.de) automatisch auf die id
    umgeschrieben; alles andere wird geflaggt (unmapped_actors) — nie geraten,
    nie ein neuer actors[]-Eintrag mit geschaetztem type erfunden.
    """
    actors = out.get("actors")
    steps = out.get("steps")
    if not isinstance(actors, list) or not actors or not isinstance(steps, list):
        return

    actor_ids = {a["id"] for a in actors if isinstance(a, dict) and isinstance(a.get("id"), str)}

    # Normalform -> id. Mehrdeutige Normalformen (Kollision) werden ausgeschlossen,
    # damit nie auf den falschen Akteur gemappt wird.
    norm_to_id: dict[str, str] = {}
    ambiguous: set[str] = set()
    for a in actors:
        if not isinstance(a, dict) or not isinstance(a.get("id"), str):
            continue
        keys = {_norm_actor(a["id"])}
        label = a.get("label")
        if isinstance(label, dict) and isinstance(label.get("de"), str):
            keys.add(_norm_actor(label["de"]))
        for k in keys:
            if not k:
                continue
            if k in norm_to_id and norm_to_id[k] != a["id"]:
                ambiguous.add(k)
            norm_to_id[k] = a["id"]
    for k in ambiguous:
        norm_to_id.pop(k, None)

    for step in steps:
        if not isinstance(step, dict):
            continue
        actor = step.get("actor")
        if not isinstance(actor, str) or actor in actor_ids:
            continue  # bereits eine gueltige id
        mapped = norm_to_id.get(_norm_actor(actor))
        sid = step.get("step_id")
        if mapped is not None:
            step["actor"] = mapped
            report.remapped_actors.append(f"steps[{sid}].actor {actor!r} -> {mapped!r}")
        else:
            report.unmapped_actors.append(
                f"steps[{sid}].actor {actor!r} (kein actors[]-Eintrag — bitte Akteur ergaenzen)"
            )


def merge_process(existing: dict, incoming: dict) -> tuple[dict, MergeReport]:
    """Mergt die Extraktion (`incoming`) verlustfrei in die bestehende,
    handgepflegte Datei (`existing`). Bestehende Daten sind die Basis.

    Wirft `MergeConflict`, wenn kein sauberer Merge moeglich ist (kaputtes
    Objekt, id-Mismatch, doppelte fachliche Schluessel).
    """
    if not isinstance(existing, dict) or not isinstance(incoming, dict):
        raise MergeConflict("Prozess-Objekt ist kein JSON-Objekt")

    ex_id, in_id = existing.get("id"), incoming.get("id")
    if ex_id is not None and in_id is not None and ex_id != in_id:
        raise MergeConflict(f"id-Mismatch: bestehend {ex_id!r} != Extraktion {in_id!r}")

    report = MergeReport()
    out = dict(existing)  # Basis: alle handgepflegten (auch additiven) Felder bleiben.

    # Top-Level i18n/Freitext (title, description) feldweise mergen.
    out = _merge_i18n_fields(out, incoming, PROCESS_I18N_FIELDS, path="", report=report)
    # path="" erzeugt fuehrende Punkte -> aufraeumen.
    report.preserved = [p.lstrip(".") for p in report.preserved]
    report.added = [a.lstrip(".") for a in report.added]

    if "preconditions" in incoming or "preconditions" in existing:
        out["preconditions"] = _merge_preconditions(
            existing.get("preconditions", []), incoming.get("preconditions", []), report=report
        )

    if "steps" in incoming or "steps" in existing:
        out["steps"] = _merge_keyed_list(
            existing.get("steps", []),
            incoming.get("steps", []),
            key="step_id",
            i18n_fields=STEP_I18N_FIELDS,
            name="steps",
            report=report,
        )

    if "references" in incoming or "references" in existing:
        out["references"] = _merge_keyed_list(
            existing.get("references", []),
            incoming.get("references", []),
            key="reference_id",
            i18n_fields=REFERENCE_I18N_FIELDS,
            name="references",
            report=report,
        )

    if "actors" in incoming or "actors" in existing:
        out["actors"] = _merge_keyed_list(
            existing.get("actors", []),
            incoming.get("actors", []),
            key="id",
            i18n_fields=ACTOR_I18N_FIELDS,
            name="actors",
            report=report,
        )

    # Freitext-Actors der Extraktion gegen actors[].id abgleichen (gender-neutral,
    # exakt). Unbekannte werden geflaggt, nicht geraten.
    _reconcile_step_actors(out, report)

    return out, report
