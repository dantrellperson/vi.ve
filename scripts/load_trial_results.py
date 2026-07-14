#!/usr/bin/env python3
"""
load_trial_results.py — Accumulate audition verdicts (the keep marks) in Postgres.

Table `trial_results`: one row per auditioned file with the combo's weights unpacked
into columns. This is the training signal — over trials, keep-rate vs. weights is
what teaches the style maps Trell's taste.

Usage:
    python3 scripts/load_trial_results.py 1 data/trial_01_manifest_filled.csv
    python3 scripts/load_trial_results.py 2 data/trial_02_manifest_filled.csv
"""

import argparse
import csv
import os
from pathlib import Path

import psycopg2

PGPORT = os.environ.get("PGPORT", "5431")

SCHEMA = """
CREATE TABLE IF NOT EXISTS trial_results (
    id        serial PRIMARY KEY,
    trial     int  NOT NULL,
    combo     text NOT NULL,
    file_kind text NOT NULL,          -- melody / bassline / drums
    key       text,
    bpm       double precision,
    w_morning double precision,
    w_outthere double precision,
    w_sickomode double precision,
    keep      boolean NOT NULL,
    UNIQUE (trial, combo, file_kind)
);
"""


def parse_weights(s):
    out = {}
    for chunk in s.split(":"):
        pass
    # format: "morning:0.12 out there:0.24 sicko mode:0.64" — song names contain spaces,
    # so split on the numbers instead
    import re
    for name, val in re.findall(r"([a-z ]+?):([\d.]+)", s):
        out[name.strip()] = float(val)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("trial", type=int)
    ap.add_argument("manifest_csv")
    args = ap.parse_args()

    conn = psycopg2.connect(dbname="vive", port=PGPORT)
    with conn.cursor() as cur:
        cur.execute(SCHEMA)
        n = 0
        with Path(args.manifest_csv).open() as f:
            for r in csv.DictReader(f):
                w = parse_weights(r["weights"])
                kind = r["file"].rsplit("- ", 1)[-1].replace(".mid", "").strip()
                keep = r["keep (y/n)"].strip().lower() == "y"
                cur.execute("""
                    INSERT INTO trial_results
                        (trial, combo, file_kind, key, bpm, w_morning, w_outthere, w_sickomode, keep)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (trial, combo, file_kind) DO UPDATE SET keep = EXCLUDED.keep
                    """, (args.trial, r["combo"], kind, r["key"], float(r["bpm"]),
                          w.get("morning", 0), w.get("out there", 0), w.get("sicko mode", 0),
                          keep))
                n += 1
        cur.execute("""
            SELECT trial, file_kind, count(*) FILTER (WHERE keep) || '/' || count(*)
            FROM trial_results GROUP BY trial, file_kind ORDER BY trial, file_kind
        """)
        print(f"loaded {n} rows — keep rates so far:")
        for row in cur.fetchall():
            print("  trial", row[0], row[1], row[2])
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
