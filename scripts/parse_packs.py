#!/usr/bin/env python3
"""
parse_packs.py — Load every midi_university pack into one normalized structure.

Core representation (decided 2026-07-12, GrooVAE-style score/feel split):
every note is stored as
    SCORE : which 16th-grid step it belongs to (the quantized pattern)
    FEEL  : deviation from that step in ticks AND milliseconds, plus velocity

Output:
    vi.ve/data/parsed_packs.json  — full normalized dataset for analysis scripts
    stdout                        — per-file summary table (sanity check)

Usage:
    python3 scripts/parse_packs.py            # parse + write JSON + print summary
    python3 scripts/parse_packs.py --dry-run  # print summary only, write nothing

Importable:
    from parse_packs import load_packs        # returns the parsed dict (re-parses live)
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

import mido

MIDI_UNIVERSITY = Path("/Users/trell/Music/Ableton/User Library/midi_university")
DATA_OUT = Path(__file__).resolve().parent.parent / "data" / "parsed_packs.json"

BEATS_PER_BAR = 4  # all packs are 4/4

# folder convention: "song title key Em bpm 71.66"
FOLDER_RE = re.compile(r"^(?P<song>.+?)\s+key\s+(?P<key>\S+)\s+bpm\s+(?P<bpm>[\d.]+)$", re.I)

# words that identify a song section inside a part name, e.g. "chorus bassline"
SECTION_WORDS = {"verse", "chorus", "brkdwn", "breakdown", "intro", "hook", "bridge", "outro",
                 "main"}


def parse_folder_name(name):
    m = FOLDER_RE.match(name.strip())
    if not m:
        return None
    return {
        "song": m.group("song").strip(),
        "key": m.group("key"),
        "bpm": float(m.group("bpm")),
    }


def parse_file_name(stem, song):
    """'out there - chorus bassline' -> part='bassline', section='chorus'.

    No section identifier means the pattern is used in BOTH 4-bar sections.
    """
    descriptor = stem.strip()
    if "-" in descriptor:
        descriptor = descriptor.split("-", 1)[1]
    descriptor = descriptor.strip().lower()
    words = descriptor.split()
    section = "both"
    if words and words[0] in SECTION_WORDS:
        section = words[0]
        words = words[1:]
    part = " ".join(words) if words else descriptor
    return part, section


def extract_notes(midi_path):
    """Return (ticks_per_beat, sorted note list) with absolute-tick note events."""
    mid = mido.MidiFile(midi_path)
    tpq = mid.ticks_per_beat
    merged = mido.merge_tracks(mid.tracks)

    abs_tick = 0
    active = {}  # pitch -> list of (start_tick, velocity), handles overlapping same-pitch notes
    notes = []
    for msg in merged:
        abs_tick += msg.time
        if msg.type == "note_on" and msg.velocity > 0:
            active.setdefault(msg.note, []).append((abs_tick, msg.velocity))
        elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
            if active.get(msg.note):
                start, vel = active[msg.note].pop(0)
                notes.append({"start_tick": start, "pitch": msg.note,
                              "velocity": vel, "duration_ticks": abs_tick - start})
    # close any hanging notes at the final tick
    for pitch, starts in active.items():
        for start, vel in starts:
            notes.append({"start_tick": start, "pitch": pitch,
                          "velocity": vel, "duration_ticks": abs_tick - start})
    notes.sort(key=lambda n: (n["start_tick"], n["pitch"]))
    return tpq, notes


def normalize_note(note, tpq, bpm):
    """Add bar/beat position and the score/feel split to a raw note event."""
    tick16 = tpq / 4  # ticks per 16th
    ms_per_tick = (60_000 / bpm) / tpq

    start = note["start_tick"]
    grid16 = round(start / tick16)          # SCORE: nearest 16th step from clip start
    deviation_ticks = start - grid16 * tick16  # FEEL: signed offset (negative = early/pushing)

    beats = start / tpq
    return {
        **note,
        "bar": int(beats // BEATS_PER_BAR),                 # 0-indexed
        "beat_in_bar": round(beats % BEATS_PER_BAR, 4),      # 0.0 = the 1
        "grid16": grid16,
        "grid16_in_bar": grid16 % (BEATS_PER_BAR * 4),
        "deviation_ticks": round(deviation_ticks, 2),
        "deviation_ms": round(deviation_ticks * ms_per_tick, 2),
        "duration_beats": round(note["duration_ticks"] / tpq, 4),
    }


def space_ratio(notes, tpq, n_bars):
    """Fraction of the pattern where NOTHING is sounding. Space is a first-class feature."""
    total = n_bars * BEATS_PER_BAR * tpq
    if total == 0:
        return 1.0
    intervals = sorted((n["start_tick"], n["start_tick"] + n["duration_ticks"]) for n in notes)
    covered, cur_start, cur_end = 0, None, None
    for s, e in intervals:
        if cur_end is None or s > cur_end:
            if cur_end is not None:
                covered += cur_end - cur_start
            cur_start, cur_end = s, e
        else:
            cur_end = max(cur_end, e)
    if cur_end is not None:
        covered += min(cur_end, total) - cur_start
    return round(1 - covered / total, 4)


def summarize(notes, tpq, bpm):
    if not notes:
        return {"n_notes": 0}
    last_end = max(n["start_tick"] + n["duration_ticks"] for n in notes)
    n_bars = max(1, -(-last_end // (BEATS_PER_BAR * tpq)))  # ceil to whole bars
    velocities = [n["velocity"] for n in notes]
    pitches = sorted({n["pitch"] for n in notes})
    deviations = [abs(n["deviation_ms"]) for n in notes]
    return {
        "n_notes": len(notes),
        "n_bars": int(n_bars),
        "unique_pitches": pitches,
        "velocity_min": min(velocities),
        "velocity_max": max(velocities),
        "velocity_mean": round(sum(velocities) / len(velocities), 1),
        "space_ratio": space_ratio(notes, tpq, n_bars),
        "mean_abs_deviation_ms": round(sum(deviations) / len(deviations), 2),
        "max_abs_deviation_ms": round(max(deviations), 2),
    }


def load_packs(root=MIDI_UNIVERSITY):
    packs = {}
    for folder in sorted(root.iterdir()):
        if not folder.is_dir():
            continue
        meta = parse_folder_name(folder.name)
        if meta is None:
            print(f"  ! skipping folder (name doesn't match convention): {folder.name}",
                  file=sys.stderr)
            continue
        parts = []
        for mid_file in sorted(folder.glob("*.mid")):
            part, section = parse_file_name(mid_file.stem, meta["song"])
            tpq, raw_notes = extract_notes(mid_file)
            notes = [normalize_note(n, tpq, meta["bpm"]) for n in raw_notes]
            parts.append({
                "part": part,
                "section": section,
                "file": mid_file.name,
                "ticks_per_beat": tpq,
                "summary": summarize(notes, tpq, meta["bpm"]),
                "notes": notes,
            })
        packs[meta["song"]] = {**meta, "folder": folder.name, "parts": parts}
    return packs


def print_summary(packs):
    header = f"{'song':<12} {'part':<18} {'sect':<7} {'notes':>5} {'bars':>4} " \
             f"{'vel range':>9} {'space':>6} {'dev ms (avg/max)':>16}"
    print(header)
    print("-" * len(header))
    for song, pack in packs.items():
        for p in pack["parts"]:
            s = p["summary"]
            if s["n_notes"] == 0:
                print(f"{song:<12} {p['part']:<18} {p['section']:<7} {'EMPTY':>5}")
                continue
            vel = f"{s['velocity_min']}-{s['velocity_max']}"
            dev = f"{s['mean_abs_deviation_ms']}/{s['max_abs_deviation_ms']}"
            print(f"{song:<12} {p['part']:<18} {p['section']:<7} {s['n_notes']:>5} "
                  f"{s['n_bars']:>4} {vel:>9} {s['space_ratio']:>6} {dev:>16}")
        print(f"{'':12} key {pack['key']}, {pack['bpm']} bpm\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="print summary only, write nothing")
    args = ap.parse_args()

    packs = load_packs()
    n_files = sum(len(p["parts"]) for p in packs.values())
    print(f"Parsed {len(packs)} packs, {n_files} MIDI files from {MIDI_UNIVERSITY}\n")
    print_summary(packs)

    if not args.dry_run:
        DATA_OUT.parent.mkdir(parents=True, exist_ok=True)
        payload = {"generated": str(date.today()), "source": str(MIDI_UNIVERSITY),
                   "beats_per_bar": BEATS_PER_BAR, "songs": packs}
        DATA_OUT.write_text(json.dumps(payload, indent=1))
        print(f"Wrote {DATA_OUT}")


if __name__ == "__main__":
    main()
