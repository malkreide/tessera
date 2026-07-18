# Reproduzierbarkeit der Extraktion

Warum das zaehlt: Tesseras Sicherheitsversprechen ist **Belegbarkeit** — jeder
Schritt und jede Reference ist als *woertliche* Stelle im gecrawlten Quelltext
belegt (`source_quote`), sonst wird er verworfen oder als unverifiziert geflaggt
(siehe `src/tessera/grounding.py`). Damit dieser Beleg stabil pruefbar bleibt,
muss der Weg von der Quellseite zum normalisierten Text reproduzierbar sein. Eine
stille Version-Drift im HTML-nach-Markdown-Pfad koennte ein bisher belegtes Zitat
ploetzlich durchs Grounding-Gate fallen lassen — oder umgekehrt.

## Abhaengigkeiten: zwei Pin-Ebenen

1. **`pyproject.toml` — Ranges.** tessera ist eine Anwendung; die Untergrenze ist
   der getestete Stand, die Obergrenze schuetzt vor Breaking Changes. Bewusst
   keine exakten Pins hier.
2. **`constraints.txt` — exakte Pins.** Die EINE Wahrheitsquelle fuer die exakten
   Versionen der direkten Deps, die den Crawl-/Verify-/Config-Pfad bestimmen
   (`httpx`, `trafilatura`, `pyyaml`, `pydantic`). Die CI-Crons installieren via
   `pip install -c constraints.txt <pakete>` — sie referenzieren die Datei, statt
   Versionen inline zu pinnen (kein Drift zwischen zwei Workflow-Dateien mehr).

Ein Versions-Bump ist damit **immer ein sichtbarer Commit** an `constraints.txt`,
nie ein impliziter Effekt eines Cron-Laufs. `constraints.txt` pinnt alle
**direkten** Laufzeit-Deps aus `pyproject.toml` — auch `crawl4ai`, `pydantic-ai`
und `openpyxl` (nur vom vollen Extraktionslauf gebraucht). Einen vollstaendigen
transitiven Lock (alle Untergraph-Deps) kann man bei installierbaren Deps mit
`pip-compile` erzeugen.

### Pins verifizieren / aktualisieren

«Verifiziert» heisst nicht «neueste PyPI-Version», sondern: der pip-Resolver
findet mit genau diesen Pins eine kompatible Kombination. So ermittelt/geprueft:

```bash
python -m pip install --dry-run --ignore-installed --report resolve.json \
  -c constraints.txt \
  "crawl4ai>=0.9,<1" "pydantic-ai>=2.5,<3" "openpyxl>=3.1,<4"
```

Exit 0 = auflösbar; die vom Resolver gewaehlten Versionen stehen in
`resolve.json` und wandern nach `constraints.txt`. Bei einem Bump denselben
Lauf mit der neuen Ober-/Untergrenze wiederholen.

## Determinismus des LLM-Laufs

- **Sampling:** Wo der Provider es akzeptiert, laeuft die Extraktion mit
  `temperature=0` (reproduzierbarere Laeufe/Diffs). Aktuelle Anthropic-Modelle
  (Opus 4.7/4.8, Fable, Mythos) akzeptieren KEINE Sampling-Parameter mehr — dort
  laesst tessera den Parameter bewusst weg (`extract._supports_sampling`);
  Reproduzierbarkeit laeuft ueber Prompt und `effort`. `temperature=0` hat
  ohnehin nie bit-identische Outputs garantiert.
- **Modell/Provider** kommen ausschliesslich aus ENV (`TESSERA_MODEL`, Key vom
  Provider-SDK). Kein Key im Code, kein stiller Fallback.
- **Nachgelagerte Determinismus-Anker:** Selbst bei Restschwankung des LLM
  greifen deterministische Gates — das Grounding-Gate (woertlicher Abgleich) und
  die Component-Vertraege (`src/tessera/contracts.py`) validieren jeden
  Zwischenstand mechanisch. Was nicht woertlich belegt ist, ueberlebt nicht.

## Kardinalregel «Link, don't assert»

Rechtlich bindende Werte (Fristen, Gebuehren, Rekursfristen) werden **nie** als
frei gerenderter Wert ausgegeben, sondern ausschliesslich als `reference` mit
Deep-Link auf die exakte Originalseite und woertlichem `source_quote`. Der
Kardinalregel-Lint (`src/tessera/binding.py`, geteilt von Validator und
Component-Vertrag `no_binding_values`) erzwingt das an jeder Grenze. So bleibt die
einzige autoritative Quelle fuer einen bindenden Wert die Originalseite — nicht
eine tessera-Ausgabe, die zwischen zwei Laeufen driften koennte.
