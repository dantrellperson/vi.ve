#!/usr/bin/env python3
"""
generate_vibes.py — First weighted style-map MIDI generation.

How the weighting works (v1 = weighted bar collage):
  Each combo assigns a weight per song (weights sum to 1). For every bar of the
  new 4-bar pattern, each instrument rolls the weighted dice to decide WHICH SONG
  that bar's pattern comes from. Heavier weight = more of that song's DNA.
  Bass/melody bars are transposed into the combo's target key (itself a weighted
  pick). Velocities are rebuilt from config/style_defaults.json because the source
  packs were drawn/laptop-played (velocity_reliable = False).

Output: ~/Music/Ableton/User Library/vibes forever/
  v01..v03 = pure controls (1.0 on a single song — should give that song's vibe back;
             verifies the weighting pipeline before trusting the blends)
  v04..v08 = random weights
  Each combo folder: melody, bassline, drums (kick 36 / snare 38 / clap 39 / hat 42)
  manifest.csv has a `keep` column — mark y/n while auditioning; that's the
  success metric for the run and future training signal for the weights.

Usage:
    python3 scripts/generate_vibes.py
"""

import csv
import json
import random
from datetime import date
from pathlib import Path

import mido

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CONFIG = Path(__file__).resolve().parent.parent / "config" / "style_defaults.json"
OUT_DIR = Path.home() / "Music" / "Ableton" / "User Library" / "vibes forever"

TPQ = 480                      # Trell's standard
BAR = 4 * TPQ                  # ticks per 4/4 bar
N_BARS = 4
PATTERN = N_BARS * BAR

DRUM_PITCH = {"kick": 36, "snare": 38, "clap": 39, "hat": 42}
NOTE_PC = {"C": 0, "Db": 1, "D": 2, "Eb": 3, "E": 4, "F": 5, "Gb": 6,
           "G": 7, "Ab": 8, "A": 9, "Bb": 10, "B": 11}

# which parts feed each generated role (sections: main pattern only, no chorus variants)
POOL = {
    "kick": {"kick"}, "snare": {"snare"}, "clap": {"clap"}, "hat": {"hihat"},
    "bass": {"bassline"}, "melody": {"melody", "keys", "chord progression"},
}
POOL_SECTIONS = {"both", "verse", "main"}


def key_pc(key):
    return NOTE_PC[key[:-1] if key.endswith("m") else key]


def build_bar_library(packs):
    """lib[role][song] = 4 bars, each a list of (offset_tick, pitch, dur) at TPQ=480."""
    lib = {role: {} for role in POOL}
    for song, pack in packs.items():
        for p in pack["parts"]:
            role = next((r for r, parts in POOL.items() if p["part"] in parts), None)
            if role is None or p["section"] not in POOL_SECTIONS:
                continue
            scale = TPQ / p["ticks_per_beat"]
            bars = [[] for _ in range(N_BARS)]
            src_bar = 4 * p["ticks_per_beat"]
            for n in p["notes"]:
                bar_i = (n["start_tick"] // src_bar) % N_BARS  # 8-bar kick folds to 4
                offset = (n["start_tick"] % src_bar) * scale
                bars[bar_i].append((round(offset), n["pitch"],
                                    max(30, round(n["duration_ticks"] * scale))))
            lib[role][song] = bars
    return lib


def monophonize(notes):
    """Keep the top note of simultaneous clusters; trim sustains at the next onset."""
    by_onset = {}
    for t, pitch, dur in sorted(notes):
        cur = by_onset.get(t)
        if cur is None or pitch > cur[1]:
            by_onset[t] = (t, pitch, dur)
    line = sorted(by_onset.values())
    out = []
    for i, (t, pitch, dur) in enumerate(line):
        if i + 1 < len(line):
            dur = min(dur, line[i + 1][0] - t)
        out.append((t, pitch, max(30, dur)))
    return out


def transpose(notes, delta):
    return [(t, p + delta, d) for (t, p, d) in notes]


def semitone_shift(src_key, dst_key):
    d = (key_pc(dst_key) - key_pc(src_key)) % 12
    return d - 12 if d > 6 else d  # smallest movement


def velocity(role, offset_in_bar, cfg, rng):
    v = cfg["velocity"][{"hat": "hihat"}.get(role, role)]
    lo, hi = v["min"], v["max"]
    if offset_in_bar % TPQ < 40:          # on a quarter-note beat -> accent
        return rng.randint(max(lo, hi - 25), hi)
    if offset_in_bar % (TPQ // 2) < 40:   # 8th offbeat -> medium
        return rng.randint(lo + (hi - lo) // 3, hi - 15)
    return rng.randint(lo, lo + (hi - lo) // 2)


def has_roll(notes):
    ticks = sorted(t for t, _, _ in notes)
    return any(b - a < 100 for a, b in zip(ticks, ticks[1:]))


def inject_roll(notes, cfg, rng):
    """One 32nd-note roll per 4 bars, ending right before beat 3 (morning finding)."""
    bar_i = rng.choice([1, 3])
    base = bar_i * BAR + TPQ + TPQ // 2          # beat 2.5 of that bar
    step = TPQ // 8                               # 32nds
    for i in range(4):
        notes.append((base + i * step, DRUM_PITCH["hat"], step - 10))
    return notes


def collage(role, lib, weights, rng):
    """Pick each bar's source song by weight; returns notes + per-bar provenance."""
    songs = [s for s in weights if s in lib[role]]
    if not songs:
        return [], []
    w = [weights[s] for s in songs]
    notes, provenance = [], []
    for bar_i in range(N_BARS):
        src = rng.choices(songs, w)[0]
        provenance.append(src)
        for (t, p, d) in lib[role][src][bar_i]:
            notes.append((bar_i * BAR + t, p, d))
    return notes, provenance


def write_midi(path, tracks_notes, bpm):
    """tracks_notes: list of (name, channel, [(tick, pitch, dur, vel)])"""
    mid = mido.MidiFile(ticks_per_beat=TPQ)
    for name, channel, notes in tracks_notes:
        trk = mido.MidiTrack()
        trk.append(mido.MetaMessage("track_name", name=name, time=0))
        trk.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))
        trk.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
        events = []
        for (tick, pitch, dur, vel) in notes:
            events.append((tick, 1, "note_on", pitch, vel))
            events.append((tick + dur, 0, "note_off", pitch, 0))
        events.sort(key=lambda e: (e[0], e[1]))  # offs before ons at the same tick
        prev = 0
        for (tick, _, kind, pitch, vel) in events:
            trk.append(mido.Message(kind, note=pitch, velocity=vel,
                                    channel=channel, time=tick - prev))
            prev = tick
        trk.append(mido.MetaMessage("end_of_track", time=max(0, PATTERN - prev)))
        mid.tracks.append(trk)
    mid.save(path)


def main():
    packs = json.loads((DATA_DIR / "parsed_packs.json").read_text())["songs"]
    cfg = json.loads(CONFIG.read_text())
    lib = build_bar_library(packs)
    songs = list(packs)

    combos = []
    for i, s in enumerate(songs):                                  # pure controls
        combos.append({"id": f"v{i+1:02}", "weights": {x: (1.0 if x == s else 0.0) for x in songs},
                       "label": f"pure-{s.replace(' ', '')}"})
    for i in range(5):                                             # random blends
        rng = random.Random(200 + i)
        raw = [rng.random() + 0.1 for _ in songs]
        total = sum(raw)
        w = {s: round(r / total, 2) for s, r in zip(songs, raw)}
        combos.append({"id": f"v{i+4:02}", "weights": w,
                       "label": " ".join(f"{s.split()[0][:3]}{int(w[s]*100)}" for s in songs)})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    for combo in combos:
        # stable seed so a stored style recipe can regenerate the exact same files
        rng = random.Random(9000 + int(combo["id"][1:]))
        weights = {s: w for s, w in combo["weights"].items() if w > 0}

        target_key = packs[rng.choices(list(weights), list(weights.values()))[0]]["key"]
        bpm = round(sum(packs[s]["bpm"] * w for s, w in weights.items()), 2)

        folder = OUT_DIR / f"{combo['id']} {combo['label']}"
        folder.mkdir(exist_ok=True)
        prov_log = {}

        # ---- drums: one file, all four roles collaged independently
        drum_notes = []
        for role in ("kick", "snare", "clap", "hat"):
            notes, prov = collage(role, lib, weights, rng)
            prov_log[role] = prov
            if role == "hat" and notes and not has_roll(notes):
                notes = inject_roll(notes, cfg, rng)
            for (t, _, d) in notes:
                drum_notes.append((t, DRUM_PITCH[role], min(d, 200),
                                   velocity(role, t % BAR, cfg, rng)))
        write_midi(folder / f"{combo['id']} - drums.mid",
                   [("drums", 9, drum_notes)], bpm)

        # ---- bass and melody: collage + transpose to target key + monophonize
        for role in ("bass", "melody"):
            notes, prov = collage(role, lib, weights, rng)
            prov_log[role] = prov
            fixed = []
            for bar_i in range(N_BARS):
                src = prov[bar_i] if prov else None
                bar_notes = [(t, p, d) for (t, p, d) in notes
                             if bar_i * BAR <= t < (bar_i + 1) * BAR]
                if src:
                    bar_notes = transpose(bar_notes, semitone_shift(packs[src]["key"], target_key))
                fixed.extend(bar_notes)
            mono = monophonize(fixed)
            track = [(t, p, d, velocity(role, t % BAR, cfg, rng)) for (t, p, d) in mono]
            name = "bassline" if role == "bass" else "melody"
            write_midi(folder / f"{combo['id']} - {name}.mid", [(name, 0, track)], bpm)

        manifest.append({"id": combo["id"], "label": combo["label"],
                         "weights": combo["weights"], "key": target_key, "bpm": bpm,
                         "bar_sources": prov_log})
        print(f"{combo['id']}  {combo['label']:<24} key {target_key:<4} {bpm:>6} bpm  "
              f"-> 3 files")

    # ---- manifest: json (full provenance) + csv with the `keep` success column
    (OUT_DIR / "manifest.json").write_text(json.dumps(
        {"generated": str(date.today()), "combos": manifest}, indent=1))
    with (OUT_DIR / "manifest.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["combo", "file", "key", "bpm", "weights", "keep (y/n)"])
        for m in manifest:
            for kind in ("melody", "bassline", "drums"):
                w.writerow([m["id"], f"{m['id']} - {kind}.mid", m["key"], m["bpm"],
                            " ".join(f"{s}:{v}" for s, v in m["weights"].items()), ""])
    print(f"\n{len(manifest) * 3} MIDI files in {OUT_DIR}")
    print("Mark keepers in manifest.csv — that's the success metric for this run.")


if __name__ == "__main__":
    main()
