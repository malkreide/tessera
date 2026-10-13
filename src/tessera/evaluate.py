"""Bewertung: Extraktion gegen die handmodellierte Zieldatei messen. Nur stdlib.

Die von Hand modellierten, menschlich reviewten Prozesse in `maschinerie-zuerich`
sind ein fertiger Massstab. Statt zu vermuten, wie gut die Extraktion ist, misst
`tessera eval` sie dagegen — ohne PR, ohne Schreibzugriff auf out/:

* **Schritte:** Paarung zu GRUPPEN (n Extraktionsschritte <-> m Handschritte).
  Liegt eine von Hand gepflegte Paarungsdatei vor (`reports/eval/<id>.pairs.yaml`,
  siehe `parse_pairing`), gilt ausschliesslich sie. Sonst eine Heuristik ueber die
  Label-Aehnlichkeit (dieselbe Metrik wie der Label-Guard beim Merge,
  `merge._label_similarity`), greedy, 1:1. Die Heuristik paart nach Wortueberlappung
  und liegt bei unterschiedlich feiner Zerlegung oft daneben (fundsache-Pilot) —
  belastbare Zahlen gibt es nur mit der Paarungsdatei. Daraus Recall (Anteil der
  Handschritte mit Entsprechung) und Precision (Anteil der Extraktionsschritte mit
  Entsprechung). Ungepaarte Handschritte sind Kandidaten fuer FEHLENDE Schritte —
  genau die Luecke, die das Grounding-Gate nicht als Fehler sieht.
* **Kanten:** nur zwischen gepaarten Gruppen vergleichbar (Kanten innerhalb einer
  Gruppe zaehlen nicht). Eine extrahierte Kante ist «exakt», wenn die Handdatei
  zwischen den beiden Gruppen eine direkte Kante fuehrt; «Abkuerzung», wenn sie
  einen Pfad in derselben Richtung fuehrt (Zwischenschritt fehlt); «umgekehrt»,
  wenn sie einen Pfad in Gegenrichtung fuehrt (falsche Reihenfolge); sonst
  «unbelegt».
* **References** (gepaart wie Schritte) und **Akteure** (gegen `actors[]` der
  Handdatei, Normalform wie beim Merge). Namen aus der Quelle, die weder ID noch
  Label eines `actors[]`-Eintrags treffen («Schul- und Sportdepartement» vs.
  `schulamt`), ordnet der optionale Abschnitt `akteure:` der Paarungsdatei zu
  (siehe `parse_actor_map`) — ausdruecklich, nicht per Wortaehnlichkeit geraten.
* **Gate-Ausfall** aus der Flags-Datei: verworfene Schritte / extrahierte Schritte.
* **Strenger Kardinalregel-Lint** auf BEIDEN Dateien: Treffer in der Handdatei
  sind die Fehlalarm-Basis (menschlich reviewter Text, der trotzdem anschlaegt).

Die Paarung ist eine Heuristik und wird darum vollstaendig im Report
ausgewiesen (jedes Paar mit Aehnlichkeit) — der Mensch sieht, worauf die Zahlen
beruhen. `evaluate` ist rein (kein Netz, keine Datei); Laden und Schreiben
macht die CLI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .binding import BINDING_VALUE_STRICT
from .grounding import BRIDGE_FLAG_PREFIX
from .merge import LABEL_SIMILARITY_MIN, _label_similarity, _norm_actor
from .plausibility import ACTOR_FLAG_PREFIX, ORDER_FLAG_PREFIX

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "eval"


@dataclass
class Pair:
    ext_id: object
    can_id: object
    ext_label: str
    can_label: str
    similarity: float


@dataclass
class Group:
    """n Extraktionsschritte <-> m Handschritte. Eine Seite darf leer sein (nur in
    der Paarungsdatei): dann ist der Schritt bewusst ohne Entsprechung erfasst."""

    ext: list[tuple[object, str]]  # (step_id, label)
    can: list[tuple[object, str]]
    similarity: float | None = None  # nur Heuristik
    note: str = ""
    not_groundable: bool = False  # Handschritt, den die Quelle nicht woertlich nennt

    @property
    def matched(self) -> bool:
        return bool(self.ext) and bool(self.can)


class PairingError(ValueError):
    """Paarungsdatei ungueltig oder veraltet; `problems` listet jeden Befund."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


PAIRING_STATUS = ("vorschlag", "bestaetigt")


@dataclass
class EvalReport:
    proc_id: str
    threshold: float
    step_groups: list[Group] = field(default_factory=list)
    pairing_source: str = ""  # leer = Heuristik, sonst Pfad der Paarungsdatei
    pairing_status: str = ""
    ext_steps: int = 0
    can_steps: int = 0
    missing_steps: list[str] = field(default_factory=list)  # Handdatei, ungepaart
    extra_steps: list[str] = field(default_factory=list)  # Extraktion, ungepaart
    edges_exact: list[str] = field(default_factory=list)
    edges_shortcut: list[str] = field(default_factory=list)
    edges_reversed: list[str] = field(default_factory=list)
    edges_unsupported: list[str] = field(default_factory=list)
    edges_missed: list[str] = field(default_factory=list)  # Handkante, nicht extrahiert
    ref_pairs: list[Pair] = field(default_factory=list)
    ext_refs: int = 0
    can_refs: int = 0
    refs_url_differs: list[str] = field(default_factory=list)
    refs_unverified: int = 0
    actors_checked: bool = False
    actors_unmapped: list[str] = field(default_factory=list)
    actors_declared_none: list[str] = field(default_factory=list)  # akteure: Name: null
    actors_mismatch: list[str] = field(default_factory=list)
    actors_available: list[str] = field(default_factory=list)  # «id» (Label) der Handdatei
    dropped_steps: int = 0
    flag_counts: dict[str, int] = field(default_factory=dict)
    strict_hits_ext: list[str] = field(default_factory=list)
    strict_hits_can: list[str] = field(default_factory=list)

    @property
    def can_matched(self) -> int:
        return sum(len(g.can) for g in self.step_groups if g.matched)

    @property
    def ext_matched(self) -> int:
        return sum(len(g.ext) for g in self.step_groups if g.matched)

    @property
    def can_not_groundable(self) -> int:
        return sum(len(g.can) for g in self.step_groups if g.not_groundable)

    @property
    def step_recall(self) -> float | None:
        return self.can_matched / self.can_steps if self.can_steps else None

    @property
    def step_recall_groundable(self) -> float | None:
        """Recall ohne Handschritte, die als nicht belegbar markiert sind
        (Start-/Entscheidungs-/Endknoten): None, wenn keiner markiert ist."""
        n = self.can_steps - self.can_not_groundable
        return self.can_matched / n if self.can_not_groundable and n else None

    @property
    def step_precision(self) -> float | None:
        return self.ext_matched / self.ext_steps if self.ext_steps else None

    @property
    def gate_dropout(self) -> float | None:
        total = self.ext_steps + self.dropped_steps
        return self.dropped_steps / total if total else None

    @property
    def edges_compared(self) -> int:
        return (
            len(self.edges_exact)
            + len(self.edges_shortcut)
            + len(self.edges_reversed)
            + len(self.edges_unsupported)
        )


def _label(item: dict) -> str:
    label = item.get("label") if isinstance(item, dict) else None
    de = label.get("de") if isinstance(label, dict) else None
    return de.strip() if isinstance(de, str) else ""


def _dep_id(dep) -> object:
    return dep.get("step_id") if isinstance(dep, dict) else dep


def pair_by_label(ext: list[dict], can: list[dict], key: str, threshold: float) -> list[Pair]:
    """Greedy-Paarung nach absteigender Label-Aehnlichkeit; jede Seite einmal.
    Leere Labels werden nie gepaart (die Metrik waere dort bedeutungslos 1.0)."""
    candidates = []
    for e in ext:
        el = _label(e)
        if not el:
            continue
        for c in can:
            cl = _label(c)
            if not cl:
                continue
            sim = _label_similarity(el, cl)
            if sim >= threshold:
                candidates.append((sim, e.get(key), c.get(key), el, cl))
    # Stabil: hoechste Aehnlichkeit zuerst, bei Gleichstand Reihenfolge der ids.
    candidates.sort(key=lambda t: (-t[0], str(t[1]), str(t[2])))
    used_e: set = set()
    used_c: set = set()
    pairs: list[Pair] = []
    for sim, eid, cid, el, cl in candidates:
        if eid in used_e or cid in used_c:
            continue
        used_e.add(eid)
        used_c.add(cid)
        pairs.append(Pair(eid, cid, el, cl, round(sim, 2)))
    return pairs


def _id_label_map(raw: object, side: str, where: str, problems: list[str]) -> dict[int, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        problems.append(f'{where}.{side}: erwartet `schritt_id: "Label"`-Paare, nicht {type(raw).__name__}')
        return {}
    out: dict[int, str] = {}
    for key, label in raw.items():
        try:
            sid = int(key)
        except (TypeError, ValueError):
            problems.append(f"{where}.{side}: Schritt-ID {key!r} ist keine Zahl")
            continue
        if not isinstance(label, str):
            problems.append(f"{where}.{side}[{sid}]: Label fehlt (als Text angeben)")
            continue
        out[sid] = label.strip()
    return out


def parse_pairing(data: object, extracted: dict, canonical: dict) -> tuple[list[Group], str]:
    """Prueft eine Paarungsdatei (bereits als YAML geladen) gegen die aktuellen
    Dateien und gibt (Gruppen, Status) zurueck. Rein; wirft PairingError mit ALLEN
    Befunden statt still zu raten.

    Format::

        leistung: fundsache
        status: vorschlag          # oder: bestaetigt
        gruppen:
          - extraktion: {1: "Label", 2: "Label"}
            hand: {3: "Label"}
            notiz: "Abgabekanaele einzeln extrahiert"
          - extraktion: {}
            hand: {2: "Gefunden oder verloren?"}
            nicht_belegbar: true    # Modellierungsknoten ohne woertliche Quelle
            notiz: "Entscheidung"

    Regeln: jede Schritt-ID beider Dateien kommt GENAU EINMAL vor (vollstaendig,
    ohne Doppel); jedes Label muss dem aktuellen `label.de` entsprechen — sonst ist
    die Datei veraltet (z.B. nach einer neuen Extraktion) und muss nachgefuehrt
    werden; `nicht_belegbar` nur bei Gruppen ohne Extraktionsschritte.
    """
    problems: list[str] = []
    if not isinstance(data, dict):
        raise PairingError(["Datei enthaelt kein YAML-Mapping"])
    proc_id = str(extracted.get("id") or canonical.get("id") or "")
    if str(data.get("leistung") or "") != proc_id:
        problems.append(f"leistung: {data.get('leistung')!r} passt nicht zu {proc_id!r}")
    status = data.get("status")
    if status not in PAIRING_STATUS:
        problems.append(f"status: {status!r} — erlaubt: {', '.join(PAIRING_STATUS)}")
    raw_groups = data.get("gruppen")
    if not isinstance(raw_groups, list) or not raw_groups:
        problems.append("gruppen: fehlt oder leer")
        raw_groups = []

    sides = {
        "extraktion": {
            s.get("step_id"): _label(s) for s in extracted.get("steps") or [] if isinstance(s, dict)
        },
        "hand": {s.get("step_id"): _label(s) for s in canonical.get("steps") or [] if isinstance(s, dict)},
    }
    seen: dict[str, dict[int, str]] = {"extraktion": {}, "hand": {}}
    groups: list[Group] = []
    for i, raw in enumerate(raw_groups, start=1):
        where = f"gruppen[{i}]"
        if not isinstance(raw, dict):
            problems.append(f"{where}: kein Mapping")
            continue
        unknown = set(raw) - {"extraktion", "hand", "notiz", "nicht_belegbar"}
        if unknown:
            problems.append(f"{where}: unbekannte Felder {sorted(unknown)}")
        maps = {side: _id_label_map(raw.get(side), side, where, problems) for side in ("extraktion", "hand")}
        if not maps["extraktion"] and not maps["hand"]:
            problems.append(f"{where}: beide Seiten leer")
        for side, mapping in maps.items():
            current = sides[side]
            for sid, label in mapping.items():
                if sid not in current:
                    problems.append(f"{where}.{side}: Schritt {sid} gibt es nicht")
                elif label != current[sid]:
                    problems.append(
                        f"{where}.{side}[{sid}]: Label «{label}» weicht vom aktuellen «{current[sid]}» ab "
                        "(Datei veraltet?)"
                    )
                if sid in seen[side]:
                    problems.append(f"{where}.{side}: Schritt {sid} schon in {seen[side][sid]}")
                else:
                    seen[side][sid] = where
        not_groundable = raw.get("nicht_belegbar", False)
        if not isinstance(not_groundable, bool):
            problems.append(f"{where}.nicht_belegbar: true oder false")
            not_groundable = False
        if not_groundable and maps["extraktion"]:
            problems.append(f"{where}.nicht_belegbar: nur fuer Gruppen ohne Extraktionsschritte")
        note = raw.get("notiz", "")
        if not isinstance(note, str):
            problems.append(f"{where}.notiz: als Text angeben")
            note = ""
        groups.append(
            Group(
                ext=sorted(maps["extraktion"].items()),
                can=sorted(maps["hand"].items()),
                note=note.strip(),
                not_groundable=bool(not_groundable),
            )
        )
    for side, current in sides.items():
        missing = [sid for sid in current if sid not in seen[side]]
        if missing:
            problems.append(f"{side}: Schritt(e) {missing} fehlen in der Paarungsdatei")
    if problems:
        raise PairingError(problems)
    return groups, str(status)


def _actor_index(canonical: dict) -> tuple[list[dict], dict[str, str]]:
    """actors[] der Handdatei und Normalform (ID und Label) -> ID."""
    actors = [
        a for a in canonical.get("actors") or [] if isinstance(a, dict) and isinstance(a.get("id"), str)
    ]
    norm_to_id: dict[str, str] = {}
    for a in actors:
        norm_to_id.setdefault(_norm_actor(a["id"]), a["id"])
        norm_to_id.setdefault(_norm_actor(_label(a)), a["id"])
    norm_to_id.pop("", None)
    return actors, norm_to_id


def _ext_actor_names(extracted: dict) -> list[str]:
    names: list[str] = []
    for s in extracted.get("steps") or []:
        actor = s.get("actor") if isinstance(s, dict) else None
        if isinstance(actor, str) and actor.strip() and actor.strip() not in names:
            names.append(actor.strip())
    return names


def parse_actor_map(data: object, extracted: dict, canonical: dict) -> dict[str, str | None]:
    """Optionaler Abschnitt `akteure:` einer Paarungsdatei (rein; wirft PairingError).

    Format: `extrahierter Name: actors[]-ID` (Zuordnung), `: null` (bewusst ohne
    Entsprechung, z.B. eine Website als «Akteur») oder `: ""` (noch offen — zaehlt
    wie nicht zugeordnet). Schluessel werden in der Akteur-Normalform verglichen.
    Ein Name, der in der Extraktion nicht vorkommt, macht die Datei veraltet; eine
    ID, die die Handdatei nicht fuehrt, ist ein Fehler. Rueckgabe: Normalform ->
    ID | None; offene Eintraege fehlen.
    """
    raw = data.get("akteure") if isinstance(data, dict) else None
    if raw is None:
        return {}
    problems: list[str] = []
    if not isinstance(raw, dict):
        raise PairingError(["akteure: erwartet `Name: actors[]-ID`-Paare"])
    actors, _ = _actor_index(canonical)
    if not actors:
        raise PairingError(["akteure: die Handdatei fuehrt keine actors[] — Abschnitt entfernen"])
    ids = {a["id"] for a in actors}
    present = {_norm_actor(n) for n in _ext_actor_names(extracted)}
    out: dict[str, str | None] = {}
    for name, target in raw.items():
        key = _norm_actor(str(name))
        if key not in present:
            problems.append(f"akteure: «{name}» kommt in der Extraktion nicht vor (Datei veraltet?)")
            continue
        if target is None:
            out[key] = None
        elif isinstance(target, str) and not target.strip():
            continue  # offen
        elif isinstance(target, str) and target.strip() in ids:
            out[key] = target.strip()
        else:
            problems.append(
                f"akteure: «{name}» -> {target!r} ist keine actors[]-ID ({', '.join(sorted(ids))})"
            )
    if problems:
        raise PairingError(problems)
    return out


def propose_pairing(extracted: dict, canonical: dict, threshold: float = LABEL_SIMILARITY_MIN) -> dict:
    """Vorschlag fuer eine Paarungsdatei aus der Heuristik (rein): jedes
    Heuristik-Paar als Gruppe, jeder ungepaarte Schritt als einseitige Gruppe.
    Der Mensch korrigiert ihn; `status` bleibt `vorschlag`."""
    ext = [s for s in extracted.get("steps") or [] if isinstance(s, dict)]
    can = [s for s in canonical.get("steps") or [] if isinstance(s, dict)]
    pairs = pair_by_label(ext, can, "step_id", threshold)
    paired_e = {p.ext_id for p in pairs}
    paired_c = {p.can_id for p in pairs}
    groups: list[dict] = [
        {
            "extraktion": {p.ext_id: p.ext_label},
            "hand": {p.can_id: p.can_label},
            "notiz": f"Heuristik (Aehnlichkeit {p.similarity}) — pruefen",
        }
        for p in pairs
    ]
    groups += [
        {"extraktion": {s.get("step_id"): _label(s)}, "hand": {}, "notiz": "ohne Entsprechung — pruefen"}
        for s in ext
        if s.get("step_id") not in paired_e
    ]
    groups += [
        {"extraktion": {}, "hand": {s.get("step_id"): _label(s)}, "notiz": "ohne Entsprechung — pruefen"}
        for s in can
        if s.get("step_id") not in paired_c
    ]
    proc_id = str(extracted.get("id") or canonical.get("id") or "")
    proposal: dict = {"leistung": proc_id, "status": "vorschlag", "gruppen": groups}
    actors, norm_to_id = _actor_index(canonical)
    open_names = [n for n in _ext_actor_names(extracted) if _norm_actor(n) not in norm_to_id]
    if actors and open_names:
        proposal["akteure"] = {n: "" for n in open_names}  # offen: ID, null oder leer lassen
    return proposal


def _edges(steps: list[dict]) -> set[tuple]:
    out: set[tuple] = set()
    for s in steps:
        for d in s.get("depends_on", []) or []:
            out.add((_dep_id(d), s.get("step_id")))
    return out


def _reachable(edges: set[tuple]) -> dict:
    """Transitive Huelle: Knoten -> Menge der von ihm aus erreichbaren Knoten."""
    succ: dict = {}
    for a, b in edges:
        succ.setdefault(a, set()).add(b)
    reach: dict = {}

    def visit(n, seen: frozenset) -> set:
        if n in reach:
            return reach[n]
        out: set = set()
        for m in succ.get(n, ()):
            if m in seen:
                continue  # Zyklus-Schutz (Handdatei sollte ein DAG sein)
            out.add(m)
            out |= visit(m, seen | {m})
        reach[n] = out
        return out

    for node in list(succ):
        visit(node, frozenset({node}))
    return reach


def _rendered_texts(process: dict):
    """(Fundstelle, Text) fuer alle gerenderten i18n-Texte — dieselben Felder,
    die der Vertrags-Validator auf die Kardinalregel lintet."""

    def i18n(where: str, obj: object):
        if isinstance(obj, dict):
            for loc, text in obj.items():
                if isinstance(text, str) and text.strip():
                    yield f"{where}.{loc}", text

    yield from i18n("title", process.get("title"))
    yield from i18n("description", process.get("description"))
    for i, p in enumerate(process.get("preconditions") or []):
        yield from i18n(f"preconditions[{i}]", p)
    for s in process.get("steps") or []:
        if not isinstance(s, dict):
            continue
        sid = s.get("step_id")
        yield from i18n(f"steps[{sid}].label", s.get("label"))
        yield from i18n(f"steps[{sid}].description", s.get("description"))
        for d in s.get("depends_on") or []:
            if isinstance(d, dict):
                yield from i18n(f"steps[{sid}].depends_on[{d.get('step_id')}].condition", d.get("condition"))
        for j, doc in enumerate(s.get("documents") or []):
            if isinstance(doc, dict):
                yield from i18n(f"steps[{sid}].documents[{j}].label", doc.get("label"))
    for r in process.get("references") or []:
        if isinstance(r, dict):
            yield from i18n(f"references[{r.get('reference_id')}].label", r.get("label"))


def _strict_hits(process: dict) -> list[str]:
    hits = []
    for where, text in _rendered_texts(process):
        m = BINDING_VALUE_STRICT.search(text)
        if m:
            hits.append(f"{where}: {m.group(0)!r}")
    return hits


def evaluate(
    extracted: dict,
    canonical: dict,
    flags: list[str] | None = None,
    *,
    threshold: float = LABEL_SIMILARITY_MIN,
    pairing: object = None,
    pairing_source: str = "",
) -> EvalReport:
    """Misst `extracted` (out/<id>.json) gegen `canonical` (Handdatei). Rein.

    `pairing` ist der geladene Inhalt einer Paarungsdatei (siehe `parse_pairing`);
    None = Heuristik. Eine ungueltige Datei wirft PairingError."""
    flags = list(flags or [])
    ext_steps = [s for s in extracted.get("steps") or [] if isinstance(s, dict)]
    can_steps = [s for s in canonical.get("steps") or [] if isinstance(s, dict)]
    rep = EvalReport(
        proc_id=str(extracted.get("id") or canonical.get("id") or "?"),
        threshold=threshold,
        ext_steps=len(ext_steps),
        can_steps=len(can_steps),
    )

    # --- Schritte -----------------------------------------------------------
    if pairing is not None:
        rep.step_groups, rep.pairing_status = parse_pairing(pairing, extracted, canonical)
        rep.pairing_source = pairing_source or "Paarungsdatei"
    else:
        rep.step_groups = [
            Group([(p.ext_id, p.ext_label)], [(p.can_id, p.can_label)], similarity=p.similarity)
            for p in pair_by_label(ext_steps, can_steps, "step_id", threshold)
        ]
    matched = [g for g in rep.step_groups if g.matched]
    group_of_ext = {sid: i for i, g in enumerate(matched) for sid, _ in g.ext}
    group_of_can = {sid: i for i, g in enumerate(matched) for sid, _ in g.can}
    notes = {
        (side, sid): g
        for g in rep.step_groups
        if not g.matched
        for side, members in (("ext", g.ext), ("can", g.can))
        for sid, _ in members
    }

    def unmatched(side: str, steps: list[dict], grouped: dict) -> list[str]:
        out = []
        for s in steps:
            sid = s.get("step_id")
            if sid in grouped:
                continue
            line = f"{sid} «{_label(s)}»"
            g = notes.get((side, sid))
            if g is not None and g.not_groundable:
                line += " (nicht belegbar)"
            if g is not None and g.note:
                line += f" — {g.note}"
            out.append(line)
        return out

    rep.missing_steps = unmatched("can", can_steps, group_of_can)
    rep.extra_steps = unmatched("ext", ext_steps, group_of_ext)

    # --- Kanten (nur zwischen gepaarten Gruppen vergleichbar) -----------------
    can_edges = _edges(can_steps)
    can_reach = _reachable(can_edges)

    def gdesc(gi: int) -> tuple[str, str]:
        can = matched[gi].can
        return "+".join(str(sid) for sid, _ in can), " + ".join(f"«{lab}»" for _, lab in can)

    def edge_desc(ga: int, gb: int) -> str:
        (ia, la), (ib, lb) = gdesc(ga), gdesc(gb)
        return f"{ia} -> {ib} ({la} -> {lb})"

    def group_edges(edges: set[tuple], group_of: dict) -> set[tuple]:
        return {
            (group_of[a], group_of[b])
            for a, b in edges
            if a in group_of and b in group_of and group_of[a] != group_of[b]
        }

    can_group_edges = group_edges(can_edges, group_of_can)
    ext_group_edges = group_edges(_edges(ext_steps), group_of_ext)
    for ga, gb in sorted(ext_group_edges):
        ca_ids = [sid for sid, _ in matched[ga].can]
        cb_ids = [sid for sid, _ in matched[gb].can]
        desc = edge_desc(ga, gb)
        if (ga, gb) in can_group_edges:
            rep.edges_exact.append(desc)
        elif any(cb in can_reach.get(ca, ()) for ca in ca_ids for cb in cb_ids):
            rep.edges_shortcut.append(desc)
        elif any(ca in can_reach.get(cb, ()) for ca in ca_ids for cb in cb_ids):
            rep.edges_reversed.append(desc)
        else:
            rep.edges_unsupported.append(desc)
    for ga, gb in sorted(can_group_edges - ext_group_edges):
        rep.edges_missed.append(edge_desc(ga, gb))

    # --- References ---------------------------------------------------------
    ext_refs = [r for r in extracted.get("references") or [] if isinstance(r, dict)]
    can_refs = [r for r in canonical.get("references") or [] if isinstance(r, dict)]
    rep.ext_refs, rep.can_refs = len(ext_refs), len(can_refs)
    rep.refs_unverified = sum(1 for r in ext_refs if r.get("status") == "unverifiziert")
    rep.ref_pairs = pair_by_label(ext_refs, can_refs, "reference_id", threshold)
    ext_by_id = {r.get("reference_id"): r for r in ext_refs}
    can_by_id = {r.get("reference_id"): r for r in can_refs}
    for p in rep.ref_pairs:
        eu = str(ext_by_id[p.ext_id].get("source_url") or "").rstrip("/")
        cu = str(can_by_id[p.can_id].get("source_url") or "").rstrip("/")
        if eu != cu:
            rep.refs_url_differs.append(f"«{p.can_label}»: Extraktion {eu or '—'} vs. Handdatei {cu or '—'}")

    # --- Akteure (nur wenn die Handdatei actors[] fuehrt) ---------------------
    actor_map = parse_actor_map(pairing, extracted, canonical) if pairing is not None else {}
    actors, norm_to_id = _actor_index(canonical)
    if actors:
        rep.actors_checked = True
        rep.actors_available = [f"`{a['id']}` ({_label(a) or '—'})" for a in actors]
        can_actor = {s.get("step_id"): s.get("actor") for s in can_steps}
        for s in ext_steps:
            actor = s.get("actor")
            key = _norm_actor(actor) if isinstance(actor, str) else ""
            # Ausdrueckliche Zuordnung aus der Paarungsdatei vor ID/Label-Abgleich.
            mapped_id = actor_map[key] if key in actor_map else norm_to_id.get(key)
            if mapped_id is None:
                target = rep.actors_declared_none if key in actor_map else rep.actors_unmapped
                target.append(f"Schritt {s.get('step_id')}: «{actor}»")
            elif s.get("step_id") in group_of_ext:
                g = matched[group_of_ext[s.get("step_id")]]
                expected = sorted({str(can_actor[c]) for c, _ in g.can if can_actor.get(c)})
                if expected and mapped_id not in expected:
                    rep.actors_mismatch.append(
                        f"Schritt {s.get('step_id')} «{_label(s)}»: «{actor}» -> {mapped_id}, "
                        f"Handdatei: {' / '.join(expected)}"
                    )

    # --- Gate-Ausfall und Hinweis-Flags -------------------------------------
    rep.dropped_steps = sum(1 for f in flags if str(f).startswith("Schritt ") and "VERWORFEN" in str(f))
    for name, prefix in (
        ("ueberbrueckte Kanten", BRIDGE_FLAG_PREFIX),
        ("Reihenfolge-Hinweise", ORDER_FLAG_PREFIX),
        ("Akteur-Hinweise", ACTOR_FLAG_PREFIX),
    ):
        rep.flag_counts[name] = sum(1 for f in flags if str(f).startswith(prefix))

    # --- Strenger Lint auf beiden Seiten --------------------------------------
    rep.strict_hits_ext = _strict_hits(extracted)
    rep.strict_hits_can = _strict_hits(canonical)
    return rep


def pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.0%}"


def render_report(rep: EvalReport, source: str) -> str:
    lines = [
        f"# Bewertung: `{rep.proc_id}` — Extraktion vs. Handdatei",
        "",
        f"Massstab: {source}",
        (
            f"Schritt-Paarung: von Hand, {rep.pairing_source} (Status: {rep.pairing_status}"
            + (" — vom Maintainer noch zu bestaetigen" if rep.pairing_status != "bestaetigt" else "")
            + ")."
            if rep.pairing_source
            else f"Schritt-Paarung: Label-Aehnlichkeit >= {rep.threshold} (Heuristik, paart nach "
            "Wortueberlappung — fuer belastbare Zahlen eine Paarungsdatei anlegen: "
            "`tessera eval --propose-pairs`)."
        ),
        f"References: Label-Aehnlichkeit >= {rep.threshold} (Heuristik). Alle Paare unten ausgewiesen.",
        "Dieser Report aendert KEINE Daten.",
        "",
        "## Kennzahlen",
        "",
        "| Kennzahl | Wert |",
        "|---|---|",
        f"| Schritt-Recall (Handschritte gefunden) | {pct(rep.step_recall)} "
        f"({rep.can_matched}/{rep.can_steps}) |",
    ]
    if rep.step_recall_groundable is not None:
        lines.append(
            f"| Schritt-Recall ohne nicht belegbare Handschritte | {pct(rep.step_recall_groundable)} "
            f"({rep.can_matched}/{rep.can_steps - rep.can_not_groundable}) |"
        )
    lines += [
        f"| Schritt-Precision (Extraktion mit Entsprechung) | {pct(rep.step_precision)} "
        f"({rep.ext_matched}/{rep.ext_steps}) |",
        f"| Gate-Ausfall (verworfene Schritte) | {pct(rep.gate_dropout)} "
        f"({rep.dropped_steps}/{rep.ext_steps + rep.dropped_steps}) |",
        f"| Kanten exakt / Abkuerzung / umgekehrt / unbelegt | {len(rep.edges_exact)} / "
        f"{len(rep.edges_shortcut)} / {len(rep.edges_reversed)} / {len(rep.edges_unsupported)} "
        f"(von {rep.edges_compared} vergleichbaren) |",
        f"| Handkanten nicht extrahiert | {len(rep.edges_missed)} |",
        f"| References gepaart | {len(rep.ref_pairs)} (Extraktion {rep.ext_refs}, "
        f"davon unverifiziert {rep.refs_unverified}; Handdatei {rep.can_refs}) |",
    ]
    if rep.actors_checked:
        lines.append(
            f"| Akteure ohne `actors[]`-Entsprechung / bewusst ohne / falsch zugeordnet | "
            f"{len(rep.actors_unmapped)} / {len(rep.actors_declared_none)} / {len(rep.actors_mismatch)} |"
        )
    for name, n in rep.flag_counts.items():
        lines.append(f"| Flags: {name} | {n} |")
    lines.append(
        f"| Strenger Lint: Treffer Extraktion / Handdatei (Fehlalarm-Basis) | "
        f"{len(rep.strict_hits_ext)} / {len(rep.strict_hits_can)} |"
    )

    def section(title: str, items: list[str], hint: str = "") -> None:
        if not items:
            return
        lines.extend(["", f"## {title}", ""])
        if hint:
            lines.extend([hint, ""])
        lines.extend(f"- {i}" for i in items)

    def members(items: list[tuple[object, str]]) -> str:
        return ", ".join(f"{sid} «{lab}»" for sid, lab in items)

    lines.extend(["", "## Schritt-Paare", ""])
    matched = [g for g in rep.step_groups if g.matched]
    if not matched:
        lines.append("- Keine Paare.")
    elif rep.pairing_source:
        lines.extend(["| Extraktion | Handdatei | Notiz |", "|---|---|---|"])
        lines.extend(f"| {members(g.ext)} | {members(g.can)} | {g.note} |" for g in matched)
    else:
        lines.extend(["| Extraktion | Handdatei | Aehnlichkeit |", "|---|---|---|"])
        lines.extend(f"| {members(g.ext)} | {members(g.can)} | {g.similarity} |" for g in matched)
    section(
        "Moeglicherweise fehlende Schritte (Handdatei, ungepaart)",
        rep.missing_steps,
        "Die Luecke, die das Grounding-Gate nicht als Fehler sieht. Gegen die Quelle pruefen: "
        "steht der Schritt dort und fiel er durchs Gate, oder fehlt er in der Quelle?",
    )
    section("Zusaetzliche Schritte (Extraktion, ungepaart)", rep.extra_steps)
    section("Kanten in umgekehrter Reihenfolge", rep.edges_reversed)
    section("Abkuerzungen (Zwischenschritt fehlt)", rep.edges_shortcut)
    section("Unbelegte Kanten (in der Handdatei kein Pfad)", rep.edges_unsupported)
    section("Handkanten, die die Extraktion nicht hat", rep.edges_missed)
    section("References mit abweichender source_url", rep.refs_url_differs)
    section(
        "Akteure ohne `actors[]`-Entsprechung",
        rep.actors_unmapped,
        "Name aus der Quelle, der weder ID noch Label der Handdatei trifft. In der "
        "Paarungsdatei unter `akteure:` zuordnen (`Name: id`) oder bewusst ausnehmen "
        "(`Name: null`). Akteure der Handdatei: " + ", ".join(rep.actors_available) + ".",
    )
    section("Akteure bewusst ohne Entsprechung (Paarungsdatei)", rep.actors_declared_none)
    section("Akteure falsch zugeordnet", rep.actors_mismatch)
    section("Strenger Lint — Treffer in der Extraktion", rep.strict_hits_ext)
    section(
        "Strenger Lint — Treffer in der Handdatei",
        rep.strict_hits_can,
        "Menschlich reviewter Text, der trotzdem anschlaegt: Fehlalarm-Basis des strengen Lints.",
    )
    lines.append("")
    return "\n".join(lines)


def pairing_path(proc_id: str) -> Path:
    return REPORTS / f"{proc_id}.pairs.yaml"


def write_report(rep: EvalReport, source: str) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"{rep.proc_id}.md"
    out.write_text(render_report(rep, source), encoding="utf-8")
    return out
