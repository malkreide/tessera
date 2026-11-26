"""Abgleich der Extraktion gegen eine bestehende, handgepflegte Zieldatei.

Hintergrund: Fuer viele Leistungen gibt es im Ziel-Repo bereits einen von Hand
modellierten, menschlich reviewten Prozess. Er ist kanonisch. tessera
extrahiert unabhaengig davon; `step_id` und `reference_id` vergibt das Modell
bei jedem Lauf neu. Sie sind KEINE fachlichen Schluessel gegenueber der
Handdatei — ein Merge ueber diese Nummern fuellte Luecken im falschen Schritt,
haengte Schritte mit Kanten auf fremde Nummern an und verlinkte Belege falsch
(Merge-Probe hund-anmelden, kita-platz-Pilot: alle 14 ID-Paare fremd).

Darum gilt seit dem Pilot: **Abgleich statt Merge.** `sync_existing` aendert an
der Handdatei nur, was sich ohne ID-Zuordnung sicher sagen laesst:

* **References ueber den natuerlichen Schluessel** `(source_url ohne Fragment,
  normalisiertes source_quote)`. Hat die Extraktion dieselbe Stelle auf
  derselben Seite woertlich wiedergefunden, wird `retrieved_at` dieser
  Hand-Reference aufgefrischt. Sonst bleibt sie unangetastet. Der `status`
  wird nie geaendert — ein wiedergefundenes Zitat einer `unverifiziert`en
  Reference wird nur gemeldet; verifizieren tut ein Mensch.
* **Prozess-`retrieved_at`** wird aufgefrischt.
* Alles andere — `steps`, `actors`, `preconditions`, `title`, `description`,
  `meta` (inkl. `herkunft`) — bleibt unveraendert. Es werden keine Schritte
  und keine References angehaengt.

Was die Extraktion darueber hinaus findet, landet als **Vorschlag** im
`AbgleichReport` (und damit im PR-Body): ungepaarte Schritte, nicht
wiedergefundene Hand-Belege, neue Belegstellen. Uebernehmen tut sie ein
Mensch im Ziel-Repo. Liegt eine bestaetigte Paarung vor
(`reports/eval/<id>.pairs.yaml`), zeigt der Bericht die Zuordnung und listet
nur ungepaarte Schritte als Vorschlag — die Paarung ist Lesehilfe, kein Gate.

Reine stdlib (kein pydantic), damit die Tests ohne Dependency-Install in der CI
laufen — wie `tests/test_grounding.py`.
"""

from __future__ import annotations

import copy
import difflib
import re
from dataclasses import dataclass, field
from urllib.parse import urldefrag

from .contract import HERKUNFT_SEIT, major_minor
from .grounding import normalize


class MergeConflict(Exception):
    """Der Abgleich ist fuer diesen Fall nicht sauber moeglich (kein JSON-Objekt,
    id-Mismatch). Der Aufrufer soll die Datei UEBERSPRINGEN und das loggen."""


@dataclass
class AbgleichReport:
    """Was der Abgleich an der Handdatei geaendert hat und was er vorschlaegt."""

    # Provenienz-Felder (retrieved_at), die das frische Crawl-Datum ersetzt hat.
    refreshed: list[str] = field(default_factory=list)
    # Hand-References, deren Zitat die Extraktion auf derselben Seite
    # woertlich wiedergefunden hat (reference_id, label.de).
    refs_confirmed: list[tuple[object, str]] = field(default_factory=list)
    # Davon `unverifiziert` in der Handdatei — Status bleibt, Hinweis an Menschen.
    refs_confirmed_unverified: list[tuple[object, str]] = field(default_factory=list)
    # Hand-References mit Zitat, die die Extraktion NICHT wiedergefunden hat.
    refs_not_found: list[tuple[object, str]] = field(default_factory=list)
    # Hand-References ohne Zitat — nicht abgleichbar.
    refs_without_quote: list[tuple[object, str]] = field(default_factory=list)
    # Belegstellen der Extraktion, die keiner Hand-Reference entsprechen.
    ref_proposals: list[dict] = field(default_factory=list)
    # Bestaetigte Paarung: (Extraktion [(id, label)], Hand [(id, label)]).
    step_pairs: list[tuple[list[tuple[object, str]], list[tuple[object, str]]]] = field(default_factory=list)
    # Schritte der Extraktion ohne Partner (ohne Paarung: alle), lesbar
    # aufbereitet: step_id, label, actor, type, vorgaenger (Labels), belege (Labels).
    step_proposals: list[dict] = field(default_factory=list)
    # Hinweis zur Paarung (verwendet, nur Vorschlag, veraltet, fehlt).
    pairing_note: str = ""
    # Weicht der eingereichte Stand von der Handdatei ab? Ohne Aenderung kein PR.
    changed: bool = False


# Unter dieser Label-Aehnlichkeit paart die Heuristik in `evaluate` nicht.
LABEL_SIMILARITY_MIN = 0.5


def _norm_label(value: object) -> str:
    """Vergleichs-Normalform fuer Labels: lowercase, Umlaut-Transliteration,
    alles Nicht-Alphanumerische zu Leerzeichen (kein inhaltlicher Eingriff)."""
    if not isinstance(value, str):
        return ""
    s = value.lower().translate(_UMLAUT_MAP)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _label_similarity(a: str, b: str) -> float:
    """Aehnlichkeit zweier Labels in [0, 1].

    Maximum aus Zeichen-Aehnlichkeit (difflib) und Token-Ueberdeckung relativ
    zum kuerzeren Label — Letzteres, damit «Hund anmelden» vs. «Hund online
    oder am Schalter anmelden» (gleicher Schritt, laenger formuliert) nicht
    faelschlich verdaechtig wird. Leere Labels sind nicht beurteilbar -> 1.0
    (kein Verdacht; das Gate soll nur klar Fremdes stoppen).
    """
    na, nb = _norm_label(a), _norm_label(b)
    if not na or not nb:
        return 1.0
    seq = difflib.SequenceMatcher(None, na, nb).ratio()
    ta, tb = set(na.split()), set(nb.split())
    tok = len(ta & tb) / min(len(ta), len(tb))
    return max(seq, tok)


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


def _label_de(item: object) -> str:
    label = item.get("label") if isinstance(item, dict) else None
    de = label.get("de") if isinstance(label, dict) else None
    return de if isinstance(de, str) else ""


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def ref_key(ref: object) -> tuple[str, str] | None:
    """Natuerlicher Schluessel einer Reference: (Seite, Zitat).

    Die Seite ohne Fragment und Trailing-Slash (Hand-References tragen oft einen
    Deep-Link mit #Anker, die Extraktion die gecrawlte Seite), das Zitat in der
    Normalform des Grounding-Gates. None ohne URL oder Zitat — dann gibt es
    nichts Belastbares zu vergleichen.
    """
    if not isinstance(ref, dict):
        return None
    url, quote = ref.get("source_url"), ref.get("source_quote")
    if not isinstance(url, str) or not isinstance(quote, str):
        return None
    page = urldefrag(url.strip())[0].rstrip("/")
    q = normalize(quote)
    if not page or not q:
        return None
    return page, q


def _dep_id(dep: object) -> object:
    return dep.get("step_id") if isinstance(dep, dict) else dep


def _step_proposal(step: dict, ext_labels: dict, ext_ref_labels: dict) -> dict:
    return {
        "step_id": step.get("step_id"),
        "label": _label_de(step),
        "actor": step.get("actor") if isinstance(step.get("actor"), str) else "",
        "type": step.get("type") if isinstance(step.get("type"), str) else "",
        "vorgaenger": [ext_labels.get(_dep_id(d), f"#{_dep_id(d)}") for d in step.get("depends_on") or []],
        "belege": [ext_ref_labels.get(r, f"#{r}") for r in step.get("reference_ids") or []],
    }


def sync_existing(
    existing: dict,
    incoming: dict,
    *,
    pairing: list[tuple[list, list]] | None = None,
    pairing_note: str = "",
) -> tuple[dict, AbgleichReport]:
    """Gleicht die Extraktion (`incoming`) gegen die Handdatei (`existing`) ab.

    Rueckgabe: (einzureichender Stand, Bericht). Der Stand ist eine Kopie der
    Handdatei, in der nur `retrieved_at` (Prozess und wiedergefundene
    References) aufgefrischt ist. `pairing` sind die Gruppen einer bestaetigten,
    aktuellen Paarungsdatei als (Extraktion-IDs, Hand-IDs); ohne sie gelten
    alle Extraktionsschritte als Vorschlag. Eingaben werden nicht mutiert.

    Wirft `MergeConflict` bei kaputtem Objekt oder id-Mismatch.
    """
    if not isinstance(existing, dict) or not isinstance(incoming, dict):
        raise MergeConflict("Prozess-Objekt ist kein JSON-Objekt")
    ex_id, in_id = existing.get("id"), incoming.get("id")
    if ex_id is not None and in_id is not None and ex_id != in_id:
        raise MergeConflict(f"id-Mismatch: bestehend {ex_id!r} != Extraktion {in_id!r}")

    report = AbgleichReport(pairing_note=pairing_note)
    out = copy.deepcopy(existing)

    in_date = incoming.get("retrieved_at")
    if not _blank(in_date) and out.get("retrieved_at") != in_date:
        if not _blank(out.get("retrieved_at")):
            report.refreshed.append("retrieved_at")
        out["retrieved_at"] = in_date

    # --- References ueber (Seite, Zitat) ---------------------------------------
    in_refs = [r for r in incoming.get("references") or [] if isinstance(r, dict)]
    in_by_key: dict[tuple[str, str], dict] = {}
    for r in in_refs:
        k = ref_key(r)
        if k is not None:
            in_by_key.setdefault(k, r)
    matched_keys: set[tuple[str, str]] = set()
    for r in out.get("references") or []:
        if not isinstance(r, dict):
            continue
        entry = (r.get("reference_id"), _label_de(r))
        k = ref_key(r)
        if k is None:
            report.refs_without_quote.append(entry)
            continue
        hit = in_by_key.get(k)
        if hit is None:
            report.refs_not_found.append(entry)
            continue
        matched_keys.add(k)
        report.refs_confirmed.append(entry)
        if r.get("status") == "unverifiziert":
            report.refs_confirmed_unverified.append(entry)
        new_date = hit.get("retrieved_at")
        if not _blank(new_date) and r.get("retrieved_at") != new_date:
            report.refreshed.append(f"references[{r.get('reference_id')}].retrieved_at")
            r["retrieved_at"] = new_date
    report.ref_proposals = [r for r in in_refs if ref_key(r) not in matched_keys]

    # --- Schritte: nie eingespielt, nur Paarung zeigen und Rest vorschlagen -----
    in_steps = [s for s in incoming.get("steps") or [] if isinstance(s, dict)]
    ext_labels = {s.get("step_id"): _label_de(s) for s in in_steps}
    ext_ref_labels = {r.get("reference_id"): _label_de(r) for r in in_refs}
    hand_labels = {s.get("step_id"): _label_de(s) for s in existing.get("steps") or [] if isinstance(s, dict)}
    paired: set[object] = set()
    for ext_ids, can_ids in pairing or []:
        if ext_ids and can_ids:
            report.step_pairs.append(
                (
                    [(i, ext_labels.get(i, "")) for i in ext_ids],
                    [(i, hand_labels.get(i, "")) for i in can_ids],
                )
            )
            paired.update(ext_ids)
    report.step_proposals = [
        _step_proposal(s, ext_labels, ext_ref_labels) for s in in_steps if s.get("step_id") not in paired
    ]

    report.changed = out != existing
    return out, report


# --- Herkunft (nur fuer NEUE Dateien) ----------------------------------------


def apply_herkunft(process: dict, pr_number: int, *, neu: bool) -> tuple[dict, str | None]:
    """Traegt die eigene PR-Nummer in meta.herkunft ein (Vertrag 0.2.0).

    Laeuft NACH dem Oeffnen des PRs (erst dann steht die Nummer fest) und
    liefert den Stand fuer den Folge-Commit. Regeln (docs/data-contract.md):

    * neue Datei (`neu`): art 'tessera', tessera_prs [pr_number];
    * bestehende Datei: 'redaktion' -> 'gemischt'; 'gemischt'/'tessera'
      bleiben; die Nummer kommt sortiert und ohne Dublette dazu;
    * geprueft_am setzt nur ein Mensch — wird nie gesetzt oder geaendert;
    * traegt die bestehende Datei KEINE Herkunft, wird nichts geraten: der
      Stand bleibt unveraendert, der Hinweis (zweiter Rueckgabewert) geht an
      den Reviewer.

    Die Eingabe wird nicht mutiert. Wer herkunft setzt, deklariert mindestens
    Vertrag 0.2.0 — eine aeltere schema_version wird deshalb angehoben.

    `pr.open_draft_pr` ruft das seit dem Abgleich (`sync_existing`) nur noch
    fuer NEUE Dateien auf: ein Abgleich-PR aendert keine Inhalte und laesst
    meta.herkunft unveraendert. Der Zweig fuer bestehende Dateien bleibt fuer
    Werkzeuge und Tests erhalten.
    """
    alt = (process.get("meta") or {}).get("herkunft")
    if not neu and not isinstance(alt, dict):
        return process, (
            "meta.herkunft der Zieldatei fehlt — nicht geraten. Bitte im Review "
            f"nachtragen (vermutlich 'gemischt' mit PR #{pr_number})."
        )
    out = copy.deepcopy(process)
    meta = out.setdefault("meta", {})
    if isinstance(alt, dict):
        h = copy.deepcopy(alt)
        if h.get("art") == "redaktion":
            h["art"] = "gemischt"
    else:
        h = {"art": "tessera"}
    prs = [n for n in h.get("tessera_prs", []) if isinstance(n, int)]
    h["tessera_prs"] = sorted({*prs, pr_number})
    meta["herkunft"] = h
    mm = major_minor(str(out.get("schema_version", "")))
    if mm is None or (mm[0] == 0 and mm < HERKUNFT_SEIT):
        out["schema_version"] = f"{HERKUNFT_SEIT[0]}.{HERKUNFT_SEIT[1]}.0"
    return out, None
