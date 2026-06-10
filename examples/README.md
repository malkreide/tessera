# Beispiel-Fixtures (synthetisch)

Diese JSONs sind **Test-Fixtures fuer den Vertrags-Validator**, nicht extrahierte,
belegte Prozessdaten. Sie demonstrieren die Struktur des Datenvertrags und die
Kardinalregel.

> **Nicht publizieren.** Die `source_url`-Werte sind Platzhalter und die
> `source_quote`-Werte sind ausdruecklich als illustrativ markiert. Echte
> Prozessdaten muessen jede Reference mit einem woertlichen Zitat der Originalseite
> belegen (Grounding-Gate), bevor sie als PR ins Ziel-Repo gehen.

## Dateien

| Datei | Zweck |
|---|---|
| `hund-anmelden.json` | **Gueltiges** Fixture. Bindende Werte (Anmeldefrist, Hundeabgabe) liegen nur in `references`; Schritte verlinken sie via `reference_ids`. en/fr/it sind leer (Uebersetzung ausstehend). |
| `invalid-binding-value-in-label.json` | **Ungueltiges** Fixture. Enthaelt absichtlich eine bindende Zahl im Step-Label («innert 10 Tagen», «CHF 175») und verletzt damit die Kardinalregel. Der Validator muss es ablehnen. |

## Pruefen

```bash
python scripts/validate_contract.py            # prueft examples/*.json
python scripts/validate_contract.py path/zu.json
```
