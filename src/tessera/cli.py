"""tessera CLI — schlichte Schleife ueber die kuratierten Leistungen.

    tessera preflight [--id ...]   Katalog-Abdeckung + robots/ToU-Check (Pflicht)
    tessera crawl     [--id ...]   Quellseiten -> Markdown-Snapshots
    tessera extract   [--id ...]   Snapshots -> Vertrags-JSON (LLM, Grounding-Gate)
    tessera validate  [--id ...]   Vertrags-Validator auf out/<id>.json
    tessera pr        [--id ...]   Draft-PR-Bundle bauen / einreichen
    tessera run       [--id ...]   alles oben in Reihenfolge
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

from .config import ROOT, SourcesConfig, load_sources

OUT = ROOT / "out"
FLAGS_SUFFIX = ".flags.json"


def _procs(cfg: SourcesConfig, ids: list[str] | None):
    if not ids:
        return cfg.processes
    return [cfg.by_id(i) for i in ids]


def cmd_preflight(cfg: SourcesConfig, ids: list[str] | None) -> int:
    from . import preflight  # noqa: PLC0415

    gate = preflight.run_preflight(cfg, only=ids)
    print("Preflight abgeschlossen -> reports/coverage.md, reports/scraping-compliance.md")
    blocked = {k: v for k, v in gate.items() if not v["allowed"]}
    for pid, entry in gate.items():
        status = "GESPERRT (robots)" if pid in blocked else "freigegeben"
        print(f"  {pid}: {status}")
    if blocked:
        print("Gesperrte Leistungen NICHT crawlen — Maintainer fragen.", file=sys.stderr)
    return 0


def cmd_crawl(cfg: SourcesConfig, ids: list[str] | None) -> int:
    from . import crawl  # noqa: PLC0415

    for proc in _procs(cfg, ids):
        print(f"Crawle {proc.id} …")
        crawl.crawl_process(proc, cfg)
    return 0


def cmd_extract(cfg: SourcesConfig, ids: list[str] | None) -> int:
    from . import crawl, extract, grounding, schema  # noqa: PLC0415

    OUT.mkdir(exist_ok=True)
    rc = 0
    for proc in _procs(cfg, ids):
        print(f"Extrahiere {proc.id} …")
        corpus_text, meta = crawl.load_corpus(proc.id)
        ok_meta = [m for m in meta if m["http_status"] == 200 and m["chars"] > 0]
        if not ok_meta:
            print(f"  [{proc.id}] Keine brauchbaren Snapshots — uebersprungen.", file=sys.stderr)
            rc = 1
            continue

        x = extract.extract_process(proc, corpus_text)
        retrieved_at = max(m["retrieved_at"] for m in ok_meta)
        process, step_quotes = schema.to_contract(
            x,
            proc_id=proc.id,
            source_url=proc.official_urls[0],
            retrieved_at=retrieved_at,
        )
        process, flags = grounding.apply_gate(
            process, step_quotes, grounding.Corpus(corpus_text)
        )
        out_json = OUT / f"{proc.id}.json"
        out_json.write_text(
            json.dumps(process, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (OUT / f"{proc.id}{FLAGS_SUFFIX}").write_text(
            json.dumps(flags, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"  [{proc.id}] -> {out_json} ({len(process['steps'])} Schritte, {len(flags)} Flags)")
        for f in flags:
            print(f"    ⚠ {f}")
    return rc


def cmd_validate(cfg: SourcesConfig, ids: list[str] | None) -> int:
    rc = 0
    for proc in _procs(cfg, ids):
        out_json = OUT / f"{proc.id}.json"
        if not out_json.exists():
            print(f"  [{proc.id}] out/{proc.id}.json fehlt — zuerst `tessera extract`.", file=sys.stderr)
            rc = 1
            continue
        # Eingangskontrolle fuer JEDE Ausgabe: der Vertrags-Validator muss Exit 0 liefern.
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "validate_contract.py"), str(out_json)]
        )
        rc = rc or result.returncode
    return rc


def cmd_pr(cfg: SourcesConfig, ids: list[str] | None) -> int:
    from . import pr as pr_mod  # noqa: PLC0415
    from .crawl import RAW  # noqa: PLC0415

    rc = 0
    for proc in _procs(cfg, ids):
        out_json = OUT / f"{proc.id}.json"
        flags_file = OUT / f"{proc.id}{FLAGS_SUFFIX}"
        if not out_json.exists():
            print(f"  [{proc.id}] out/{proc.id}.json fehlt.", file=sys.stderr)
            rc = 1
            continue
        if cmd_validate(cfg, [proc.id]) != 0:
            print(f"  [{proc.id}] Validierung fehlgeschlagen — KEIN PR.", file=sys.stderr)
            rc = 1
            continue
        process = json.loads(out_json.read_text(encoding="utf-8"))
        flags = json.loads(flags_file.read_text(encoding="utf-8")) if flags_file.exists() else []
        meta = json.loads((RAW / proc.id / "meta.json").read_text(encoding="utf-8"))
        body = pr_mod.build_pr_body(proc, process, flags, meta)
        pr_mod.write_bundle(proc, process, body)
        pr_mod.open_draft_pr(proc, process, body)
    return rc


COMMANDS = {
    "preflight": cmd_preflight,
    "crawl": cmd_crawl,
    "extract": cmd_extract,
    "validate": cmd_validate,
    "pr": cmd_pr,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tessera", description=__doc__)
    parser.add_argument("command", choices=[*COMMANDS, "run"])
    parser.add_argument("--id", action="append", dest="ids", metavar="LEISTUNG",
                        help="nur diese Leistung(en) verarbeiten")
    args = parser.parse_args(argv)

    cfg = load_sources()
    if args.command == "run":
        for name in ("preflight", "crawl", "extract", "validate", "pr"):
            rc = COMMANDS[name](cfg, args.ids)
            if rc != 0:
                print(f"Abbruch in Schritt {name!r} (Exit {rc}).", file=sys.stderr)
                return rc
        return 0
    return COMMANDS[args.command](cfg, args.ids)


if __name__ == "__main__":
    raise SystemExit(main())
