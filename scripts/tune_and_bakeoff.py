#!/usr/bin/env python3
"""
tune_and_bakeoff.py — harness-driven tuning round 1 (no ears required).

Stage 1  KNOB GRID-SEARCH: transcribe the worst clean stem (keys, F1 0.34,
         split_rate 3.07) under a grid of Basic Pitch thresholds, scored
         against ground truth. Winner = the config that kills over-segmentation
         without losing recall. Validated on the horn stem too.

Stage 2  SEPARATOR BAKE-OFF: re-run the full-pipeline test with
         htdemucs (baseline, cached) vs htdemucs_6s (6 stems: adds piano+guitar)
         vs htdemucs_ft (fine-tuned, 4x slower, cleaner). Scoreboard: the horn
         (0.72 clean -> 0.02 through baseline) and drum-stem recall (0.53).
         Melodic parts are scored against their BEST-matching stem (upper bound
         on what each separator preserves).

Everything is scored with transcription_eval; results append to
data/tuning_round_01.json as stages finish.
"""

import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
import librosa

sys.path.append(str(Path(__file__).resolve().parent))
import audio_to_midi as a2m
from transcription_eval import (GT_DIR, discover, load_gt_midi, eval_melodic,
                                eval_drums, predict_onsets, DRUM_WORDS)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUT = DATA_DIR / "tuning_round_01.json"
CROP_S = 170          # keys clip ends ~146s into the bounce; crop speeds the grid

results = {"stage1_grid": {}, "stage2_bakeoff": {}}


def save():
    OUT.write_text(json.dumps(results, indent=1))


def crop(wav_path, seconds, tmpdir):
    y, sr = librosa.load(str(wav_path), sr=None, mono=True, duration=seconds)
    out = Path(tmpdir) / (Path(wav_path).stem + "_crop.wav")
    sf.write(out, y, sr)
    return out


def predict_melodic(wav_path):
    notes = a2m.transcribe_stem(wav_path)
    return (np.array([n[0] for n in notes]), np.array([n[2] for n in notes]))


def main():
    song = discover(GT_DIR)
    bpm = song["bpm"]
    gts = {p: load_gt_midi(f["midi"], bpm) for p, f in song["pairs"].items()}

    # ---------------- stage 1: grid search on keys, validate on horn
    print("STAGE 1 — Basic Pitch knob grid (scored on 'keys magic'):", flush=True)
    with tempfile.TemporaryDirectory() as td:
        keys_crop = crop(song["pairs"]["keys magic"]["bounce"], CROP_S, td)
        horn_crop = crop(song["pairs"]["synthy horn"]["bounce"], CROP_S, td)

        grid = [(ot, ft, mnl)
                for ot in (0.5, 0.65, 0.8)
                for ft in (0.3, 0.45)
                for mnl in (60, 120, 200)]
        rows = []
        for ot, ft, mnl in grid:
            a2m.CONFIG.update(onset_threshold=ot, frame_threshold=ft, min_note_len_ms=mnl)
            r = eval_melodic(gts["keys magic"], predict_melodic(keys_crop), bpm)
            rows.append({"onset": ot, "frame": ft, "min_len": mnl, **r})
            print(f"  ot={ot} ft={ft} min={mnl:>3}  f1={r['f1']:.2f} "
                  f"prec={r['precision']:.2f} rec={r['recall']:.2f} split={r['split_rate']}",
                  flush=True)
        best = max(rows, key=lambda r: r["f1"])
        results["stage1_grid"] = {"rows": rows, "best": best}
        save()

        a2m.CONFIG.update(onset_threshold=best["onset"], frame_threshold=best["frame"],
                          min_note_len_ms=best["min_len"])
        horn_r = eval_melodic(gts["synthy horn"], predict_melodic(horn_crop), bpm)
        results["stage1_grid"]["horn_with_best"] = horn_r
        print(f"  BEST: {best['onset']}/{best['frame']}/{best['min_len']} "
              f"keys f1 {best['f1']}  |  horn with best: f1 {horn_r['f1']}", flush=True)
        save()

    # ---------------- stage 2: separator bake-off (best knobs applied)
    drum_parts = [p for p in gts if set(p.split()) & DRUM_WORDS]
    mel_parts = [p for p in gts if p not in drum_parts]
    gt_drums_all = np.sort(np.concatenate([gts[p][0] for p in drum_parts]))
    drums_span = max(gts[p][2] for p in drum_parts)

    for model in ("htdemucs", "htdemucs_6s", "htdemucs_ft"):
        print(f"\nSTAGE 2 — separator: {model}", flush=True)
        a2m.CONFIG["demucs_model"] = model
        cache = GT_DIR / "_stems_cache" / model / song["mix"].stem
        if not cache.exists() or not list(cache.glob("*.wav")):
            print(f"  separating (slow, CPU)…", flush=True)
            a2m.separate_stems(song["mix"], GT_DIR / "_stems_cache")
        stems = {p.stem: p for p in cache.glob("*.wav")}
        model_res = {}

        preds = {s: predict_melodic(p) for s, p in stems.items() if s != "drums"}
        for part in mel_parts:
            scored = {s: eval_melodic(gts[part], pred, bpm) for s, pred in preds.items()}
            stem_best, r = max(scored.items(), key=lambda kv: (kv[1]["f1"], kv[1]["onset_f1"]))
            model_res[part] = {"best_stem": stem_best, **r}
            print(f"  {part:<14} best stem: {stem_best:<8} f1={r['f1']:.2f} "
                  f"onset_f1={r.get('onset_f1', 0):.2f}", flush=True)

        if "drums" in stems:
            r = eval_drums((gt_drums_all, None, drums_span), predict_onsets(stems["drums"]), bpm)
            model_res["all drums (union)"] = r
            print(f"  drums union    f1={r['f1']:.2f} recall={r['recall']:.2f}", flush=True)

        results["stage2_bakeoff"][model] = model_res
        save()

    print("\ndone — full results in", OUT, flush=True)


if __name__ == "__main__":
    main()
