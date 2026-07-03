"""Striktes Extraktionsschema (struktur-only) und Abbildung auf den Datenvertrag.

Zwei Ebenen:

* X*-Modelle: das, was das LLM liefern muss. Jeder Schritt und jede Referenz
  traegt eine WOERTLICHE Belegstelle (source_quote) aus dem Crawl-Korpus —
  das ist der Input fuer das Grounding-Gate. Schritt-Belegstellen sind rein
  intern und werden NICHT ausgegeben (der Vertrag kennt sie nicht).
* to_contract(): baut daraus exakt das kanonische Kern-Format
  (docs/data-contract.md, abgeglichen auf maschinerie-zuerich).

KARDINALREGEL ist hier Schema-Wissen: Labels/Descriptions duerfen keine
bindenden Zahlen tragen; Fristen/Gebuehren existieren nur als Reference.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .contract import SCHEMA_VERSION
from .risk import HIGH_RISK_DISCLAIMER_KEY, is_high_risk

# Additive kanonische Step-Typen (maschinerie-zuerich, vom Vertrags-Validator
# geprueft). Strukturelle Klassifikation eines ohnehin belegten Schritts —
# speist im Ziel-Dashboard die Indikatoren (z.B. Medienbruch, Online-Schritt).
StepType = Literal["start", "input", "prozess", "entscheidung", "loop", "warten", "ende"]


class XText(BaseModel):
    """Deutscher Text plus optional Leichte Sprache (ls)."""

    model_config = ConfigDict(extra="forbid")

    de: str = Field(min_length=1)
    ls: str = ""


class XCondDep(BaseModel):
    """Bedingte Kante: Vorgaenger-Schritt + Bedingung (z.B. Entscheidungsausgang)."""

    model_config = ConfigDict(extra="forbid")

    step_id: int
    condition: XText


class XReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_id: int = Field(ge=1)
    label: XText = Field(
        description="Benennt den bindenden Wert OHNE die Zahl (z.B. 'Meldefrist bei Zuzug')."
    )
    source_url: str = Field(description="Deep-Link auf die exakte Originalseite.")
    source_quote: str = Field(
        description="WOERTLICHES Zitat der Belegstelle aus dem gecrawlten Quelltext. Leer lassen, wenn keine woertliche Stelle existiert."
    )


class XDocument(BaseModel):
    """Ein vom Schritt benoetigtes Dokument. Wie ein Schritt belegbar: das
    source_quote ist intern (Grounding-Gate) und wird NICHT publiziert."""

    model_config = ConfigDict(extra="forbid")

    label: XText = Field(description="Dokument-Bezeichnung OHNE bindende Zahlen (z.B. 'Ausweis').")
    required: bool | None = Field(
        default=None, description="True = zwingend, False = optional, None = unklar aus der Quelle."
    )
    source_quote: str = Field(
        description="WOERTLICHE Belegstelle aus dem Quelltext (intern, wird nicht publiziert). Leer lassen, wenn nicht woertlich belegbar."
    )


class XStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: int = Field(ge=1)
    actor: str = Field(min_length=1, description="Handelnde Rolle (Buerger:in oder Behoerde).")
    label: XText = Field(description="Schritt-Bezeichnung OHNE bindende Zahlen.")
    type: StepType | None = Field(
        default=None,
        description="Strukturtyp des Schritts (start/input/prozess/entscheidung/loop/warten/ende); None, wenn nicht eindeutig.",
    )
    depends_on: list[int | XCondDep] = Field(
        default_factory=list, description="Vorgaenger-step_ids; leer = Start-Schritt."
    )
    reference_ids: list[int] = Field(default_factory=list)
    documents: list[XDocument] = Field(
        default_factory=list, description="Benoetigte Dokumente (jeweils woertlich belegt)."
    )
    source_quote: str = Field(
        description="WOERTLICHE Stelle im Quelltext, die diesen Schritt belegt (intern, wird nicht publiziert)."
    )


class XProcess(BaseModel):
    """Extraktionsergebnis. Bewusst OHNE target_audience: das ist kuratiertes
    Metadatum aus sources.yaml und wird nicht vom LLM (neu) klassifiziert."""

    model_config = ConfigDict(extra="forbid")

    title: XText
    preconditions: list[XText] = Field(default_factory=list)
    steps: list[XStep]
    references: list[XReference] = Field(default_factory=list)


def _i18n(x: XText, *, with_empty: bool = True) -> dict:
    """XText -> kanonisches i18n-Objekt. en/fr/it bleiben leer (Uebersetzung
    ausstehend — wird NICHT maschinell geraten); ls nur, wenn vorhanden."""
    out: dict = {"de": x.de.strip()}
    if with_empty:
        out.update({"en": "", "fr": "", "it": ""})
    if x.ls.strip():
        out["ls"] = x.ls.strip()
    return out


def to_contract(
    x: XProcess,
    *,
    proc_id: str,
    target_audience: str,
    source_url: str,
    retrieved_at: str,
) -> tuple[dict, dict[int, str], dict[tuple[int, int], str]]:
    """Baut das Vertrags-JSON (Kernfelder) und liefert die internen Belegstellen
    separat zurueck (fuer das Grounding-Gate): Schritt-Zitate je step_id und
    Dokument-Zitate je (step_id, Dokument-Index)."""
    steps = []
    step_quotes: dict[int, str] = {}
    doc_quotes: dict[tuple[int, int], str] = {}
    for s in x.steps:
        step_quotes[s.step_id] = s.source_quote
        dep: list = []
        for d in s.depends_on:
            if isinstance(d, XCondDep):
                dep.append({"step_id": d.step_id, "condition": _i18n(d.condition, with_empty=False)})
            else:
                dep.append(d)
        entry: dict = {
            "step_id": s.step_id,
            "actor": s.actor.strip(),
            "label": _i18n(s.label),
            "depends_on": dep,
        }
        if s.type:
            entry["type"] = s.type
        if s.reference_ids:
            entry["reference_ids"] = s.reference_ids
        if s.documents:
            docs = []
            for i, d in enumerate(s.documents):
                doc_quotes[(s.step_id, i)] = d.source_quote
                doc: dict = {"label": _i18n(d.label, with_empty=False)}
                if d.required is not None:
                    doc["required"] = d.required
                docs.append(doc)
            entry["documents"] = docs
        steps.append(entry)

    references = []
    for r in x.references:
        references.append(
            {
                "reference_id": r.reference_id,
                "label": _i18n(r.label),
                "source_url": r.source_url,
                "source_quote": r.source_quote.strip(),
                "status": "verifiziert",  # Grounding-Gate stuft ggf. auf 'unverifiziert' herab
                "retrieved_at": retrieved_at,
            }
        )

    process: dict = {
        "$schema": "../../../schemas/opengov-process-schema.json",
        "schema_version": SCHEMA_VERSION,
        "id": proc_id,
        "lebenslage_ref": proc_id,
        "city": "zh",
        "title": _i18n(x.title),
        "target_audience": target_audience,
        "steps": steps,
        "source_url": source_url,
        "retrieved_at": retrieved_at,
        # Hochrisiko-Faelle tragen den sichtbaren Hochrisiko-Disclaimer (kanonisch
        # `Prozesse.disclaimerHochrisiko`); sonst der reguläre Prozess-Disclaimer.
        "disclaimer_key": HIGH_RISK_DISCLAIMER_KEY if is_high_risk(proc_id) else "Prozesse.disclaimer",
    }
    if x.preconditions:
        process["preconditions"] = [_i18n(p, with_empty=False) for p in x.preconditions]
    if references:
        process["references"] = references
    return process, step_quotes, doc_quotes
