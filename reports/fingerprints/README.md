# Änderungs-Baselines (v2 `tessera fingerprint` / `tessera diff`)

Je Leistung liegt hier eine committete Baseline:

- **`<id>.json`** — je Quell-URL ein SHA-256 über den normalisierten
  Seitentext (`grounding.normalize`) plus Zeichenzahl. `tessera diff`
  vergleicht die Live-Seiten dagegen; nur inhaltliche Änderungen lösen einen
  Befund aus, Kosmetik (Whitespace, Typografie, Markdown-Deko) nicht.
- **`<id>/NN-slug.txt`** — der zeilenweise normalisierte Seitentext derselben
  URL. Zweck: Meldet `diff` eine Änderung, zeigt er (und das rollende
  `source-change`-Issue) einen unified-diff-Auszug baseline vs. live — also
  *was* sich geändert hat, nicht nur *wo*.

## Provenienz und Zweck

Die Textdateien sind **normalisierte Auszüge amtlicher Webseiten** der in
`sources.yaml` kuratierten Quellen (Quell-URL steht im zugehörigen JSON).
Sie dienen ausschliesslich der Änderungserkennung (Diff-Basis) und sind
**keine publizierten Prozessdaten** — publiziert wird nur der belegte,
menschlich reviewte Vertrags-Output via Draft-PR.

## Pflege

`tessera fingerprint --id <leistung>` schreibt JSON **und** Textdateien neu
und entfernt nicht mehr geführte `.txt` (das Verzeichnis gehört vollständig
dem Fingerprint). Nach einem bestätigten Re-Extraktions-Lauf ausführen und
committen.

Ohne lokale Session mit offener Netz-Policy: Actions → **fingerprint** →
«Run workflow» mit den Leistungs-IDs (z.B. `kita-platz veranstaltung`). Der
Workflow läuft auf demselben Runner wie `change-diff.yml` (vergleichbare
Hashes), bricht bei einer Leistung ohne erreichbare URL ohne Commit ab und
reicht die Baseline als Draft-PR auf einem eigenen Branch ein — nie nach
`main`.

Robots-/ToU-Gate: eine Baseline (also Volltext der Quellseiten) entsteht nur
für Leistungen, deren Domains freigegeben sind (`terms_of_use` in
`sources.yaml`, siehe `reports/scraping-compliance.md`). Ist eine angeforderte
Leistung gesperrt, schreibt `tessera fingerprint` nichts und endet mit Exit 1;
der Workflow scheitert dann ohne Commit. Die bereits committeten Baselines
bleiben davon unberührt. Ältere Hash-only-Baselines bleiben gültig; sie liefern lediglich
keine Diff-Auszüge, bis der nächste `fingerprint`-Lauf die Texte ergänzt.
