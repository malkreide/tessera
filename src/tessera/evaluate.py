"""Bewertung: Extraktion gegen die handmodellierte Zieldatei messen. Nur stdlib.

Die von Hand modellierten, menschlich reviewten Prozesse in `maschinerie-zuerich`
sind ein fertiger Massstab. Statt zu vermuten, wie gut die Extraktion ist, misst
`tessera eval` sie dagegen — ohne PR, ohne Schreibzugriff auf out/:

* **Schritte:** Paarung ueber die Label-Aehnlichkeit (dieselbe Metrik wie der
  Label-Guard beim Merge, `merge._label_similarity`), greedy nach absteigender
  Aehnlichkeit, jede Seite hoechstens einmal. Daraus Recall (wie viel der
  Handdatei wurde gefunden) und Precision (wie viel der Extraktion hat eine
  Entsprechung). Ungepaarte Handschritte sind Kandidaten fuer FEHLENDE Schritte —
  genau die Luecke, die das Grounding-Gate nicht als Fehler sieht.
* **Kanten:** nur zwischen gepaarten Schritten vergleichbar. Eine extrahierte
  Kante ist «exakt», wenn die Handdatei sie direkt fuehrt; «Abkuerzung», wenn die
  Handdatei einen Pfad in derselben Richtung fuehrt (Zwischenschritt fehlt);
  «umgekehrt», wenn die Handdatei einen Pfad in Gegenrichtung fuehrt (falsche
  Reihenfolge); sonst «unbelegt».
* **References** (gepaart wie Schritte) und **Akteure** (gegen `actors[]` der
  Handdatei, Normalform wie beim Merge).
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
class EvalReport:
    proc_id: str
    threshold: float
    step_pairs: list[Pair] = field(default_factory=list)
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
    actors_mismatch: list[str] = field(default_factory=list)
    dropped_steps: int = 0
    flag_counts: dict[str, int] = field(default_factory=dict)
    strict_hits_ext: list[str] = field(default_factory=list)
    strict_hits_can: list[str] = field(default_factory=list)

    @property
    def step_recall(self) -> float | None:
        return len(self.step_pairs) / self.can_steps if self.can_steps else None

    @property
    def step_precision(self) -> float | None:
        return len(self.step_pairs) / self.ext_steps if self.ext_steps else None

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
) -> EvalReport:
    """Misst `extracted` (out/<id>.json) gegen `canonical` (Handdatei). Rein."""
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
    rep.step_pairs = pair_by_label(ext_steps, can_steps, "step_id", threshold)
    paired_ext = {p.ext_id: p.can_id for p in rep.step_pairs}
    paired_can = {p.can_id for p in rep.step_pairs}
    rep.missing_steps = [
        f"{s.get('step_id')} «{_label(s)}»" for s in can_steps if s.get("step_id") not in paired_can
    ]
    rep.extra_steps = [
        f"{s.get('step_id')} «{_label(s)}»" for s in ext_steps if s.get("step_id") not in paired_ext
    ]

    # --- Kanten (nur zwischen gepaarten Schritten vergleichbar) ---------------
    can_edges = _edges(can_steps)
    can_reach = _reachable(can_edges)
    can_labels = {s.get("step_id"): _label(s) for s in can_steps}
    mapped: set[tuple] = set()
    for a, b in _edges(ext_steps):
        if a not in paired_ext or b not in paired_ext:
            continue
        ca, cb = paired_ext[a], paired_ext[b]
        mapped.add((ca, cb))
        desc = f"{ca} -> {cb} («{can_labels.get(ca, '?')}» -> «{can_labels.get(cb, '?')}»)"
        if (ca, cb) in can_edges:
            rep.edges_exact.append(desc)
        elif cb in can_reach.get(ca, ()):
            rep.edges_shortcut.append(desc)
        elif ca in can_reach.get(cb, ()):
            rep.edges_reversed.append(desc)
        else:
            rep.edges_unsupported.append(desc)
    for ca, cb in sorted(can_edges, key=lambda e: (str(e[0]), str(e[1]))):
        if ca in paired_can and cb in paired_can and (ca, cb) not in mapped:
            rep.edges_missed.append(
                f"{ca} -> {cb} («{can_labels.get(ca, '?')}» -> «{can_labels.get(cb, '?')}»)"
            )

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
    actors = [
        a for a in canonical.get("actors") or [] if isinstance(a, dict) and isinstance(a.get("id"), str)
    ]
    if actors:
        rep.actors_checked = True
        norm_to_id: dict[str, str] = {}
        for a in actors:
            norm_to_id.setdefault(_norm_actor(a["id"]), a["id"])
            norm_to_id.setdefault(_norm_actor(_label(a)), a["id"])
        norm_to_id.pop("", None)
        can_actor = {s.get("step_id"): s.get("actor") for s in can_steps}
        for s in ext_steps:
            actor = s.get("actor")
            mapped_id = norm_to_id.get(_norm_actor(actor)) if isinstance(actor, str) else None
            if mapped_id is None:
                rep.actors_unmapped.append(f"Schritt {s.get('step_id')}: «{actor}»")
            elif s.get("step_id") in paired_ext:
                expected = can_actor.get(paired_ext[s.get("step_id")])
                if expected and expected != mapped_id:
                    rep.actors_mismatch.append(
                        f"Schritt {s.get('step_id')} «{_label(s)}»: «{actor}» -> {mapped_id}, Handdatei: {expected}"
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
        f"Paarung: Label-Aehnlichkeit >= {rep.threshold} (Heuristik — alle Paare unten ausgewiesen).",
        "Dieser Report aendert KEINE Daten.",
        "",
        "## Kennzahlen",
        "",
        "| Kennzahl | Wert |",
        "|---|---|",
        f"| Schritt-Recall (Handschritte gefunden) | {pct(rep.step_recall)} "
        f"({len(rep.step_pairs)}/{rep.can_steps}) |",
        f"| Schritt-Precision (Extraktion mit Entsprechung) | {pct(rep.step_precision)} "
        f"({len(rep.step_pairs)}/{rep.ext_steps}) |",
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
            f"| Akteure ohne `actors[]`-Entsprechung / falsch zugeordnet | "
            f"{len(rep.actors_unmapped)} / {len(rep.actors_mismatch)} |"
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

    lines.extend(["", "## Schritt-Paare", ""])
    if rep.step_pairs:
        lines.extend(["| Extraktion | Handdatei | Aehnlichkeit |", "|---|---|---|"])
        lines.extend(
            f"| {p.ext_id} «{p.ext_label}» | {p.can_id} «{p.can_label}» | {p.similarity} |"
            for p in rep.step_pairs
        )
    else:
        lines.append("- Keine Paare.")
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
    section("Akteure ohne `actors[]`-Entsprechung", rep.actors_unmapped)
    section("Akteure falsch zugeordnet", rep.actors_mismatch)
    section("Strenger Lint — Treffer in der Extraktion", rep.strict_hits_ext)
    section(
        "Strenger Lint — Treffer in der Handdatei",
        rep.strict_hits_can,
        "Menschlich reviewter Text, der trotzdem anschlaegt: Fehlalarm-Basis des strengen Lints.",
    )
    lines.append("")
    return "\n".join(lines)


def write_report(rep: EvalReport, source: str) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"{rep.proc_id}.md"
    out.write_text(render_report(rep, source), encoding="utf-8")
    return out
