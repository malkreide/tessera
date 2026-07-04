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
committen. Ältere Hash-only-Baselines bleiben gültig; sie liefern lediglich
keine Diff-Auszüge, bis der nächste `fingerprint`-Lauf die Texte ergänzt.
