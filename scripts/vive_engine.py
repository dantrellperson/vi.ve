#!/usr/bin/env python3
"""
vive_engine.py — the callable API for vi.ve generation. First brick of the
future `vive` Python package (and, one day, the AI assistant producer bot).

Wraps the established riding-trap ruleset (trial 08, generate_vibes_v8) behind
three functions a notebook can drive:

    packs, cfg, lib = load_context()
    combos = random_combos(n=8)                    # explore new weight territory
    combos = combos_from_style("riding trap", n=4) # rerun a registered style's weights
    manifest = run_trial(9, combos)                # -> MIDI files + manifest v2 + archive

run_trial writes:
    ~/Music/Ableton/User Library/vibes forever/t{trial} v01../  (melody, bassline, drums)
    .../manifest.csv   (v2: keep/ehh/cream + diagnostics -> grade it)
    .../manifest.json  (full provenance)
    vi.ve/data/generation_run_trial_{trial:02}.json  (archive, needed for cream auto-registration)

After grading, load verdicts (and auto-register full-cream packs) with:
    python3 scripts/load_trial_results.py {trial} data/trial_{trial:02}_manifest_filled.csv \
        --run-manifest data/generation_run_trial_{trial:02}.json
"""

import json
import os
import random
from datetime import date
from pathlib import Path

from generate_vibes import (BAR, DRUM_PITCH, OUT_DIR, CONFIG, DATA_DIR,
                            velocity, write_midi, build_bar_library)
from generate_vibes_v3 import bar_means
from generate_vibes_v8 import build_candidate, bar_slice, N_CANDIDATES
from trial_manifest import write_manifest_csv

PGPORT = os.environ.get("PGPORT", "5431")
N_BARS = 4

NOTE_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]


def note_name(p):
    """Ableton naming: MIDI 60 = C3."""
    return NOTE_NAMES[p % 12] + str(p // 12 - 2)


def load_context():
    packs = json.loads((DATA_DIR / "parsed_packs.json").read_text())["songs"]
    cfg = json.loads(CONFIG.read_text())
    return packs, cfg, build_bar_library(packs)


def next_trial_number():
    """Next trial = 1 + highest archived generation run."""
    runs = sorted(DATA_DIR.glob("generation_run_trial_*.json"))
    if not runs:
        return 1
    return max(int(p.stem.rsplit("_", 1)[-1]) for p in runs) + 1


def random_combos(n=8, seed_base=None, songs=("morning", "out there", "sicko mode")):
    """Fresh weighted dice — new map territory each run (seed_base varies by trial)."""
    seed_base = seed_base if seed_base is not None else random.randrange(10_000)
    combos = []
    for i in range(n):
        rng = random.Random(seed_base + i)
        raw = [rng.random() + 0.1 for _ in songs]
        total = sum(raw)
        w = {s: round(r / total, 2) for s, r in zip(songs, raw)}
        combos.append({"id": f"v{i+1:02}", "weights": w,
                       "label": " ".join(f"{s.split()[0][:3]}{int(w[s]*100)}" for s in songs)})
    return combos, seed_base


def combos_from_style(style_name, n=4):
    """Pull a registered style's weights from Postgres; n combos = n dice rolls of it."""
    import psycopg2
    conn = psycopg2.connect(dbname="vive", port=PGPORT)
    with conn.cursor() as cur:
        cur.execute("SELECT recipe->'weights' FROM styles WHERE name = %s", (style_name,))
        row = cur.fetchone()
    conn.close()
    if not row or not isinstance(row[0], dict):
        raise ValueError(f"style '{style_name}' has no stored weight dict")
    w = row[0]
    return [{"id": f"v{i+1:02}", "weights": w,
             "label": f"{style_name.replace(' ', '')}-roll{i+1}"} for i in range(n)]


def run_trial(trial, combos=None, n_combos=8, n_candidates=N_CANDIDATES, seed_base=None):
    """Generate a full trial: melody/bassline/drums per combo, best-of-N candidates,
    manifest v2 for grading. Returns the manifest (list of combo dicts)."""
    packs, cfg, lib = load_context()
    if combos is None:
        combos, seed_base = random_combos(n_combos, seed_base)
    gen_seed = seed_base if seed_base is not None else 11_000 + trial * 100

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    for idx, combo in enumerate(combos):
        weights = {s: w for s, w in combo["weights"].items() if w > 0}
        bpm = round(sum(packs[s]["bpm"] * w for s, w in weights.items()), 2)

        candidates = [build_candidate(packs, lib, cfg, weights,
                                      gen_seed + idx * 41 + k,
                                      gen_seed + 5_000 + idx * 41 + k)
                      for k in range(n_candidates)]
        best = max(candidates, key=lambda c: c["score"])

        folder = OUT_DIR / f"t{trial} {combo['id']} {combo['label']}"
        folder.mkdir(exist_ok=True)
        rng, mel_rng = best["rng"], best["mel_rng"]

        drum_notes = [(t, DRUM_PITCH["kick"], min(d, 200), velocity("kick", t % BAR, cfg, rng))
                      for (t, _, d) in best["kick"]]
        prov_log = {"kick+bass (locked)": best["prov"]}
        for role, (notes, p) in best["drums_extra"].items():
            prov_log[role] = p
            drum_notes += [(t, DRUM_PITCH[role], min(d, 200), velocity(role, t % BAR, cfg, rng))
                           for (t, _, d) in notes]
        write_midi(folder / f"t{trial} {combo['id']} - drums.mid", [("drums", 9, drum_notes)], bpm)
        write_midi(folder / f"t{trial} {combo['id']} - bassline.mid",
                   [("bassline", 0, [(t, p, d, velocity("bass", t % BAR, cfg, rng))
                                     for (t, p, d) in best["bass"]])], bpm)
        write_midi(folder / f"t{trial} {combo['id']} - melody.mid",
                   [("melody", 0, [(t, p, d, velocity("melody", t % BAR, cfg, mel_rng))
                                   for (t, p, d) in best["melody"]])], bpm)
        prov_log["melody"] = f"vocabulary = {best['melody_vocab']}"

        bar1 = sorted(bar_slice(best["bass"], 0))
        manifest.append({"id": combo["id"], "label": combo["label"], "trial": trial,
                         "weights": combo["weights"], "key": best["key"], "bpm": bpm,
                         "melody_vocabulary": best["melody_vocab"],
                         "candidate_seed": best["seed"], "chosen_score": best["score"],
                         "candidate_scores": [c["score"] for c in candidates],
                         "bass_bar1_notes": [note_name(p) for _, p, _ in bar1],
                         "bass_last_note": note_name(sorted(best["bass"])[-1][1]) if best["bass"] else "-",
                         "bar_sources": prov_log})

    run = {"generated": str(date.today()), "trial": trial, "combos": manifest}
    (OUT_DIR / "manifest.json").write_text(json.dumps(run, indent=1))
    write_manifest_csv(OUT_DIR / "manifest.csv", f"t{trial}", manifest)
    (DATA_DIR / f"generation_run_trial_{trial:02}.json").write_text(json.dumps(run, indent=1))
    return manifest
