#!/usr/bin/env python3
"""
generate_vibes_v6.py — Trial 06: bass lane + root landing + candidate self-scoring.

Trial 05 readout: melodies 7/8 cream, drums 7/8, basslines 4/8 = the bottleneck.
Flags said why: wrong lane (high "out there" bass DNA) and bad landing (loop
doesn't resolve). And the v04 experiment proved per-run dice variance is real.
Three changes:

1. BASS LANE FOLD — same medicine that fixed melodies: bars riding above the sub
   lane fold down an octave. ONE bar may stay high (that's the bounce, which is
   wanted); the line's overall median must sit in the sub lane.
2. ROOT LANDING — the loop's final bass note resolves to the target key's root,
   folded downward (low landing), so bar 4 leads back into bar 1's restart.
3. SELF-SCORING GATE — every combo generates 6 candidate packs on different dice
   and only the best-scoring one is presented. The score encodes everything the
   trials have taught: bass lane, end-low, bounce present, root landing,
   kick<->bass co-hit in the style zone (0.64-1.0), melody density zone + span.
   Trell's ears stay the final judge; they just stop auditioning unlucky dice.

Combos: v01/v02 re-roll the two recipes whose basses got flagged in trial 05
(t5-v05 and t5-v07 weights) to verify the fixes; v03-v08 are fresh draws.

Output: ~/Music/Ableton/User Library/vibes forever/t6 v01..v08 + manifest.csv (v2)
Usage:  python3 scripts/generate_vibes_v6.py
"""

import json
import random
from datetime import date
from statistics import median

from generate_vibes import (BAR, N_BARS, TPQ, DRUM_PITCH, OUT_DIR, CONFIG, DATA_DIR,
                            build_bar_library, collage, has_roll, inject_roll,
                            monophonize, transpose, semitone_shift, velocity,
                            write_midi, key_pc)
from generate_vibes_v3 import (collage_locked, shape_bass_register, bar_means,
                               generate_melody_v3)
from generate_vibes_v4 import clamp_register
from trial_manifest import write_manifest_csv

BASS_FLOOR = 24
BASS_LANE_CEIL = 44          # bar means above this are "out of the sub lane"
N_CANDIDATES = 6

FLAGGED_T5_V05 = {"morning": 0.25, "out there": 0.45, "sicko mode": 0.3}
FLAGGED_T5_V07 = {"morning": 0.09, "out there": 0.71, "sicko mode": 0.2}


# ---------------------------------------------------------------- bass rules

def shift_bar(notes, bar_i, semis):
    return [(t, p + semis, d) if bar_i * BAR <= t < (bar_i + 1) * BAR else (t, p, d)
            for (t, p, d) in notes]


def bass_lane_fold(notes):
    """Fold high bars into the sub lane; the single highest bar may stay (bounce)."""
    means = bar_means(notes)
    if not means:
        return notes
    bounce = max(means, key=means.get)
    for b in list(means):
        if b == bounce or means[b] <= BASS_LANE_CEIL:
            continue
        lo = min(p for (t, p, _) in notes if b * BAR <= t < (b + 1) * BAR)
        if lo - 12 >= BASS_FLOOR:
            notes = shift_bar(notes, b, -12)
    if median(p for _, p, _ in notes) > BASS_LANE_CEIL:
        if min(p for _, p, _ in notes) - 12 >= BASS_FLOOR:
            notes = [(t, p - 12, d) for (t, p, d) in notes]
    return notes


def resolve_root(notes, target_key):
    """The loop's last note lands on the key root, folded downward."""
    if not notes:
        return notes
    notes = sorted(notes)
    t, p, d = notes[-1]
    root = p - ((p - key_pc(target_key)) % 12)
    if root < BASS_FLOOR:
        root += 12
    notes[-1] = (t, root, d)
    return notes


# ---------------------------------------------------------------- scoring

def co_hit_rate(kick_notes, bass_notes):
    kick_ticks = sorted(t for (t, _, _) in kick_notes)
    bass_ticks = sorted(t for (t, _, _) in bass_notes)
    if not kick_ticks or not bass_ticks:
        return 0.0
    tol = TPQ / 8
    return sum(1 for t in bass_ticks
               if min(abs(t - k) for k in kick_ticks) <= tol) / len(bass_ticks)


def score_pack(bass, melody, kick, target_key):
    """Everything five trials of feedback taught us, as one number."""
    s = 0.0
    if bass:
        pitches = [p for _, p, _ in bass]
        means = bar_means(bass)
        if 30 <= median(pitches) <= BASS_LANE_CEIL:
            s += 2                                            # sub lane
        if means and means.get(max(means)) == min(means.values()):
            s += 2                                            # loop ends low (the drop)
        if means and max(means.values()) - min(means.values()) >= 5:
            s += 1                                            # bounce present
        if pitches and sorted(bass)[-1][1] % 12 == key_pc(target_key):
            s += 1                                            # root landing
        rate = co_hit_rate(kick, bass)
        s += 3 * min(rate / 0.64, 1.0)                        # kick<->bass lock (zone floor)
    if melody:
        per_bar = len(melody) / N_BARS
        if 5 <= per_bar <= 9:
            s += 1                                            # density zone
        pitches = [p for _, p, _ in melody]
        if max(pitches) - min(pitches) <= 12:
            s += 1                                            # tight register
    return round(s, 2)


# ---------------------------------------------------------------- generation

def build_candidate(packs, lib, cfg, weights, seed, mel_seed):
    rng = random.Random(seed)
    mel_rng = random.Random(mel_seed)

    target_key = packs[rng.choices(list(weights), list(weights.values()))[0]]["key"]
    locked, prov = collage_locked(("kick", "bass"), lib, weights, rng)

    kick = locked["kick"]
    drum_extra = {}
    for role in ("snare", "clap", "hat"):
        notes, p = collage(role, lib, weights, rng)
        if role == "hat" and notes and not has_roll(notes):
            notes = inject_roll(notes, cfg, rng)
        drum_extra[role] = (notes, p)

    bass = []
    for bar_i in range(N_BARS):
        bar_notes = [(t, p, d) for (t, p, d) in locked["bass"]
                     if bar_i * BAR <= t < (bar_i + 1) * BAR]
        bass.extend(transpose(bar_notes, semitone_shift(packs[prov[bar_i]]["key"], target_key)))
    bass = monophonize(bass)
    bass = bass_lane_fold(bass)
    bass = shape_bass_register(bass, rng)
    bass = bass_lane_fold(bass)              # shape may re-lift; lane rule has final say
    bass = resolve_root(bass, target_key)

    melody, winner = generate_melody_v3(packs, weights, target_key, mel_rng)
    melody = monophonize(clamp_register(melody))

    return {"key": target_key, "kick": kick, "bass": bass, "melody": melody,
            "drums_extra": drum_extra, "prov": prov, "melody_vocab": winner,
            "score": score_pack(bass, melody, kick, target_key),
            "rng": rng, "mel_rng": mel_rng, "seed": seed}


def main():
    packs = json.loads((DATA_DIR / "parsed_packs.json").read_text())["songs"]
    cfg = json.loads(CONFIG.read_text())
    lib = build_bar_library(packs)
    songs = list(packs)

    combos = [
        {"id": "v01", "weights": FLAGGED_T5_V05, "label": "t5v05weights-fixcheck"},
        {"id": "v02", "weights": FLAGGED_T5_V07, "label": "t5v07weights-fixcheck"},
    ]
    for i in range(6):
        rng = random.Random(400 + i)
        raw = [rng.random() + 0.1 for _ in songs]
        total = sum(raw)
        w = {s: round(r / total, 2) for s, r in zip(songs, raw)}
        combos.append({"id": f"v{i+3:02}", "weights": w,
                       "label": " ".join(f"{s.split()[0][:3]}{int(w[s]*100)}" for s in songs)})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    for idx, combo in enumerate(combos):
        weights = {s: w for s, w in combo["weights"].items() if w > 0}
        bpm = round(sum(packs[s]["bpm"] * w for s, w in weights.items()), 2)

        candidates = [build_candidate(packs, lib, cfg, weights,
                                      9700 + idx * 31 + k, 9800 + idx * 31 + k)
                      for k in range(N_CANDIDATES)]
        best = max(candidates, key=lambda c: c["score"])
        all_scores = [c["score"] for c in candidates]

        folder = OUT_DIR / f"t6 {combo['id']} {combo['label']}"
        folder.mkdir(exist_ok=True)

        rng, mel_rng = best["rng"], best["mel_rng"]
        drum_notes = [(t, DRUM_PITCH["kick"], min(d, 200), velocity("kick", t % BAR, cfg, rng))
                      for (t, _, d) in best["kick"]]
        prov_log = {"kick+bass (locked)": best["prov"]}
        for role, (notes, p) in best["drums_extra"].items():
            prov_log[role] = p
            drum_notes += [(t, DRUM_PITCH[role], min(d, 200), velocity(role, t % BAR, cfg, rng))
                           for (t, _, d) in notes]
        write_midi(folder / f"t6 {combo['id']} - drums.mid", [("drums", 9, drum_notes)], bpm)
        write_midi(folder / f"t6 {combo['id']} - bassline.mid",
                   [("bassline", 0, [(t, p, d, velocity("bass", t % BAR, cfg, rng))
                                     for (t, p, d) in best["bass"]])], bpm)
        write_midi(folder / f"t6 {combo['id']} - melody.mid",
                   [("melody", 0, [(t, p, d, velocity("melody", t % BAR, cfg, mel_rng))
                                   for (t, p, d) in best["melody"]])], bpm)
        prov_log["melody"] = f"grammar-v4, vocabulary = {best['melody_vocab']}"

        bmeans = bar_means(best["bass"])
        manifest.append({"id": combo["id"], "label": combo["label"], "trial": 6,
                         "weights": combo["weights"], "key": best["key"], "bpm": bpm,
                         "melody_vocabulary": best["melody_vocab"],
                         "candidate_seed": best["seed"], "candidate_scores": all_scores,
                         "chosen_score": best["score"],
                         "bass_register_by_bar": " ".join(f"{bmeans.get(b, 0):.0f}"
                                                          for b in range(N_BARS)),
                         "bar_sources": prov_log})
        print(f"t6 {combo['id']}  {combo['label']:<22} key {best['key']:<4} "
              f"score {best['score']} (candidates: {all_scores})  "
              f"bass: {manifest[-1]['bass_register_by_bar']}")

    (OUT_DIR / "manifest.json").write_text(json.dumps(
        {"generated": str(date.today()), "trial": 6, "combos": manifest}, indent=1))
    write_manifest_csv(OUT_DIR / "manifest.csv", "t6", manifest)
    print(f"\n{len(manifest) * 3} files in {OUT_DIR} — manifest v2, mark away")


if __name__ == "__main__":
    main()
