# Datenvertrag: Tessera → Maschinerie Zürich

> **Status: Entwurf.** Kanonisch ist das in **v0** im Repo `maschinerie-zuerich`
> definierte Prozess-Schema, sobald es existiert. Dieser Vertrag wird darauf
> abgeglichen. Bis dahin dient er als gemeinsame Zielvorgabe für beide Repos.

Dieser Vertrag definiert das Format, das Tessera produziert und die Maschinerie
konsumiert. Er ist die einzige Schnittstelle zwischen den beiden Repos – Änderungen
hier sind Breaking Changes und müssen in beiden Repos nachgezogen und versioniert
werden.

## Grundsätze

1. **«Link, don't assert».** Rechtlich bindende Werte (Fristen, Gebühren,
   Rekursfristen) erscheinen **nur** als `references` (Label + Link), nie als
   gerenderter autoritativer Wert in einem Schritt-Label.
2. **Belegbarkeit.** Jeder Schritt und jede Referenz trägt eine `source_quote`, die
   wörtlich in der Quelle auffindbar sein muss. Nicht belegbare Elemente werden vor
   der Ausgabe verworfen.
3. **Provenienz.** Jeder Prozess trägt Quell-URL, Abrufdatum und einen
   Inoffiziell-Hinweis.
4. **Versionierung.** Jedes Objekt trägt `schema_version` (SemVer).

## Objekt `Process`

| Feld | Typ | Pflicht | Anmerkung |
|---|---|---|---|
| `schema_version` | string (SemVer) | ja | z.B. `"0.1.0"` |
| `id` | string (kebab-case) | ja | z.B. `"hund-anmelden"` |
| `lebenslage_ref` | string | ja | Schlüssel der bestehenden Lebenslage in der Maschinerie |
| `title` | i18n-Objekt | ja | `{de, en, fr, it, leichte_sprache}` |
| `target_audience` | enum | ja | eCH-0073: `bevoelkerung` \| `wirtschaft` \| `behoerden` |
| `preconditions` | i18n-Liste | nein | Vorbedingungen (eCH-0073) |
| `steps` | `Step[]` | ja | siehe unten |
| `references` | `Reference[]` | nein | bindende Werte als Links (siehe unten) |
| `source_url` | string (URL) | ja | Originalseite der Behörde |
| `retrieved_at` | string (ISO 8601) | ja | Abrufzeitpunkt |
| `disclaimer_key` | string | ja | i18n-Key des Inoffiziell-Hinweises |

## Objekt `Step`

| Feld | Typ | Pflicht | Anmerkung |
|---|---|---|---|
| `step_id` | integer | ja | eindeutig je Prozess (Knoten im Graph) |
| `actor` | string | ja | handelnde Behörde oder Bürger:in |
| `label` | i18n-Objekt | ja | Schritt-Bezeichnung; **keine bindenden Zahlen** |
| `depends_on` | integer[] | ja | `step_id`s der Vorgänger (Kanten); leer = Start |
| `reference_ids` | integer[] | nein | Verweise auf `references` (z.B. zugehörige Frist) |

## Objekt `Reference` (hier liegen Fristen, Gebühren, Rekursfristen)

| Feld | Typ | Pflicht | Anmerkung |
|---|---|---|---|
| `reference_id` | integer | ja | eindeutig je Prozess |
| `label` | i18n-Objekt | ja | z.B. «Rekursfrist» – **ohne** die Zahl als behaupteten Fakt |
| `source_url` | string (URL) | ja | Deep-Link auf die exakte Stelle der Originalseite |
| `source_quote` | string | ja | wörtliche Belegstelle aus der Quelle (für Grounding/Audit) |
| `retrieved_at` | string (ISO 8601) | ja | Abrufzeitpunkt |

## Beispiel (gekürzt)

```json
{
  "schema_version": "0.1.0",
  "id": "hund-anmelden",
  "lebenslage_ref": "hund-anmelden",
  "title": { "de": "Hund anmelden", "en": "Register a dog", "fr": "", "it": "", "leichte_sprache": "" },
  "target_audience": "bevoelkerung",
  "preconditions": { "de": ["Wohnsitz in der Stadt Zürich"] },
  "steps": [
    { "step_id": 1, "actor": "Halter:in", "label": { "de": "Hund online anmelden" }, "depends_on": [], "reference_ids": [1] },
    { "step_id": 2, "actor": "Steueramt", "label": { "de": "Veranlagung der Hundeabgabe" }, "depends_on": [1], "reference_ids": [2] }
  ],
  "references": [
    { "reference_id": 1, "label": { "de": "Anmeldefrist" }, "source_url": "https://www.stadt-zuerich.ch/...", "source_quote": "innert ...", "retrieved_at": "2026-06-09T00:00:00Z" },
    { "reference_id": 2, "label": { "de": "Höhe der Hundeabgabe" }, "source_url": "https://www.stadt-zuerich.ch/...", "source_quote": "...", "retrieved_at": "2026-06-09T00:00:00Z" }
  ],
  "source_url": "https://www.stadt-zuerich.ch/...",
  "retrieved_at": "2026-06-09T00:00:00Z",
  "disclaimer_key": "process.disclaimer.unofficial"
}
```

## Maschinenlesbar & Validierung

- Eine maschinenlesbare Fassung dieses Entwurfs liegt als JSON Schema in
  `docs/process.schema.json`. Sie ist **abgeleitet und nicht-kanonisch** – bei
  Abweichung gilt das v0-Schema im Repo `maschinerie-zuerich`.
- Der Check `scripts/validate_contract.py` (nur Python-stdlib, keine Dependency)
  prueft Prozess-JSONs gegen den Vertrag, inklusive Graph-Integritaet (DAG),
  Referenz-Integritaet, Grounding-Gate (`source_quote` vorhanden) und der
  Kardinalregel (bindende Zahl im Step-Label = Fehler). Beispiele in `examples/`.

```bash
python scripts/validate_contract.py            # prueft examples/*.json
python scripts/validate_contract.py pfad/zu/prozess.json
```

## Was bewusst NICHT im Vertrag steht

- Keine Klartext-Felder für Fristen/Gebühren als Zahl. Wer eine Frist sehen will,
  folgt dem Link in `references`. Das ist Absicht, kein fehlendes Feld.
- Keine BPMN-/XML-Repräsentation (optionaler Export erst in v3).
- Kein `confidence_score`. Belegbarkeit (`source_quote`) ersetzt Selbsteinschätzung.
