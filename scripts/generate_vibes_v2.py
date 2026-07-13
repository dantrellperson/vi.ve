#!/usr/bin/env python3
"""
generate_vibes_v2.py — Trial 02: grammar-based melody, collage bass/drums.

Trial 01 verdict: basslines + drums (bar collage) validated by ear — "Riding Trap."
Melodies rejected as channel surfing. Root cause (notebooks/trial_01_review.ipynb):
the melody pool's between-song spread is ~2x any other role, so whole-bar splicing
jumps register/density/space at every bar boundary.

Trial 02 changes ONLY the melody engine:
  - one register for the whole pattern (weighted pick of a source register)
  - one rhythmic MOTIF, developed across 4 bars (A / A' / B / A-resolve) —
    motif continuity is what bar collage destroyed
  - rhythm sampled from the weighted songs' melody IOI vocabulary
  - pitches walk a weighted scale-degree transition chain (natural minor),
    phrase starts on a chord tone, bar 4 resolves to root or 5th
  - density + space aimed at the melody target zone (sparse leads, NOT the
    30-notes/bar chord cloud that poisoned trial 1)
  - hand-feel: small timing deviation + default velocity model

Bass and drums reuse the trial-1 collage engine with the SAME seeds — the weight
combos are held constant so trial 2 vs trial 1 isolates the melody change.

Output: ~/Music/Ableton/User Library/vibes forever/t2 v01..v08 + manifest.csv (keep column)
Usage:  python3 scripts/generate_vibes_v2.py
"""

import csv
import json
import random
from datetime import date
from pathlib import Path

from generate_vibes import (BAR, N_BARS, PATTERN, TPQ, DRUM_PITCH, OUT_DIR, CONFIG,
                            DATA_DIR, build_bar_library, collage, has_roll, inject_roll,
                            monophonize, velocity, write_midi, key_pc)

MINOR = [0, 2, 3, 5, 7, 8, 10]          # natural minor scale degrees (semitones)
CHORD_TONES = [0, 3, 7]                  # phrase anchors: root, b3, 5th
STEP16 = TPQ // 4

# melody grammar sources = actual lead lines only; the dense chord cloud from
# "morning" is what poisoned trial 1, so it contributes pitch DNA but not density
MELODY_PARTS = {"melody", "keys", "chord progression"}
DENSITY_ZONE = (5, 9)                    # onsets/bar target (sparse lead lane)
SPACE_MIN = 0.25                         # >= 25% of the bar stays empty


def melody_vocab(packs, weights):
    """Weighted IOI (in 16ths) and scale-degree-step vocabularies from the sources."""
    iois, degree_steps, registers = [], [], []
    for song, w in weights.items():
        if w <= 0:
            continue
        root = key_pc(packs[song]["key"])
        for p in packs[song]["parts"]:
            if p["part"] not in MELODY_PARTS or p["section"] not in ("both", "verse", "main"):
                continue
            line = monophonize([(n["start_tick"], n["pitch"], n["duration_ticks"])
                                for n in p["notes"]])
            if len(line) < 3:
                continue
            registers.append((sum(n[1] for n in line) / len(line), w))
            scale_of = {pc: i for i, pc in enumerate(MINOR)}
            degs = [scale_of.get((pitch - root) % 12) for _, pitch, _ in line]
            tpq = p["ticks_per_beat"]
            for a, b in zip(line, line[1:]):
                ioi = round((b[0] - a[0]) / (tpq / 4))
                if 1 <= ioi <= 8:
                    iois.append((ioi, w))
            for a, b in zip(degs, degs[1:]):
                if a is not None and b is not None:
                    step = b - a
                    if abs(step) <= 4:
                        degree_steps.append((step, w))
    return iois, degree_steps, registers


def weighted_sample(pool, rng):
    items = [x for x, _ in pool]
    weights = [w for _, w in pool]
    return rng.choices(items, weights)[0]


def make_motif_rhythm(iois, rng):
    """Onset positions (in 16ths) for one bar: start on the 1, fill <= 12 sixteenths,
    leaving the tail of the bar as guaranteed space. Anti-repetition rule: the same
    IOI more than twice in a row reads as an arpeggiator ("constant 8ths" is on the
    rejected list), so a third repeat gets one redraw."""
    positions, pos = [0], 0
    budget = rng.randint(*DENSITY_ZONE) - 1
    recent = []
    while budget > 0:
        ioi = weighted_sample(iois, rng)
        if len(recent) >= 2 and recent[-1] == recent[-2] == ioi:
            ioi = weighted_sample(iois, rng)      # one redraw to break the run
        recent.append(ioi)
        pos += ioi
        if pos > 16 * (1 - SPACE_MIN):
            break
        positions.append(pos)
        budget -= 1
    return positions


def degrees_for(rhythm, degree_steps, rng, start_choices=CHORD_TONES, resolve=False):
    scale_of = {pc: i for i, pc in enumerate(MINOR)}
    deg = scale_of[rng.choice(start_choices)]
    out = [deg]
    for _ in rhythm[1:]:
        deg = max(0, min(len(MINOR) * 2 - 1, deg + weighted_sample(degree_steps, rng)))
        out.append(deg)
    if resolve and out:
        out[-1] = scale_of[rng.choice([0, 7])]   # land on root or 5th
    return out


def to_pitches(degrees, root_pitch):
    return [root_pitch + (d // len(MINOR)) * 12 + MINOR[d % len(MINOR)] for d in degrees]


def generate_melody(packs, weights, target_key, rng):
    """Motif-driven 4-bar melody: A / A-varied / B / A-resolved. One register."""
    iois, degree_steps, registers = melody_vocab(packs, weights)
    if not iois or not degree_steps:
        return []
    center = weighted_sample(registers, rng)
    root_pitch = 12 * round((center - key_pc(target_key)) / 12) + key_pc(target_key)

    rhythm_a = make_motif_rhythm(iois, rng)
    rhythm_b = make_motif_rhythm(iois, rng)
    degs_a = degrees_for(rhythm_a, degree_steps, rng)

    bars = []
    for bar_i, (rhythm, degs) in enumerate([
        (rhythm_a, degs_a),                                            # A: the motif
        (rhythm_a, degs_a[:-1] + degrees_for(rhythm_a[-1:], degree_steps, rng)),  # A': new tail
        (rhythm_b, degrees_for(rhythm_b, degree_steps, rng, start_choices=[3, 7])),  # B: answer
        (rhythm_a, degrees_for(rhythm_a, degree_steps, rng, resolve=True)),          # A resolves
    ]):
        pitches = to_pitches(degs, root_pitch)
        for pos, pitch in zip(rhythm, pitches):
            tick = bar_i * BAR + pos * STEP16
            tick += rng.randint(-8, 8) if pos != 0 else 0    # hand feel (<= ~14 ms), 1 stays anchored
            next_i = rhythm.index(pos) + 1
            gap = (rhythm[next_i] - pos) * STEP16 if next_i < len(rhythm) else 4 * STEP16
            dur = min(max(STEP16, int(gap * rng.uniform(0.7, 0.95))), 4 * STEP16)
            bars.append((max(0, tick), pitch, dur))
    return bars


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
        rng = random.Random(200 + i)                    # same weight draws as trial 1
        raw = [rng.random() + 0.1 for _ in songs]
        total = sum(raw)
        w = {s: round(r / total, 2) for s, r in zip(songs, raw)}
        combos.append({"id": f"v{i+4:02}", "weights": w,
                       "label": " ".join(f"{s.split()[0][:3]}{int(w[s]*100)}" for s in songs)})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    for idx, combo in enumerate(combos):
        rng = random.Random(9000 + int(combo["id"][1:]))       # trial-1 seed: bass/drums repro
        mel_rng = random.Random(9100 + int(combo["id"][1:]))   # fresh seed for the new melody
        weights = {s: w for s, w in combo["weights"].items() if w > 0}

        target_key = packs[rng.choices(list(weights), list(weights.values()))[0]]["key"]
        bpm = round(sum(packs[s]["bpm"] * w for s, w in weights.items()), 2)

        folder = OUT_DIR / f"t2 {combo['id']} {combo['label']}"
        folder.mkdir(exist_ok=True)
        prov_log = {}

        drum_notes = []
        for role in ("kick", "snare", "clap", "hat"):
            notes, prov = collage(role, lib, weights, rng)
            prov_log[role] = prov
            if role == "hat" and notes and not has_roll(notes):
                notes = inject_roll(notes, cfg, rng)
            for (t, _, d) in notes:
                drum_notes.append((t, DRUM_PITCH[role], min(d, 200),
                                   velocity(role, t % BAR, cfg, rng)))
        write_midi(folder / f"t2 {combo['id']} - drums.mid", [("drums", 9, drum_notes)], bpm)

        notes, prov = collage("bass", lib, weights, rng)
        prov_log["bass"] = prov
        from generate_vibes import transpose, semitone_shift
        fixed = []
        for bar_i in range(N_BARS):
            bar_notes = [(t, p, d) for (t, p, d) in notes if bar_i * BAR <= t < (bar_i + 1) * BAR]
            if prov:
                bar_notes = transpose(bar_notes, semitone_shift(packs[prov[bar_i]]["key"], target_key))
            fixed.extend(bar_notes)
        bass_track = [(t, p, d, velocity("bass", t % BAR, cfg, rng))
                      for (t, p, d) in monophonize(fixed)]
        write_midi(folder / f"t2 {combo['id']} - bassline.mid", [("bassline", 0, bass_track)], bpm)

        melody = generate_melody(packs, weights, target_key, mel_rng)
        mel_track = [(t, p, d, velocity("melody", t % BAR, cfg, mel_rng))
                     for (t, p, d) in melody]
        write_midi(folder / f"t2 {combo['id']} - melody.mid", [("melody", 0, mel_track)], bpm)
        prov_log["melody"] = "grammar-v2 (motif AA'BA, weighted IOI+degree vocab)"

        n_mel = len(melody)
        manifest.append({"id": combo["id"], "label": combo["label"], "trial": 2,
                         "weights": combo["weights"], "key": target_key, "bpm": bpm,
                         "melody_notes": n_mel, "bar_sources": prov_log})
        print(f"t2 {combo['id']}  {combo['label']:<24} key {target_key:<4} {bpm:>6} bpm  "
              f"melody {n_mel} notes ({n_mel / N_BARS:.1f}/bar)")

    (OUT_DIR / "manifest.json").write_text(json.dumps(
        {"generated": str(date.today()), "trial": 2, "combos": manifest}, indent=1))
    with (OUT_DIR / "manifest.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["combo", "file", "key", "bpm", "weights", "keep (y/n)"])
        for m in manifest:
            for kind in ("melody", "bassline", "drums"):
                w.writerow([f"t2 {m['id']}", f"t2 {m['id']} - {kind}.mid", m["key"], m["bpm"],
                            " ".join(f"{s}:{v}" for s, v in m["weights"].items()), ""])
    print(f"\n{len(manifest) * 3} files in {OUT_DIR} — mark keepers in manifest.csv")


if __name__ == "__main__":
    main()
