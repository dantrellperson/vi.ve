#!/usr/bin/env python3
"""
load_postgres.py — Store vi.ve analysis output in local Postgres.

Creates database `vive` (if missing) with two tables:

  metrics         long format per the mindDump: song / style / scope / metric / value,
                  plus run_date + source_file so old analysis runs are kept
  style_profiles  one jsonb row per run_date — the full style_profile.json history

Loads : data/intra_pack_metrics.csv, data/cross_song_trends.csv, data/style_profile.json
Re-running on the same day upserts (no duplicate rows per run_date).

Connection: uses libpq defaults — env vars (PGHOST/PGUSER/PGPASSWORD) and ~/.pgpass.
No credentials live in this script.

Usage:
    python3 scripts/load_postgres.py            # create schema + load everything
    python3 scripts/load_postgres.py --query    # just print a sanity-check summary
"""

import argparse
import csv
import json
from datetime import date
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CSV_FILES = ["intra_pack_metrics.csv", "cross_song_trends.csv"]
PROFILE_JSON = DATA_DIR / "style_profile.json"
DB_NAME = "vive"

SCHEMA = """
CREATE TABLE IF NOT EXISTS metrics (
    id          serial PRIMARY KEY,
    run_date    date   NOT NULL,
    song        text   NOT NULL,
    style       text   NOT NULL,
    scope       text   NOT NULL,
    metric      text   NOT NULL,
    value_num   double precision,
    value_text  text,
    source_file text   NOT NULL,
    UNIQUE (run_date, song, scope, metric, source_file)
);
CREATE INDEX IF NOT EXISTS metrics_metric_idx ON metrics (metric);
CREATE INDEX IF NOT EXISTS metrics_song_idx   ON metrics (song);

CREATE TABLE IF NOT EXISTS style_profiles (
    run_date date PRIMARY KEY,
    profile  jsonb NOT NULL
);
"""


def ensure_database():
    """Create the vive database if it doesn't exist (connects to 'postgres' to do it)."""
    conn = psycopg2.connect(dbname="postgres")
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
        if not cur.fetchone():
            cur.execute(f'CREATE DATABASE "{DB_NAME}"')
            print(f"Created database {DB_NAME}")
    conn.close()


def load(conn):
    today = date.today()
    with conn.cursor() as cur:
        cur.execute(SCHEMA)

        total = 0
        for name in CSV_FILES:
            path = DATA_DIR / name
            if not path.exists():
                print(f"  ! missing {path}, skipping")
                continue
            rows = []
            with path.open() as f:
                for r in csv.DictReader(f):
                    try:
                        num, txt = float(r["value"]), None
                    except ValueError:
                        num, txt = None, r["value"]
                    rows.append((today, r["song"], r["style"], r["scope"],
                                 r["metric"], num, txt, name))
            execute_values(cur, """
                INSERT INTO metrics
                    (run_date, song, style, scope, metric, value_num, value_text, source_file)
                VALUES %s
                ON CONFLICT (run_date, song, scope, metric, source_file)
                DO UPDATE SET value_num = EXCLUDED.value_num,
                              value_text = EXCLUDED.value_text,
                              style = EXCLUDED.style
                """, rows)
            total += len(rows)
            print(f"  loaded {len(rows):>4} rows from {name}")

        if PROFILE_JSON.exists():
            cur.execute("""
                INSERT INTO style_profiles (run_date, profile) VALUES (%s, %s)
                ON CONFLICT (run_date) DO UPDATE SET profile = EXCLUDED.profile
                """, (today, PROFILE_JSON.read_text()))
            print(f"  loaded style profile for {today}")

    conn.commit()
    print(f"Done — {total} metric rows upserted for run_date {today}")


def summary(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*), count(DISTINCT metric), count(DISTINCT run_date) FROM metrics")
        n, m, runs = cur.fetchone()
        print(f"metrics: {n} rows, {m} distinct metrics, {runs} analysis run(s)")
        cur.execute("""
            SELECT song, count(*) FROM metrics GROUP BY song ORDER BY song
        """)
        for song, c in cur.fetchall():
            print(f"  {song:<12} {c} rows")
        cur.execute("""
            SELECT scope, metric, value_num FROM metrics
            WHERE metric LIKE 'ktb_co_hit%' AND run_date = (SELECT max(run_date) FROM metrics)
            ORDER BY scope
        """)
        print("sanity check — kick<->bass co-hit rates:")
        for scope, metric, v in cur.fetchall():
            print(f"  {scope:<30} {v}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--query", action="store_true", help="print summary only, load nothing")
    args = ap.parse_args()

    ensure_database()
    conn = psycopg2.connect(dbname=DB_NAME)
    if not args.query:
        load(conn)
    summary(conn)
    conn.close()


if __name__ == "__main__":
    main()
