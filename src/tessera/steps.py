"""Die Extraktions-Strecke als Kette validierter Components (ODTP-Muster,
konzeptionell — kein ODTP-Code, keine Runtime, keine Dependency).

Statt einer linearen Prozedur in `cli.cmd_extract` ist die Strecke hier in klar
abgegrenzte Schritte zerlegt. Jeder Schritt ist EINE Transformation mit
explizit typisierter Ein- und Ausgabe (die `_Artifact`-Dataclasses unten), und
jede Grenze wird gegen einen Teil-Vertrag validiert (`contracts.py`). Eine
Verletzung stoppt den Schritt HART (`ComponentError`) — kein stilles
Weiterreichen fehlerhafter Zwischenstaende.

    load  ->  extract  ->  to_contract  ->  ground  ->  screen
    Korpus    XProcess     Kern-Vertrag    gegatet     + Screening-Flags

Die eigentlichen Transformationen rufen dieselben Funktionen wie bisher
(crawl/extract/schema/grounding/screening) — die Component-Schicht fuegt nur die
validierten Grenzen hinzu. pydantic/crawl4ai werden erst hier (lazy) importiert;
`component.py` und `contracts.py` bleiben stdlib-rein und dependency-frei testbar.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import contracts
from .component import Component, run_pipeline


# --- Artefakte an den Component-Grenzen (explizit typisierte Ein-/Ausgabe) ---
@dataclass(frozen=True)
class CrawlCorpus:
    text: str
    meta: list[dict]
    url_texts: dict[str, str]
    usable_meta: list[dict]


@dataclass(frozen=True)
class Draft:
    corpus: CrawlCorpus
    xprocess: object  # schema.XProcess (pydantic; an dieser Grenze als Objekt)


@dataclass(frozen=True)
class Core:
    corpus: CrawlCorpus
    process: dict
    step_quotes: dict
    doc_quotes: dict


@dataclass(frozen=True)
class Grounded:
    corpus: CrawlCorpus
    process: dict
    flags: list[str] = field(default_factory=list)


def _load(proc) -> CrawlCorpus:
    from . import crawl  # noqa: PLC0415

    text, meta, url_texts = crawl.load_corpus(proc.id)
    usable = [m for m in meta if m["http_status"] == 200 and m["chars"] > 0]
    return CrawlCorpus(text=text, meta=meta, url_texts=url_texts, usable_meta=usable)


def _load_ok(corpus: CrawlCorpus) -> list[str]:
    problems = contracts.nonempty_corpus(corpus.text)
    if not corpus.usable_meta:
        problems.append("Keine brauchbaren Snapshots (http_status 200, chars > 0).")
    return problems


def _extract(proc, corpus: CrawlCorpus) -> Draft:
    from . import registry  # noqa: PLC0415

    # Registry waehlt den Extraktor pro Leistung (spezialisiert vor generisch);
    # ein neuer Prozesstyp kommt hinzu, ohne diese Strecke anzufassen.
    xprocess = registry.get_extractor(proc).extract(proc, corpus.text)
    return Draft(corpus=corpus, xprocess=xprocess)


def _draft_ok(draft: Draft) -> list[str]:
    # Der Contract prueft die Dict-Form (dependency-frei getestet); hier dumpen.
    return contracts.xprocess_wellformed(draft.xprocess.model_dump())


def _to_contract(proc, draft: Draft) -> Core:
    from . import schema  # noqa: PLC0415

    corpus = draft.corpus
    retrieved_at = max(m["retrieved_at"] for m in corpus.usable_meta)
    process, step_quotes, doc_quotes = schema.to_contract(
        draft.xprocess,
        proc_id=proc.id,
        target_audience=proc.target_audience,  # kuratiert, nie LLM-inferiert
        source_url=proc.official_urls[0],
        retrieved_at=retrieved_at,
    )
    # Provenienz je Reference: das Abrufdatum IHRER Quellseite (aus meta.json),
    # nicht pauschal das juengste des Laufs. Unbekannte URLs behalten den
    # Fallback; das per-URL-Grounding flaggt sie ohnehin.
    date_by_url = {m["url"].strip().rstrip("/"): m["retrieved_at"] for m in corpus.usable_meta}
    for ref in process.get("references", []):
        d = date_by_url.get(str(ref.get("source_url", "")).strip().rstrip("/"))
        if d:
            ref["retrieved_at"] = d
    return Core(corpus=corpus, process=process, step_quotes=step_quotes, doc_quotes=doc_quotes)


def _ground(core: Core) -> Grounded:
    from . import grounding  # noqa: PLC0415

    corpus = core.corpus
    # Per-URL-Grounding: Reference-Zitate muessen auf der Seite ihrer source_url
    # stehen, nicht bloss irgendwo im Gesamt-Korpus.
    corpus_by_url = {u: grounding.Corpus(t) for u, t in corpus.url_texts.items()}
    process, flags = grounding.apply_gate(
        core.process,
        core.step_quotes,
        grounding.Corpus(corpus.text),
        core.doc_quotes,
        corpus_by_url=corpus_by_url,
    )
    return Grounded(corpus=corpus, process=process, flags=flags)


def _screen(grounded: Grounded) -> Grounded:
    from . import screening  # noqa: PLC0415

    # Injection-Screening auf dem UNTRUSTED Korpus: Flag, kein Gate — das
    # Grounding-Gate beweist Herkunft, nicht Legitimitaet; injizierter Seitentext
    # wuerde es bestehen. Befund vorne anstellen (prominent).
    flags = screening.screen_url_texts(grounded.corpus.url_texts) + grounded.flags
    return Grounded(corpus=grounded.corpus, process=grounded.process, flags=flags)


def build_pipeline(proc) -> list[Component]:
    """Baut die validierte Component-Kette fuer eine Leistung. proc/config werden
    in die Transformationen geschlossen; die Grenzen tragen die Teil-Vertraege."""
    return [
        Component("load", _load, check_output=_load_ok),
        Component("extract", lambda c: _extract(proc, c), check_output=_draft_ok),
        Component("to_contract", lambda d: _to_contract(proc, d), check_output=lambda core: contracts.core_contract(core.process)),
        Component("ground", _ground, check_output=lambda g: contracts.grounded_ok(g.process)),
        Component("screen", _screen, check_output=lambda g: contracts.grounded_ok(g.process)),
    ]


def run_extract(proc) -> Grounded:
    """Fuehrt die Extraktions-Strecke fuer eine Leistung aus. Jede Grenze wird
    validiert; die erste Verletzung wirft `ComponentError` (harter Stopp)."""
    return run_pipeline(build_pipeline(proc), proc)
