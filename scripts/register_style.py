#!/usr/bin/env python3
"""
register_style.py — Save a named style Trell discovers while auditioning generated packs.

The `styles` table stores the style name plus a jsonb `recipe` that lets the style be
recreated without re-explaining: song weights, target key, bpm, generator version, and
the exact per-bar source map of the exemplar combo (from the generation run manifest).

Usage:
    python3 scripts/register_style.py "riding trap" v04 data/generation_run_2026-07-13.json \
        --description "..." --verdict "..."
    python3 scripts/register_style.py --list
"""

import argparse
import json
import os
from datetime import date
from pathlib import Path

import psycopg2

PGPORT = os.environ.get("PGPORT", "5431")

SCHEMA = """
CREATE TABLE IF NOT EXISTS styles (
    id          serial PRIMARY KEY,
    name        text   UNIQUE NOT NULL,
    created     date   NOT NULL,
    description text,
    verdict     text,
    recipe      jsonb  NOT NULL
);
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("name", nargs="?", help="style name, e.g. 'riding trap'")
    ap.add_argument("combo", nargs="?", help="exemplar combo id, e.g. v04")
    ap.add_argument("run_manifest", nargs="?", help="generation run json with the combo")
    ap.add_argument("--description", default="")
    ap.add_argument("--verdict", default="")
    ap.add_argument("--list", action="store_true", help="show registered styles")
    args = ap.parse_args()

    conn = psycopg2.connect(dbname="vive", port=PGPORT)
    with conn.cursor() as cur:
        cur.execute(SCHEMA)
        if args.list or not args.name:
            cur.execute("SELECT name, created, verdict, recipe->>'exemplar_combo' FROM styles")
            for row in cur.fetchall():
                print(row)
            conn.commit()
            return

        run = json.loads(Path(args.run_manifest).read_text())
        combo = next(c for c in run["combos"] if c["id"] == args.combo)
        recipe = {
            "generator": "generate_vibes.py v1 (bar collage)",
            "exemplar_combo": combo["id"],
            "weights": combo["weights"],
            "key": combo["key"],
            "bpm": combo["bpm"],
            "bar_sources": combo["bar_sources"],
            "velocity_model": "config/style_defaults.json",
            "run_manifest": args.run_manifest,
        }
        cur.execute("""
            INSERT INTO styles (name, created, description, verdict, recipe)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (name) DO UPDATE SET description = EXCLUDED.description,
                verdict = EXCLUDED.verdict, recipe = EXCLUDED.recipe
            """, (args.name, date.today(), args.description, args.verdict,
                  json.dumps(recipe)))
        print(f"Registered style '{args.name}' (exemplar {combo['id']})")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
