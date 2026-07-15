#!/usr/bin/env python3
"""
load_trial_results.py — Accumulate audition verdicts in Postgres.

Handles both manifest formats:
  v1 (trials 1-4): keep (y/n) only
  v2 (trial 5+):   keep/ehh/cream tiers + diagnostic flags + WHOLE PACK rows

Auto-registration: if every file in a pack is marked cream=y AND the run's
manifest.json is provided, the pack's formula is stored in the `styles` table as
'cream-t{trial}-{combo}' (rename it later with register_style.py — only cream
formulas deserve storage, per Trell 2026-07-13).

Usage:
    python3 scripts/load_trial_results.py 5 data/trial_05_manifest_filled.csv \
        --run-manifest data/generation_run_trial_05.json
"""

import argparse
import csv
import json
import os
import re
from datetime import date
from pathlib import Path

import psycopg2

PGPORT = os.environ.get("PGPORT", "5431")

FLAGS = ["ehh", "cream", "fixable", "too_busy", "too_empty", "too_random",
         "too_repetitive", "robotic", "wrong_lane", "bad_landing",
         "gels", "rides", "song_worthy"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS trial_results (
    id        serial PRIMARY KEY,
    trial     int  NOT NULL,
    combo     text NOT NULL,
    file_kind text NOT NULL,          -- melody / bassline / drums / pack
    key       text,
    bpm       double precision,
    w_morning double precision,
    w_outthere double precision,
    w_sickomode double precision,
    keep      boolean,
    UNIQUE (trial, combo, file_kind)
);
""" + "\n".join(f"ALTER TABLE trial_results ADD COLUMN IF NOT EXISTS {f} boolean;"
                for f in FLAGS)


def yn(row, *names):
    for n in names:
        for col in (f"{n} (y/n)", n):
            if col in row and row[col].strip():
                return row[col].strip().lower() == "y"
    return None


def parse_weights(s):
    return {name.strip(): float(v) for name, v in re.findall(r"([a-z ]+?):([\d.]+)", s)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("trial", type=int)
    ap.add_argument("manifest_csv")
    ap.add_argument("--run-manifest", help="generation manifest.json for cream auto-registration")
    args = ap.parse_args()

    conn = psycopg2.connect(dbname="vive", port=PGPORT)
    with conn.cursor() as cur:
        cur.execute(SCHEMA)
        n = 0
        cream_by_combo = {}
        with Path(args.manifest_csv).open() as f:
            for r in csv.DictReader(f):
                w = parse_weights(r["weights"])
                if r["file"].strip() == "WHOLE PACK":
                    kind = "pack"
                else:
                    kind = r["file"].rsplit("- ", 1)[-1].replace(".mid", "").strip()
                flags = {name: yn(r, name.replace("_", " "), name) for name in FLAGS}
                combo_id = r["combo"].split()[-1]
                if kind in ("melody", "bassline", "drums"):
                    cream_by_combo.setdefault(combo_id, []).append(bool(flags["cream"]))
                cur.execute(f"""
                    INSERT INTO trial_results
                        (trial, combo, file_kind, key, bpm, w_morning, w_outthere,
                         w_sickomode, keep, {', '.join(FLAGS)})
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, {', '.join('%s' for _ in FLAGS)})
                    ON CONFLICT (trial, combo, file_kind) DO UPDATE SET
                        keep = EXCLUDED.keep,
                        {', '.join(f'{f} = EXCLUDED.{f}' for f in FLAGS)}
                    """, (args.trial, r["combo"], kind, r["key"], float(r["bpm"]),
                          w.get("morning", 0), w.get("out there", 0), w.get("sicko mode", 0),
                          yn(r, "keep")) + tuple(flags[f] for f in FLAGS))
                n += 1

        full_cream = [c for c, marks in cream_by_combo.items()
                      if len(marks) == 3 and all(marks)]
        if full_cream and args.run_manifest:
            run = json.loads(Path(args.run_manifest).read_text())
            for combo_id in full_cream:
                combo = next(c for c in run["combos"] if c["id"] == combo_id)
                recipe = {"generator": f"trial {args.trial}", "exemplar_combo": combo_id,
                          "weights": combo["weights"], "key": combo["key"],
                          "bpm": combo["bpm"], "bar_sources": combo.get("bar_sources"),
                          "melody_vocabulary": combo.get("melody_vocabulary"),
                          "run_manifest": args.run_manifest}
                cur.execute("""
                    INSERT INTO styles (name, created, description, verdict, recipe)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (name) DO UPDATE SET recipe = EXCLUDED.recipe
                    """, (f"cream-t{args.trial}-{combo_id}", date.today(),
                          "auto-registered: full cream-of-the-crop pack (rename me)",
                          "all 3 files cream", json.dumps(recipe)))
                print(f"  ★ full cream pack {combo_id} -> styles table as cream-t{args.trial}-{combo_id}")
        elif full_cream:
            print(f"  ! full cream packs {full_cream} found but no --run-manifest given; not registered")

        cur.execute("""
            SELECT trial, file_kind, count(*) FILTER (WHERE keep) || '/' || count(*)
            FROM trial_results WHERE file_kind <> 'pack'
            GROUP BY trial, file_kind ORDER BY trial, file_kind
        """)
        print(f"loaded {n} rows — keep rates so far:")
        for row in cur.fetchall():
            print("  trial", row[0], row[1], row[2])
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
