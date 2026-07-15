#!/usr/bin/env python3
"""
generate_vibes_v3.py — Trial 03: coherence rules from Trial 02 feedback.

Three changes, each mapped to a specific Trial-02 observation:

1. ANCHOR-SONG RULE (v04–v06 rejected wholesale):
   each bar draws ONE song that supplies kick AND bass together, preserving the
   kick<->bass lock (co-hit 0.64–1.0 = the style signature). Hats/snare/clap still
   roll independent weighted dice — their placement blends safely.

2. WINNER-TAKES-VOCABULARY MELODY ("high pitch random notes"):
   the weights pick WHICH single song supplies the whole melody language —
   vocabulary, register, everything. Plus phrase spillover: chromatic/scale pickups
   into the next bar and sustained tails across barlines, because bar-boxed phrases
   are what read as random.

3. BASS REGISTER SHAPE ("loops must end low"):
   high<->low shifting = bounce, high->low = drop, and bar 4 must resolve LOW so the
   loop restart drops. If the collage comes out flat, one middle bar is lifted an
   octave for bounce; if bar 4 isn't the low point, it gets pulled down.

Same 8 weight combos as trials 1–2 (controlled comparison).
Output: ~/Music/Ableton/User Library/vibes forever/t3 v01..v08 + manifest.csv
Usage:  python3 scripts/generate_vibes_v3.py
"""

import csv
import json
import random
from datetime import date
from pathlib import Path

from generate_vibes import (BAR, N_BARS, TPQ, DRUM_PITCH, OUT_DIR, CONFIG, DATA_DIR,
                            build_bar_library, collage, has_roll, inject_roll,
                            monophonize, transpose, semitone_shift, velocity,
                            write_midi, key_pc)
from generate_vibes_v2 import (MINOR, STEP16, melody_vocab, weighted_sample,
                               make_motif_rhythm, degrees_for, to_pitches)

BASS_FLOOR, BASS_CEIL = 24, 58


def collage_locked(roles, lib, weights, rng):
    """One weighted draw per bar supplies EVERY role in `roles` (the anchor-song rule)."""
    songs = [s for s in weights if all(s in lib[r] for r in roles)]
    if not songs:
        return {r: [] for r in roles}, []
    w = [weights[s] for s in songs]
    notes = {r: [] for r in roles}
    provenance = []
    for bar_i in range(N_BARS):
        src = rng.choices(songs, w)[0]
        provenance.append(src)
        for r in roles:
            for (t, p, d) in lib[r][src][bar_i]:
                notes[r].append((bar_i * BAR + t, p, d))
    return notes, provenance


def bar_means(notes):
    means = {}
    for bar_i in range(N_BARS):
        ps = [p for (t, p, _) in notes if bar_i * BAR <= t < (bar_i + 1) * BAR]
        if ps:
            means[bar_i] = sum(ps) / len(ps)
    return means


def shift_bar(notes, bar_i, semis):
    return [(t, p + semis, d) if bar_i * BAR <= t < (bar_i + 1) * BAR else (t, p, d)
            for (t, p, d) in notes]


def shape_bass_register(notes, rng):
    """Enforce the register rules: bounce if flat, and the loop ends LOW (bar 4)."""
    means = bar_means(notes)
    if len(means) < 2:
        return notes
    # bounce: if all bars sit in one register, lift a middle bar an octave
    if max(means.values()) - min(means.values()) < 5:
        candidates = [b for b in (1, 2) if b in means]
        if candidates:
            b = rng.choice(candidates)
            hi = max(p for (t, p, _) in notes if b * BAR <= t < (b + 1) * BAR)
            if hi + 12 <= BASS_CEIL:
                notes = shift_bar(notes, b, 12)
                means = bar_means(notes)
    # drop: bar 4 must be the low point of the loop
    last = max(means)
    guard = 4
    while guard and means[last] > min(means.values()) + 0.5:
        lo = min(p for (t, p, _) in notes if last * BAR <= t < (last + 1) * BAR)
        if lo - 12 < BASS_FLOOR:
            break
        notes = shift_bar(notes, last, -12)
        means = bar_means(notes)
        guard -= 1
    return notes


def generate_melody_v3(packs, weights, target_key, rng):
    """One song's whole language (winner by weight), AA'BA motif, phrases spilling
    over barlines via pickups + sustained tails."""
    winner = rng.choices(list(weights), list(weights.values()))[0]
    iois, degree_steps, registers = melody_vocab(packs, {winner: 1.0})
    if not iois or not degree_steps:
        return [], winner
    center = weighted_sample(registers, rng)
    root_pitch = 12 * round((center - key_pc(target_key)) / 12) + key_pc(target_key)

    rhythm_a = make_motif_rhythm(iois, rng)
    rhythm_b = make_motif_rhythm(iois, rng)
    degs_a = degrees_for(rhythm_a, degree_steps, rng)

    plans = [
        (rhythm_a, degs_a),
        (rhythm_a, degs_a[:-1] + degrees_for(rhythm_a[-1:], degree_steps, rng)),
        (rhythm_b, degrees_for(rhythm_b, degree_steps, rng, start_choices=[3, 7])),
        (rhythm_a, degrees_for(rhythm_a, degree_steps, rng, resolve=True)),
    ]
    notes = []
    for bar_i, (rhythm, degs) in enumerate(plans):
        pitches = to_pitches(degs, root_pitch)
        for j, (pos, pitch) in enumerate(zip(rhythm, pitches)):
            tick = bar_i * BAR + pos * STEP16
            tick += rng.randint(-8, 8) if pos != 0 else 0
            gap = ((rhythm[j + 1] - pos) * STEP16 if j + 1 < len(rhythm) else 4 * STEP16)
            dur = min(max(STEP16, int(gap * rng.uniform(0.7, 0.95))), 4 * STEP16)
            if j == len(rhythm) - 1 and bar_i < N_BARS - 1 and rng.random() < 0.6:
                dur = int(dur + rng.uniform(0.5, 2.0) * TPQ)   # tail sustains over the barline
            notes.append((max(0, tick), pitch, dur))
        # pickup into the next bar: chromatic or scale approach to its first note
        if bar_i < N_BARS - 1 and rng.random() < 0.5:
            nxt = to_pitches(plans[bar_i + 1][1][:1], root_pitch)[0]
            approach = nxt - rng.choice([1, 2])
            tick = (bar_i + 1) * BAR - STEP16
            notes.append((tick, approach, STEP16 - 20))
    return sorted(notes), winner


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
        rng = random.Random(9200 + int(combo["id"][1:]))
        mel_rng = random.Random(9300 + int(combo["id"][1:]))
        weights = {s: w for s, w in combo["weights"].items() if w > 0}

        target_key = packs[rng.choices(list(weights), list(weights.values()))[0]]["key"]
        bpm = round(sum(packs[s]["bpm"] * w for s, w in weights.items()), 2)

        folder = OUT_DIR / f"t3 {combo['id']} {combo['label']}"
        folder.mkdir(exist_ok=True)
        prov_log = {}

        # ---- anchor-song rule: kick + bass locked to the same per-bar source
        locked, prov = collage_locked(("kick", "bass"), lib, weights, rng)
        prov_log["kick+bass (locked)"] = prov

        drum_notes = []
        for (t, _, d) in locked["kick"]:
            drum_notes.append((t, DRUM_PITCH["kick"], min(d, 200),
                               velocity("kick", t % BAR, cfg, rng)))
        for role in ("snare", "clap", "hat"):
            notes, p = collage(role, lib, weights, rng)
            prov_log[role] = p
            if role == "hat" and notes and not has_roll(notes):
                notes = inject_roll(notes, cfg, rng)
            for (t, _, d) in notes:
                drum_notes.append((t, DRUM_PITCH[role], min(d, 200),
                                   velocity(role, t % BAR, cfg, rng)))
        write_midi(folder / f"t3 {combo['id']} - drums.mid", [("drums", 9, drum_notes)], bpm)

        # ---- bass: transpose to target key, then apply the register shape rules
        bass = []
        for bar_i in range(N_BARS):
            bar_notes = [(t, p, d) for (t, p, d) in locked["bass"]
                         if bar_i * BAR <= t < (bar_i + 1) * BAR]
            bass.extend(transpose(bar_notes, semitone_shift(packs[prov[bar_i]]["key"], target_key)))
        bass = shape_bass_register(monophonize(bass), rng)
        write_midi(folder / f"t3 {combo['id']} - bassline.mid",
                   [("bassline", 0, [(t, p, d, velocity("bass", t % BAR, cfg, rng))
                                     for (t, p, d) in bass])], bpm)

        # ---- melody: one song's whole language
        melody, winner = generate_melody_v3(packs, weights, target_key, mel_rng)
        write_midi(folder / f"t3 {combo['id']} - melody.mid",
                   [("melody", 0, [(t, p, d, velocity("melody", t % BAR, cfg, mel_rng))
                                   for (t, p, d) in melody])], bpm)
        prov_log["melody"] = f"grammar-v3, vocabulary = {winner}"

        bmeans = bar_means(bass)
        shape = " ".join(f"{bmeans.get(b, 0):.0f}" for b in range(N_BARS))
        manifest.append({"id": combo["id"], "label": combo["label"], "trial": 3,
                         "weights": combo["weights"], "key": target_key, "bpm": bpm,
                         "melody_vocabulary": winner, "bass_register_by_bar": shape,
                         "bar_sources": prov_log})
        print(f"t3 {combo['id']}  {combo['label']:<24} key {target_key:<4} "
              f"melody={winner:<11} bass registers: {shape}")

    (OUT_DIR / "manifest.json").write_text(json.dumps(
        {"generated": str(date.today()), "trial": 3, "combos": manifest}, indent=1))
    with (OUT_DIR / "manifest.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["combo", "file", "key", "bpm", "weights", "keep (y/n)"])
        for m in manifest:
            for kind in ("melody", "bassline", "drums"):
                w.writerow([f"t3 {m['id']}", f"t3 {m['id']} - {kind}.mid", m["key"], m["bpm"],
                            " ".join(f"{s}:{v}" for s, v in m["weights"].items()), ""])
    print(f"\n{len(manifest) * 3} files in {OUT_DIR} — mark keepers in manifest.csv")


if __name__ == "__main__":
    main()
