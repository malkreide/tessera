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


class XStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: int = Field(ge=1)
    actor: str = Field(min_length=1, description="Handelnde Rolle (Buerger:in oder Behoerde).")
    label: XText = Field(description="Schritt-Bezeichnung OHNE bindende Zahlen.")
    depends_on: list[int | XCondDep] = Field(
        default_factory=list, description="Vorgaenger-step_ids; leer = Start-Schritt."
    )
    reference_ids: list[int] = Field(default_factory=list)
    source_quote: str = Field(
        description="WOERTLICHE Stelle im Quelltext, die diesen Schritt belegt (intern, wird nicht publiziert)."
    )


class XProcess(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: XText
    target_audience: Literal["bevoelkerung", "wirtschaft", "behoerden"]
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
    source_url: str,
    retrieved_at: str,
) -> tuple[dict, dict[int, str]]:
    """Baut das Vertrags-JSON (Kernfelder) und liefert die internen
    Schritt-Belegstellen separat zurueck (fuer das Grounding-Gate)."""
    steps = []
    step_quotes: dict[int, str] = {}
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
        if s.reference_ids:
            entry["reference_ids"] = s.reference_ids
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
        "schema_version": "0.1.0",
        "id": proc_id,
        "lebenslage_ref": proc_id,
        "city": "zh",
        "title": _i18n(x.title),
        "target_audience": x.target_audience,
        "steps": steps,
        "source_url": source_url,
        "retrieved_at": retrieved_at,
        "disclaimer_key": "Prozesse.disclaimer",
    }
    if x.preconditions:
        process["preconditions"] = [_i18n(p, with_empty=False) for p in x.preconditions]
    if references:
        process["references"] = references
    return process, step_quotes
