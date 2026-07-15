#!/usr/bin/env python3
"""
generate_vibes_v5.py — Trial 05: same engine as Trial 04, experimental combo design,
manifest v2 (keep/ehh/cream tiers + diagnostic flags).

Engine unchanged (79% keep rate in trial 04) — this trial changes WHAT we test:

  THE v04 EXPERIMENT: the weight recipe mor12/out24/sic64 went 0-for-9 files across
  trials 2-4 while its neighbors passed. Was it the weights or the dice?
    v01 + v02 = v04's exact weights, two DIFFERENT random seeds.
    v03       = v05's weights (0-for-6 in trials 2-3), fresh seed.
  If both v01 and v02 fail again -> the weight mixture itself is cursed and becomes
  a no-go region of the map. If they pass -> it was per-run dice, not the recipe.

  v04-v08 = five brand-new random weight draws (unexplored map territory).

No pure controls this round — the engine has earned trust; every slot explores.

Output: ~/Music/Ableton/User Library/vibes forever/t5 v01..v08 + manifest.csv (v2)
Usage:  python3 scripts/generate_vibes_v5.py
"""

import json
import random
from datetime import date

from generate_vibes import (BAR, N_BARS, DRUM_PITCH, OUT_DIR, CONFIG, DATA_DIR,
                            build_bar_library, collage, has_roll, inject_roll,
                            monophonize, transpose, semitone_shift, velocity,
                            write_midi)
from generate_vibes_v3 import (collage_locked, shape_bass_register, bar_means,
                               generate_melody_v3)
from generate_vibes_v4 import clamp_register
from trial_manifest import write_manifest_csv

V04_WEIGHTS = {"morning": 0.12, "out there": 0.24, "sicko mode": 0.64}
V05_WEIGHTS = {"morning": 0.24, "out there": 0.61, "sicko mode": 0.15}


def build_combos(songs):
    combos = [
        {"id": "v01", "weights": V04_WEIGHTS, "label": "v04weights-rerun-a"},
        {"id": "v02", "weights": V04_WEIGHTS, "label": "v04weights-rerun-b"},
        {"id": "v03", "weights": V05_WEIGHTS, "label": "v05weights-rerun"},
    ]
    for i in range(5):
        rng = random.Random(300 + i)                 # fresh draws, new map territory
        raw = [rng.random() + 0.1 for _ in songs]
        total = sum(raw)
        w = {s: round(r / total, 2) for s, r in zip(songs, raw)}
        combos.append({"id": f"v{i+4:02}", "weights": w,
                       "label": " ".join(f"{s.split()[0][:3]}{int(w[s]*100)}" for s in songs)})
    return combos


def main():
    packs = json.loads((DATA_DIR / "parsed_packs.json").read_text())["songs"]
    cfg = json.loads(CONFIG.read_text())
    lib = build_bar_library(packs)

    combos = build_combos(list(packs))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    for idx, combo in enumerate(combos):
        # v01 vs v02: identical weights, deliberately different seeds
        rng = random.Random(9500 + idx * 7)
        mel_rng = random.Random(9600 + idx * 7)
        weights = {s: w for s, w in combo["weights"].items() if w > 0}

        target_key = packs[rng.choices(list(weights), list(weights.values()))[0]]["key"]
        bpm = round(sum(packs[s]["bpm"] * w for s, w in weights.items()), 2)

        folder = OUT_DIR / f"t5 {combo['id']} {combo['label']}"
        folder.mkdir(exist_ok=True)
        prov_log = {}

        locked, prov = collage_locked(("kick", "bass"), lib, weights, rng)
        prov_log["kick+bass (locked)"] = prov

        drum_notes = [(t, DRUM_PITCH["kick"], min(d, 200), velocity("kick", t % BAR, cfg, rng))
                      for (t, _, d) in locked["kick"]]
        for role in ("snare", "clap", "hat"):
            notes, p = collage(role, lib, weights, rng)
            prov_log[role] = p
            if role == "hat" and notes and not has_roll(notes):
                notes = inject_roll(notes, cfg, rng)
            drum_notes += [(t, DRUM_PITCH[role], min(d, 200), velocity(role, t % BAR, cfg, rng))
                           for (t, _, d) in notes]
        write_midi(folder / f"t5 {combo['id']} - drums.mid", [("drums", 9, drum_notes)], bpm)

        bass = []
        for bar_i in range(N_BARS):
            bar_notes = [(t, p, d) for (t, p, d) in locked["bass"]
                         if bar_i * BAR <= t < (bar_i + 1) * BAR]
            bass.extend(transpose(bar_notes, semitone_shift(packs[prov[bar_i]]["key"], target_key)))
        bass = shape_bass_register(monophonize(bass), rng)
        write_midi(folder / f"t5 {combo['id']} - bassline.mid",
                   [("bassline", 0, [(t, p, d, velocity("bass", t % BAR, cfg, rng))
                                     for (t, p, d) in bass])], bpm)

        melody, winner = generate_melody_v3(packs, weights, target_key, mel_rng)
        melody = monophonize(clamp_register(melody))
        write_midi(folder / f"t5 {combo['id']} - melody.mid",
                   [("melody", 0, [(t, p, d, velocity("melody", t % BAR, cfg, mel_rng))
                                   for (t, p, d) in melody])], bpm)
        prov_log["melody"] = f"grammar-v4, vocabulary = {winner}"

        bmeans = bar_means(bass)
        manifest.append({"id": combo["id"], "label": combo["label"], "trial": 5,
                         "weights": combo["weights"], "key": target_key, "bpm": bpm,
                         "melody_vocabulary": winner,
                         "bass_register_by_bar": " ".join(f"{bmeans.get(b, 0):.0f}"
                                                          for b in range(N_BARS)),
                         "bar_sources": prov_log})
        print(f"t5 {combo['id']}  {combo['label']:<22} key {target_key:<4} "
              f"melody={winner:<11} bass: {manifest[-1]['bass_register_by_bar']}")

    (OUT_DIR / "manifest.json").write_text(json.dumps(
        {"generated": str(date.today()), "trial": 5, "combos": manifest}, indent=1))
    write_manifest_csv(OUT_DIR / "manifest.csv", "t5", manifest)
    print(f"\n{len(manifest) * 3} files in {OUT_DIR}")
    print("manifest.csv is v2: keep/ehh/cream + diagnostics per file, gels/rides/song-worthy per pack")


if __name__ == "__main__":
    main()
