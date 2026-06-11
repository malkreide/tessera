# Katalog-Abdeckung (Pre-Flight)

> **Vorlage.** Wird vom Pre-Flight-Lauf der v1-Pipeline aus echten Abrufen gefüllt.
> Solange `Status = offen`, ist die Zeile nicht verifiziert.

Pre-Flight-Grundsatz: **Katalog konsumieren, nicht entdecken.** Quellen:

- **I14Y Public API** (Behördenleistungen, ohne Auth) — Basis `https://api.i14y.admin.ch`
  (exakten Ressourcen-Pfad gegen die Live-API-Doku bestätigen, nicht raten).
- **eCH-0070-Leistungsinventar** (XLSX) — als zusätzliche Abgleichquelle.

Für jede Leistung aus `sources.yaml` wird geprüft, ob sie im Katalog geführt ist und
die kuratierten Quell-URLs erreichbar sind.

| Leistung (`id`) | im I14Y-Katalog? | in eCH-0070? | Quell-URLs erreichbar? | Abrufdatum | Status |
|---|---|---|---|---|---|
| hund-anmelden | offen | offen | offen | – | offen |
| umzug-melden | offen | offen | offen | – | offen |

**Legende:** `ja` / `nein` / `offen` (noch nicht geprüft). Status `bereit`, sobald
Katalog-Treffer und Quell-URLs bestätigt sind; sonst `offen` oder `blockiert`
(mit Begründung).
