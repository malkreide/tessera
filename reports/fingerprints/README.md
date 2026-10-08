# Änderungs-Baselines (v2 `tessera fingerprint` / `tessera diff`)

Je Leistung liegt hier eine committete Baseline:

- **`<id>.json`** — je Quell-URL ein SHA-256 über den normalisierten
  Seitentext (`grounding.normalize`) plus Zeichenzahl. `tessera diff`
  vergleicht die Live-Seiten dagegen; nur inhaltliche Änderungen lösen einen
  Befund aus, Kosmetik (Whitespace, Typografie, Markdown-Deko) nicht.

**Hier liegt kein Seitentext.** Die Baselines enthalten nur Hash und
Zeichenzahl — keinen Inhalt der amtlichen Seiten. Deren Nutzungsbedingungen
erlauben nur Ansehen, Herunterladen zum Eigengebrauch und Ausdrucken; Volltext
gehört deshalb nicht in dieses öffentliche Repo. `.gitignore` sperrt
`reports/fingerprints/*/`, und `tests/test_diff.py` schlägt in der CI fehl,
sobald hier etwas anderes als die JSON-Baselines und dieses README liegt.

## Diff-Auszüge (nur lokal)

`tessera fingerprint` legt den zeilenweise normalisierten Seitentext je URL
zusätzlich **lokal** ab: `reports/raw/fingerprints/<id>/NN-slug.txt`
(git-ignoriert, nie committet). Meldet ein lokaler `tessera diff` eine
Änderung, zeigt er daraus einen unified-diff-Auszug baseline vs. live — also
*was* sich geändert hat, nicht nur *wo*. Fehlt der lokale Text (frischer
Checkout, CI-Cron), wird die Änderung weiterhin gemeldet, nur ohne Auszug.

## Pflege

`tessera fingerprint --id <leistung>` schreibt die JSON-Baseline neu (und den
lokalen Text; nicht mehr geführte lokale `.txt` werden entfernt). Nach einem
bestätigten Re-Extraktions-Lauf ausführen und das JSON committen.

Ohne lokale Session mit offener Netz-Policy: Actions → **fingerprint** →
«Run workflow» mit den Leistungs-IDs (z.B. `kita-platz veranstaltung`). Der
Workflow läuft auf demselben Runner wie `change-diff.yml` (vergleichbare
Hashes), bricht bei einer Leistung ohne erreichbare URL ohne Commit ab und
reicht die Baseline als Draft-PR auf einem eigenen Branch ein — nie nach
`main`.

Robots-/ToU-Gate: eine Baseline entsteht nur für Leistungen, deren Domains
freigegeben sind (`terms_of_use` in `sources.yaml`, siehe
`reports/scraping-compliance.md`). Ist eine angeforderte Leistung gesperrt,
schreibt `tessera fingerprint` nichts und endet mit Exit 1; der Workflow
scheitert dann ohne Commit. Die bereits committeten Baselines bleiben davon
unberührt.
