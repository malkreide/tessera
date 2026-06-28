# Lokales Modell betreiben (z. B. Raspberry Pi 5 mit Gemma)

> Status: **Notiz, nicht empfohlener Default.** Die Pipeline läuft produktiv gegen
> einen API-Provider (Default `anthropic:claude-opus-4-8`). Dieses Dokument hält fest,
> ob und wie ein lokales Modell ginge — für den Fall, dass jemand es später braucht
> (z. B. Datenschutz-sensible Umgebung). Bei nicht-sensiblen, öffentlichen
> Verwaltungsquellen gibt es keinen Grund, vom API-Provider abzuweichen.

## Geht das überhaupt?

Technisch ja. Provider und Modell kommen ausschliesslich aus dem ENV
(`src/tessera/extract.py`): `TESSERA_MODEL` ist ein pydantic-ai-Modellstring, es gibt
keine harte Anthropic-Abhängigkeit im Code. `pydantic-ai` spricht auch
OpenAI-kompatible Endpunkte, und ein lokaler [Ollama](https://ollama.com)-Server
bietet genau so einen an. Der grobe Weg:

```bash
# Auf dem Pi: ollama serve; ollama pull gemma3:4b
export TESSERA_MODEL=openai:gemma3:4b
export OPENAI_BASE_URL=http://localhost:11434/v1
export OPENAI_API_KEY=ollama        # Dummy genügt — Ollama prüft ihn nicht;
                                    # der Key-Check in extract.py verlangt nur,
                                    # dass die Variable gesetzt ist.
```

**Mögliche kleine Code-Anpassung:** Aktuell wird nur der Modell-String an `Agent()`
übergeben, kein `base_url`. Greift pydantic-ai die `OPENAI_BASE_URL` nicht von selbst
auf, muss der Provider explizit mit `base_url` konstruiert werden (wenige Zeilen in
`extract.py`). Diese Anpassung ist bewusst **nicht** gemacht — sie wird erst gebaut,
wenn ein lokales Modell wirklich gebraucht wird.

## Der eigentliche Haken: die Aufgabe, nicht die Hardware

Tessera verlangt zwei Dinge, die kleine, quantisierte Modelle auf einem Pi 5
(CPU-Inferenz, begrenztes RAM) schlecht liefern:

1. **Striktes structured output** — der ganze `XProcess`-Pydantic-Graph in einem
   Rutsch, valide. Kleine Gemma-Varianten brechen hier oft das Schema.
2. **Zeichengetreues `source_quote`** — das Grounding-Gate
   («Belegbarkeit statt Selbsteinschätzung», siehe `CLAUDE.md`) verwirft jeden
   Schritt, dessen Zitat nicht **wörtlich** im Quelltext steht. Kleine Modelle
   paraphrasieren statt exakt zu kopieren — genau das fällt hier raus.

Das Beruhigende: Ein schwaches lokales Modell produziert **keinen falschen Output**,
sondern **wenig oder keinen**. Grounding-Gate und Pydantic-Validator fangen
Halluzinationen ab; die Cardinal Rule «Link, don't assert» bleibt intakt. Es ist also
kein *Sicherheits*-, sondern ein *Nutzbarkeits*problem: auf dem Pi mit Gemma 4B sind
viele geflaggte/verworfene Schritte und langsame Läufe (langer Markdown-Kontext auf
CPU) zu erwarten.

## Realistischere Variante, falls lokal je nötig wird

Pi 5 als **Orchestrator** — Crawl, Validierung und PR-Erstellung laufen ohnehin lokal
und brauchen kein grosses Modell. Nur den reinen Extraktions-Call gegen ein stärkeres
Modell schicken: entweder weiter beim API-Provider, oder ein grösseres lokales Modell
auf einer Maschine mit GPU im selben Netz (gleicher `OPENAI_BASE_URL`-Mechanismus).
