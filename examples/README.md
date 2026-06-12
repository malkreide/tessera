# Beispiel-Fixtures (synthetisch)

Diese JSONs sind **Test-Fixtures fuer den Vertrags-Validator**, nicht extrahierte,
belegte Prozessdaten. Sie demonstrieren die Struktur des Datenvertrags und die
Kardinalregel.

> **Nicht publizieren.** Die `source_url`-Werte sind Platzhalter und die
> `source_quote`-Werte sind ausdruecklich als illustrativ markiert. Echte
> Prozessdaten muessen jede Reference mit einem woertlichen Zitat der Originalseite
> belegen (Grounding-Gate), bevor sie als PR ins Ziel-Repo gehen.

## Dateien

Dateien mit Praefix `invalid-` MUESSEN den Validator scheitern lassen; alle anderen
MUESSEN gueltig sein (`tests/run_checks.py` prueft genau diese Erwartung).

| Datei | Zweck |
|---|---|
| `hund-anmelden.json` | **Gueltig.** Bindende Werte nur in `references`; eine bedingte `depends_on`-Kante (i18n-`condition`); `ls` + tagesgenaues Datum. |
| `extensions-showcase.json` | **Gueltig.** Uebt **alle additiven kanonischen Felder** aus: `city`, `description`, `actors` (mit `einheit_ref`), `legal_basis`, `sources`, `reife`, `meta`; Step `type`/`description`/`documents`/`source_id`/`loops_back_to`; Reference `status` (verifiziert + unverifiziert). |
| `invalid-binding-value-in-label.json` | **Ungueltig.** Bindende Zahl im Step-Label («innert 10 Tagen», «CHF 175») – Kardinalregel-Verstoss. |
| `invalid-binding-value-in-condition.json` | **Ungueltig.** Bindende Zahl in einer `depends_on[].condition` («innert 30 Tagen») – Kardinalregel gilt fuer ALLE gerenderten Texte, auch Bedingungs-Kanten. |
| `invalid-grounding-verifiziert.json` | **Ungueltig.** Reference mit `status: verifiziert` ohne `source_quote` – Grounding-Gate-Verstoss. |

## Pruefen

```bash
python scripts/validate_contract.py            # prueft examples/*.json
python scripts/validate_contract.py path/zu.json
python tests/run_checks.py                      # Erwartungen (CI-Einstieg)
```

Der Validator prueft die echten kanonischen Prozess-JSONs aus `maschinerie-zuerich`
1:1 (Kern- + additive Felder).
