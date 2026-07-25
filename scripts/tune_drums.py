#!/usr/bin/env python3
"""
tune_drums.py — grid-search the drum classifier against the ground-truth harness.

Tuning round 1 optimised Basic Pitch knobs against a metric that could not see
drum lane errors (union onsets: 0.57, while Trell graded the same packs 0/5).
This tunes the per-band share thresholds against per-class macro F1 instead —
the metric that can tell a kick from a hi-hat.

Cheap by construction: Demucs stems come from the harness cache and the onset
envelopes are computed ONCE per stem, so each grid point is just re-thresholding.

Usage:
    python3 scripts/tune_drums.py              # sweep, print top 10, write JSON
"""

import itertools
import json
import sys
from pathlib import Path

import numpy as np

sys.path.append(str(Path(__file__).resolve().parent))
from audio_to_midi import CONFIG, drum_envelopes, pick_drum_hits
from transcription_eval import (GT_DIR, DRUM_WORDS, discover, load_gt_midi,
                                drum_class_of, eval_drums_per_class)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GRID = {
    "drum_share_kick":  [0.30, 0.35, 0.40, 0.45, 0.50],
    "drum_share_snare": [0.02, 0.05, 0.08, 0.12, 0.15, 0.20],
    "drum_share_hihat": [0.02, 0.05, 0.10, 0.15, 0.20, 0.25],
}


def main():
    song = discover(GT_DIR)
    bpm = song["bpm"]

    gt_by_class, span = {}, 0.0
    for part, files in song["pairs"].items():
        if not set(part.split()) & DRUM_WORDS:
            continue
        cls = drum_class_of(part)
        if not cls:
            continue
        onsets, _, part_span = load_gt_midi(files["midi"], bpm)
        gt_by_class.setdefault(cls, []).append(onsets)
        span = max(span, part_span)
    gt_by_class = {c: np.sort(np.concatenate(v)) for c, v in gt_by_class.items()}
    print(f"ground truth lanes: { {c: len(v) for c, v in gt_by_class.items()} }")

    stem_dir = GT_DIR / "_stems_cache" / CONFIG["demucs_model"] / song["mix"].stem
    drum_stem = next(iter(stem_dir.glob("drums.wav")), None)
    if drum_stem is None:
        raise SystemExit(f"no cached drum stem in {stem_dir} — run transcription_eval.py first")

    print(f"computing envelopes once from {drum_stem.name}…")
    env_pack = drum_envelopes(drum_stem)

    keys = list(GRID)
    combos = list(itertools.product(*(GRID[k] for k in keys)))
    print(f"sweeping {len(combos)} threshold combinations…")

    results = []
    for values in combos:
        CONFIG.update(dict(zip(keys, values)))
        pred = {c: np.array([t for t, _ in h])
                for c, h in pick_drum_hits(env_pack).items()}
        r = eval_drums_per_class(gt_by_class, pred, bpm, span)
        results.append({**dict(zip(keys, values)), "macro_f1": r["macro_f1"],
                        "per_class": {c: m["f1"] for c, m in r["per_class"].items()}})

    results.sort(key=lambda r: -r["macro_f1"])
    print("\ntop 10 by per-class macro F1:")
    print(f"  {'kick':>6} {'snare':>6} {'hihat':>6} | {'macro':>6} | per-lane F1")
    for r in results[:10]:
        pc = r["per_class"]
        print(f"  {r['drum_share_kick']:6.2f} {r['drum_share_snare']:6.2f} "
              f"{r['drum_share_hihat']:6.2f} | {r['macro_f1']:6.2f} | "
              f"kick {pc.get('kick', 0):.2f}  snare {pc.get('snare', 0):.2f}  "
              f"hihat {pc.get('hihat', 0):.2f}")

    out = DATA_DIR / "drum_tuning_round_02.json"
    out.write_text(json.dumps({"grid": GRID, "results": results}, indent=1))
    print(f"\nbest: {results[0]}")
    print(f"wrote {out}")
    return results


if __name__ == "__main__":
    main()
