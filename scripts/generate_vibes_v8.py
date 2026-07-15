#!/usr/bin/env python3
"""
generate_vibes_v8.py — Trial 08: remove the contaminated source instead of disguising it.

Trial 07 post-mortem (all 8 basslines failed): every failed bassline contained bars
from "out there"'s verse bassline — the +8/octave/octave/+5 counter-melody structure.
The v7 octave-fold only re-pitched it; rhythm and contour survived, which is what the
ear caught. Probability math made contamination near-certain: P(pattern in a 4-bar
collage) = 1-(1-w)^4 = 87% at w=0.4. And the score never penalized the source.

Changes:
  1. "out there" is REMOVED from the kick+bass anchor pool (weights renormalize
     over morning/sicko). It still supplies hats, snare, clap, and melody vocabulary.
  2. The laundering fold is deleted; the retired structure is now a -3 score
     PENALTY (belt and braces — the source is gone).
  3. Bounce comes only from the register-shape rules on morning/sicko bars.
  4. Combo design: 8 fresh draws, NO flagged-recipe re-rolls (that feedback loop
     pushed out-there bass share 25% -> 37.5% -> 47% across trials 5-7).

Trial 06 verdict under harsher standards: melody 8/8, drums 8/8, bass 1/8 —
7 wrong-lane marks, all traced to one root cause: the engine still wrote for the
old Arturia Mini sub workflow while Trell now plays an 808 audio sample whose root
sits at middle C (C3 = MIDI 60, Ableton naming). New rules, verbatim from feedback:

  FRAME    basslines are delivered in the 808 frame (median folded into ~F#2-A3);
           no more manual pitching up
  BAR 1    most of bar 1 never a full octave+ above middle C -> notes above C4 fold down
  RETIRED  the "all high above root" bar (+8 / octave / octave / octave / +5 —
           out-there counter DNA): alternating notes fold down an octave instead,
           creating intra-bar bounce (D4->D3, C4->C3 bouncing into A3)
  ENDINGS  a bar never ends exactly one octave below the root; it finishes on the
           root, or the b7 when the bar begins on the root
  LANDING  the loop's final note = the root at the 808 octave (E3/Eb3)

Everything else (anchor lock, end-low drop, melody engine, 6-candidate scoring
gate) carries over; the score gains terms for each new rule.

Combos: v01/v02 re-roll t6-v03 and t6-v07 weights (flagged basslines) as fix
checks; v03-v08 fresh draws.

Output: ~/Music/Ableton/User Library/vibes forever/t7 v01..v08 + manifest.csv (v2)
Usage:  python3 scripts/generate_vibes_v7.py
"""

import json
import random
from datetime import date
from statistics import median

from generate_vibes import (BAR, N_BARS, TPQ, DRUM_PITCH, OUT_DIR, CONFIG, DATA_DIR,
                            build_bar_library, collage, has_roll, inject_roll,
                            monophonize, transpose, semitone_shift, velocity,
                            write_midi, key_pc)
from generate_vibes_v3 import collage_locked, bar_means, generate_melody_v3
from generate_vibes_v4 import clamp_register
from generate_vibes_v6 import co_hit_rate, shift_bar
from trial_manifest import write_manifest_csv

BASS_FLOOR = 48            # C2 — nothing below this in the 808 frame
LANE = (56, 69)            # the line's median lives here (~G#2-A3)
BAR1_CEIL = 71             # bar-1 notes above this (C4+) fold down
BOUNCE_CEIL = 78
N_CANDIDATES = 6

T6_V03_W = {"morning": 0.24, "out there": 0.21, "sicko mode": 0.55}
T6_V07_W = {"morning": 0.24, "out there": 0.64, "sicko mode": 0.13}


def root_ref(key):
    return 60 + key_pc(key)          # Em -> E3 (64), Ebm -> Eb3 (63)


def bar_slice(notes, bar_i):
    return [n for n in notes if bar_i * BAR <= n[0] < (bar_i + 1) * BAR]


# ---------------------------------------------------------------- the new rules

def to_808_frame(notes):
    """Octave-shift the whole line until its median sits in the 808 lane."""
    if not notes:
        return notes
    shift = 24                        # out of the old Arturia sub workflow
    med = median(p for _, p, _ in notes)
    while med + shift > LANE[1]:
        shift -= 12
    while med + shift < LANE[0]:
        shift += 12
    return [(t, p + shift, d) for (t, p, d) in notes]


def fold_high_bars(notes, root):
    """RETIRED STRUCTURE: a bar with every note >= root+7 folds alternating notes
    down an octave (never the bar's last note) -> intra-bar bounce."""
    out = []
    for bar_i in range(N_BARS):
        ns = sorted(bar_slice(notes, bar_i))
        if ns and all(p >= root + 7 for _, p, _ in ns):
            ns = [(t, p - 12, d) if (j % 2 == 0 and j != len(ns) - 1 and p - 12 >= BASS_FLOOR)
                  else (t, p, d) for j, (t, p, d) in enumerate(ns)]
        out.extend(ns)
    return sorted(out)


def cap_bar1(notes):
    """Most of bar 1 never a full octave+ above middle C."""
    return sorted([(t, p - 12, d) if (t < BAR and p > BAR1_CEIL and p - 12 >= BASS_FLOOR)
                   else (t, p, d) for (t, p, d) in notes])


def fix_bar_endings(notes, root):
    """A bar never ends exactly one octave below the root: raise to the root, or
    to the b7 when the bar begins on the root."""
    out = list(sorted(notes))
    for bar_i in range(N_BARS):
        ns = bar_slice(out, bar_i)
        if not ns:
            continue
        t_last, p_last, d_last = ns[-1]
        if p_last == root - 12:
            new_p = root - 2 if ns[0][1] == root else root
            out[out.index((t_last, p_last, d_last))] = (t_last, new_p, d_last)
    return sorted(out)


def end_low_shape(notes, rng):
    """Keep the drop: bar 4 is the loop's low point (within 808-frame floors)."""
    means = bar_means(notes)
    if len(means) < 2:
        return notes
    if max(means.values()) - min(means.values()) < 5:
        candidates = [b for b in (1, 2) if b in means]
        if candidates:
            b = rng.choice(candidates)
            hi = max(p for (t, p, _) in bar_slice(notes, b))
            if hi + 12 <= BOUNCE_CEIL:
                notes = shift_bar(notes, b, 12)
                means = bar_means(notes)
    last = max(means)
    guard = 3
    while guard and means[last] > min(means.values()) + 0.5:
        lo = min(p for (t, p, _) in bar_slice(notes, last))
        if lo - 12 < 54:              # never drops into octave-below-root territory
            break
        notes = shift_bar(notes, last, -12)
        means = bar_means(notes)
        guard -= 1
    return notes


def resolve_loop(notes, root):
    if not notes:
        return notes
    notes = sorted(notes)
    t, p, d = notes[-1]
    notes[-1] = (t, root, d)
    return notes


# ---------------------------------------------------------------- scoring

def score_pack(bass, melody, kick, target_key):
    root = root_ref(target_key)
    s = 0.0
    if bass:
        pitches = [p for _, p, _ in bass]
        means = bar_means(bass)
        if LANE[0] <= median(pitches) <= LANE[1]:
            s += 2                                              # 808 lane
        if means and means.get(max(means)) == min(means.values()):
            s += 2                                              # loop ends low
        if means and max(means.values()) - min(means.values()) >= 5:
            s += 1                                              # bounce
        bar1 = [p for (t, p, _) in bass if t < BAR]
        if bar1 and sum(1 for p in bar1 if p <= BAR1_CEIL) / len(bar1) > 0.5:
            s += 1                                              # bar-1 ceiling
        for b in range(N_BARS):
            ns = bar_slice(bass, b)
            if ns and all(p >= root + 7 for _, p, _ in ns):
                s -= 3                                          # retired structure = hard penalty
        if sorted(bass)[-1][1] == root:
            s += 1                                              # root landing at 808 octave
        s += 3 * min(co_hit_rate(kick, bass) / 0.64, 1.0)       # kick<->bass lock
    if melody:
        if 5 <= len(melody) / N_BARS <= 9:
            s += 1
        pitches = [p for _, p, _ in melody]
        if max(pitches) - min(pitches) <= 12:
            s += 1
    return round(s, 2)


# ---------------------------------------------------------------- generation

def build_candidate(packs, lib, cfg, weights, seed, mel_seed):
    rng = random.Random(seed)
    mel_rng = random.Random(mel_seed)

    target_key = packs[rng.choices(list(weights), list(weights.values()))[0]]["key"]
    root = root_ref(target_key)
    anchor_weights = {s: w for s, w in weights.items() if s != "out there"}
    if not anchor_weights:
        anchor_weights = {"sicko mode": 1.0}
    locked, prov = collage_locked(("kick", "bass"), lib, anchor_weights, rng)

    drum_extra = {}
    for role in ("snare", "clap", "hat"):
        notes, p = collage(role, lib, weights, rng)
        if role == "hat" and notes and not has_roll(notes):
            notes = inject_roll(notes, cfg, rng)
        drum_extra[role] = (notes, p)

    bass = []
    for bar_i in range(N_BARS):
        bar_notes = bar_slice(locked["bass"], bar_i)
        bass.extend(transpose(bar_notes, semitone_shift(packs[prov[bar_i]]["key"], target_key)))
    bass = monophonize(bass)
    bass = to_808_frame(bass)
    bass = end_low_shape(bass, rng)
    bass = cap_bar1(bass)
    bass = fix_bar_endings(bass, root)
    bass = resolve_loop(bass, root)

    melody, winner = generate_melody_v3(packs, weights, target_key, mel_rng)
    melody = monophonize(clamp_register(melody))

    return {"key": target_key, "kick": locked["kick"], "bass": bass, "melody": melody,
            "drums_extra": drum_extra, "prov": prov, "melody_vocab": winner,
            "score": score_pack(bass, melody, locked["kick"], target_key),
            "rng": rng, "mel_rng": mel_rng, "seed": seed}


def main():
    packs = json.loads((DATA_DIR / "parsed_packs.json").read_text())["songs"]
    cfg = json.loads(CONFIG.read_text())
    lib = build_bar_library(packs)
    songs = list(packs)

    combos = []
    for i in range(8):
        rng = random.Random(600 + i)
        raw = [rng.random() + 0.1 for _ in songs]
        total = sum(raw)
        w = {s: round(r / total, 2) for s, r in zip(songs, raw)}
        combos.append({"id": f"v{i+1:02}", "weights": w,
                       "label": " ".join(f"{s.split()[0][:3]}{int(w[s]*100)}" for s in songs)})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    note_name = lambda p: "CDbDEbEFGbGAbABbB"[0] if False else \
        ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"][p % 12] + str(p // 12 - 2)
    for idx, combo in enumerate(combos):
        weights = {s: w for s, w in combo["weights"].items() if w > 0}
        bpm = round(sum(packs[s]["bpm"] * w for s, w in weights.items()), 2)

        candidates = [build_candidate(packs, lib, cfg, weights,
                                      10100 + idx * 41 + k, 10200 + idx * 41 + k)
                      for k in range(N_CANDIDATES)]
        best = max(candidates, key=lambda c: c["score"])

        folder = OUT_DIR / f"t8 {combo['id']} {combo['label']}"
        folder.mkdir(exist_ok=True)

        rng, mel_rng = best["rng"], best["mel_rng"]
        drum_notes = [(t, DRUM_PITCH["kick"], min(d, 200), velocity("kick", t % BAR, cfg, rng))
                      for (t, _, d) in best["kick"]]
        prov_log = {"kick+bass (locked)": best["prov"]}
        for role, (notes, p) in best["drums_extra"].items():
            prov_log[role] = p
            drum_notes += [(t, DRUM_PITCH[role], min(d, 200), velocity(role, t % BAR, cfg, rng))
                           for (t, _, d) in notes]
        write_midi(folder / f"t8 {combo['id']} - drums.mid", [("drums", 9, drum_notes)], bpm)
        write_midi(folder / f"t8 {combo['id']} - bassline.mid",
                   [("bassline", 0, [(t, p, d, velocity("bass", t % BAR, cfg, rng))
                                     for (t, p, d) in best["bass"]])], bpm)
        write_midi(folder / f"t8 {combo['id']} - melody.mid",
                   [("melody", 0, [(t, p, d, velocity("melody", t % BAR, cfg, mel_rng))
                                   for (t, p, d) in best["melody"]])], bpm)
        prov_log["melody"] = f"grammar-v4, vocabulary = {best['melody_vocab']}"

        bar1 = sorted(bar_slice(best["bass"], 0))
        manifest.append({"id": combo["id"], "label": combo["label"], "trial": 8,
                         "weights": combo["weights"], "key": best["key"], "bpm": bpm,
                         "melody_vocabulary": best["melody_vocab"],
                         "candidate_seed": best["seed"], "chosen_score": best["score"],
                         "candidate_scores": [c["score"] for c in candidates],
                         "bass_bar1_notes": [note_name(p) for _, p, _ in bar1],
                         "bass_last_note": note_name(sorted(best["bass"])[-1][1]),
                         "bar_sources": prov_log})
        print(f"t8 {combo['id']}  {combo['label']:<22} key {best['key']:<4} score {best['score']}"
              f"  bar1: {' '.join(manifest[-1]['bass_bar1_notes']):<24}"
              f" lands on {manifest[-1]['bass_last_note']}")

    (OUT_DIR / "manifest.json").write_text(json.dumps(
        {"generated": str(date.today()), "trial": 8, "combos": manifest}, indent=1))
    write_manifest_csv(OUT_DIR / "manifest.csv", "t8", manifest)
    print(f"\n{len(manifest) * 3} files in {OUT_DIR} — 808 frame, Ableton note names (C3 = middle C)")


if __name__ == "__main__":
    main()
