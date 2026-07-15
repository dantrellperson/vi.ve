#!/usr/bin/env python3
"""
generate_vibes_v4.py — Trial 04: Trial 03 with two melody fixes from feedback.

Trial 03 result: 17/24 kept (71%); melodies 6/8. Two criticisms to fix:
  1. Register spread too wide (pure-morning melody ran E4 up to D6).
     -> clamp_register(): every pitch folds into a +/-8 semitone window around
        the melody's median — max span 16 semitones, typically less.
  2. Notes bleed over and overlap other notes.
     -> the melody line is monophonized before writing: each note is trimmed
        at the next onset. Barline tails now sustain only until the next note
        speaks (mono-synth behavior), pickups stay intact.

SAME seeds as Trial 03 — every melody Trell liked comes back as the same line,
fixed. Bass/drums pipeline unchanged from v3 (anchor-song lock, register shape).

Output: ~/Music/Ableton/User Library/vibes forever/t4 v01..v08 + manifest.csv
Usage:  python3 scripts/generate_vibes_v4.py
"""

import csv
import json
import random
from datetime import date
from statistics import median

from generate_vibes import (BAR, N_BARS, DRUM_PITCH, OUT_DIR, CONFIG, DATA_DIR,
                            build_bar_library, collage, has_roll, inject_roll,
                            monophonize, transpose, semitone_shift, velocity,
                            write_midi)
from generate_vibes_v3 import (collage_locked, shape_bass_register, bar_means,
                               generate_melody_v3)

REGISTER_HALF_SPAN = 8   # semitones each side of the median -> max 16-semitone spread
LEAD_LANE = (64, 76)     # the melody's median must land between E4 and E5
                         # (Trell: E4 start was right, D6 was too high)


def clamp_register(notes):
    """Fold outlier pitches by octaves into a tight window around the melody median,
    then octave-shift the whole line so it sits in the lead lane (fixes tight-but-
    stratospheric lines, not just wide ones)."""
    if not notes:
        return notes
    center = median(p for _, p, _ in notes)
    out = []
    for (t, p, d) in notes:
        while p > center + REGISTER_HALF_SPAN:
            p -= 12
        while p < center - REGISTER_HALF_SPAN:
            p += 12
        out.append((t, p, d))
    center = median(p for _, p, _ in out)
    shift = 0
    while center + shift > LEAD_LANE[1]:
        shift -= 12
    while center + shift < LEAD_LANE[0]:
        shift += 12
    return [(t, p + shift, d) for (t, p, d) in out]


def main():
    packs = json.loads((DATA_DIR / "parsed_packs.json").read_text())["songs"]
    cfg = json.loads(CONFIG.read_text())
    lib = build_bar_library(packs)
    songs = list(packs)

    combos = []
    for i, s in enumerate(songs):
        combos.append({"id": f"v{i+1:02}", "weights": {x: (1.0 if x == s else 0.0) for x in songs},
                       "label": f"pure-{s.replace(' ', '')}"})
    for i in range(5):
        rng = random.Random(200 + i)
        raw = [rng.random() + 0.1 for _ in songs]
        total = sum(raw)
        w = {s: round(r / total, 2) for s, r in zip(songs, raw)}
        combos.append({"id": f"v{i+4:02}", "weights": w,
                       "label": " ".join(f"{s.split()[0][:3]}{int(w[s]*100)}" for s in songs)})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    for combo in combos:
        rng = random.Random(9200 + int(combo["id"][1:]))      # trial-3 seeds: same DNA
        mel_rng = random.Random(9300 + int(combo["id"][1:]))
        weights = {s: w for s, w in combo["weights"].items() if w > 0}

        target_key = packs[rng.choices(list(weights), list(weights.values()))[0]]["key"]
        bpm = round(sum(packs[s]["bpm"] * w for s, w in weights.items()), 2)

        folder = OUT_DIR / f"t4 {combo['id']} {combo['label']}"
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
        write_midi(folder / f"t4 {combo['id']} - drums.mid", [("drums", 9, drum_notes)], bpm)

        bass = []
        for bar_i in range(N_BARS):
            bar_notes = [(t, p, d) for (t, p, d) in locked["bass"]
                         if bar_i * BAR <= t < (bar_i + 1) * BAR]
            bass.extend(transpose(bar_notes, semitone_shift(packs[prov[bar_i]]["key"], target_key)))
        bass = shape_bass_register(monophonize(bass), rng)
        write_midi(folder / f"t4 {combo['id']} - bassline.mid",
                   [("bassline", 0, [(t, p, d, velocity("bass", t % BAR, cfg, rng))
                                     for (t, p, d) in bass])], bpm)

        melody, winner = generate_melody_v3(packs, weights, target_key, mel_rng)
        melody = monophonize(clamp_register(melody))          # the two trial-4 fixes
        write_midi(folder / f"t4 {combo['id']} - melody.mid",
                   [("melody", 0, [(t, p, d, velocity("melody", t % BAR, cfg, mel_rng))
                                   for (t, p, d) in melody])], bpm)
        prov_log["melody"] = f"grammar-v4 (v3 line, register-clamped + mono), vocabulary = {winner}"

        pitches = [p for _, p, _ in melody]
        span = f"{min(pitches)}-{max(pitches)} (span {max(pitches) - min(pitches)})" if pitches else "-"
        bmeans = bar_means(bass)
        manifest.append({"id": combo["id"], "label": combo["label"], "trial": 4,
                         "weights": combo["weights"], "key": target_key, "bpm": bpm,
                         "melody_vocabulary": winner, "melody_register": span,
                         "bass_register_by_bar": " ".join(f"{bmeans.get(b, 0):.0f}" for b in range(N_BARS)),
                         "bar_sources": prov_log})
        print(f"t4 {combo['id']}  {combo['label']:<24} melody register {span}")

    (OUT_DIR / "manifest.json").write_text(json.dumps(
        {"generated": str(date.today()), "trial": 4, "combos": manifest}, indent=1))
    with (OUT_DIR / "manifest.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["combo", "file", "key", "bpm", "weights", "keep (y/n)"])
        for m in manifest:
            for kind in ("melody", "bassline", "drums"):
                w.writerow([f"t4 {m['id']}", f"t4 {m['id']} - {kind}.mid", m["key"], m["bpm"],
                            " ".join(f"{s}:{v}" for s, v in m["weights"].items()), ""])
    print(f"\n{len(manifest) * 3} files in {OUT_DIR} — mark keepers in manifest.csv")


if __name__ == "__main__":
    main()
