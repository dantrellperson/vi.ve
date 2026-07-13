#!/usr/bin/env python3
"""
cross_song_trends.py — What the songs AGREE on. Agreement = style.

Answers the cross-song questions from the mindDump:
  - Position consensus: per instrument role, which 16th positions are used by
    all 3 songs (universal), 2 of 3 (common), or only 1 (song-specific)?
    -> statements like "the kick always hits the 1"
  - Shared rhythm phrases: recurring inter-onset n-grams that appear in >= 2 songs
    -> statements like "a 16th-16th-8th run shows up everywhere"
  - Metric target zones: for every metric in intra_pack_metrics.csv, the min/mean/max
    across songs per role. Per the Witek decision, generation aims INSIDE the zone.
  - Key relatedness: semitone + circle-of-fifths distance between the songs' keys.

Reads  : data/parsed_packs.json, data/intra_pack_metrics.csv
Writes : data/style_profile.json   <- seed of the weighted style map
         data/cross_song_trends.csv (long format: song=ALL rows)

Usage:
    python3 scripts/cross_song_trends.py
"""

import csv
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PACKS_JSON = DATA_DIR / "parsed_packs.json"
METRICS_CSV = DATA_DIR / "intra_pack_metrics.csv"
PROFILE_OUT = DATA_DIR / "style_profile.json"
TRENDS_OUT = DATA_DIR / "cross_song_trends.csv"

STEPS_PER_BAR = 16

ROLES = {
    "bassline": "bass", "kick": "kick", "snare": "snare", "clap": "clap",
    "hihat": "hat", "chord progression": "chords", "keys": "chords", "melody": "melody",
}

NOTE_PC = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5,
           "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}


def parse_key(key):
    """'Ebm' -> (pc 3, 'minor');  'C' -> (0, 'major')"""
    name, mode = (key[:-1], "minor") if key.endswith("m") else (key, "major")
    return NOTE_PC[name], mode


def cof_distance(pc_a, pc_b):
    """Steps apart on the circle of fifths (0-6)."""
    pos = {(7 * i) % 12: i for i in range(12)}
    d = abs(pos[pc_a] - pos[pc_b])
    return min(d, 12 - d)


def role_of(scope):
    """Map a metrics-CSV scope ('verse bassline', 'kick|bassline') to a role key."""
    if "|" in scope:
        left, right = scope.split("|", 1)
        return f"{role_of(left)}|{role_of(right)}"
    for part, role in ROLES.items():
        if scope == part or scope.endswith(" " + part):
            return role
    return scope


def positions_in_bar(part):
    return {n["grid16_in_bar"] for n in part["notes"]}


def ioi_ngrams(part, n):
    """n-grams of inter-onset intervals, in rounded 16th steps."""
    tpq = part["ticks_per_beat"]
    ticks = sorted({note["start_tick"] for note in part["notes"]})
    iois = [round((b - a) / (tpq / 4)) for a, b in zip(ticks, ticks[1:])]
    return Counter(tuple(iois[i:i + n]) for i in range(len(iois) - n + 1))


def main():
    data = json.loads(PACKS_JSON.read_text())
    songs = data["songs"]
    song_names = list(songs)

    # ---- group parts by role, per song
    by_role = defaultdict(lambda: defaultdict(list))  # role -> song -> [parts]
    for song, pack in songs.items():
        for p in pack["parts"]:
            role = ROLES.get(p["part"])
            if role:
                by_role[role][song].append(p)

    profile = {
        "generated": str(date.today()),
        "style": "hip-hop",
        "songs": {s: {"key": songs[s]["key"], "bpm": songs[s]["bpm"]} for s in song_names},
        "key_relations": [],
        "roles": {},
        "pair_metric_zones": {},
    }
    trend_rows = []

    # ---- key relatedness
    for i, a in enumerate(song_names):
        for b in song_names[i + 1:]:
            pc_a, mode_a = parse_key(songs[a]["key"])
            pc_b, mode_b = parse_key(songs[b]["key"])
            rel = {
                "a": f"{a} ({songs[a]['key']})", "b": f"{b} ({songs[b]['key']})",
                "same_key": songs[a]["key"] == songs[b]["key"],
                "semitone_distance": min((pc_a - pc_b) % 12, (pc_b - pc_a) % 12),
                "cof_distance": cof_distance(pc_a, pc_b),
                "same_mode": mode_a == mode_b,
            }
            profile["key_relations"].append(rel)
            trend_rows.append(("ALL", "hip-hop", f"{a}|{b}", "key_cof_distance",
                               rel["cof_distance"]))

    # ---- position consensus + shared n-grams, per role
    for role, per_song in sorted(by_role.items()):
        n_songs = len(per_song)
        pos_counts = Counter()
        for song, parts in per_song.items():
            song_positions = set()
            for p in parts:
                song_positions |= positions_in_bar(p)
            for pos in song_positions:
                pos_counts[pos] += 1

        universal = sorted(p for p, c in pos_counts.items() if c == n_songs)
        common = sorted(p for p, c in pos_counts.items() if c == n_songs - 1 >= 2)

        grams = defaultdict(lambda: [0, 0])  # ngram -> [n_songs_with_it, total_count]
        for n in (2, 3):
            for song, parts in per_song.items():
                song_grams = Counter()
                for p in parts:
                    song_grams.update(ioi_ngrams(p, n))
                for g, c in song_grams.items():
                    grams[g][0] += 1
                    grams[g][1] += c
        shared = [{"ioi_16ths": list(g), "songs": sc, "count": tc}
                  for g, (sc, tc) in sorted(grams.items(),
                                            key=lambda kv: (-kv[1][0], -kv[1][1]))
                  if sc >= 2][:8]

        profile["roles"][role] = {
            "songs_with_role": n_songs,
            "universal_positions_16th": universal,
            "majority_positions_16th": common,
            "shared_ioi_ngrams": shared,
            "metric_zones": {},
        }
        trend_rows.append(("ALL", "hip-hop", role, "n_universal_positions", len(universal)))

    # ---- metric target zones from intra_pack_metrics.csv
    zones = defaultdict(list)  # (role_scope, metric) -> [values]
    with METRICS_CSV.open() as f:
        for row in csv.DictReader(f):
            try:
                zones[(role_of(row["scope"]), row["metric"])].append(float(row["value"]))
            except ValueError:
                continue

    for (scope, metric), values in sorted(zones.items()):
        zone = {"min": min(values), "mean": round(sum(values) / len(values), 3),
                "max": max(values), "n": len(values)}
        if "|" in scope:
            profile["pair_metric_zones"].setdefault(scope, {})[metric] = zone
        elif scope in profile["roles"]:
            profile["roles"][scope]["metric_zones"][metric] = zone
        trend_rows.append(("ALL", "hip-hop", scope, f"zone_{metric}",
                           f"{zone['min']}..{zone['max']}"))

    # ---- write outputs
    PROFILE_OUT.write_text(json.dumps(profile, indent=1))
    with TRENDS_OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["song", "style", "scope", "metric", "value"])
        w.writerows(trend_rows)
    print(f"Wrote {PROFILE_OUT}")
    print(f"Wrote {len(trend_rows)} trend rows -> {TRENDS_OUT}\n")

    # ---- digest
    beat_name = lambda p: f"{p // 4 + 1}{['', '-e', '-and', '-ah'][p % 4]}"
    for role, info in profile["roles"].items():
        uni = ", ".join(beat_name(p) for p in info["universal_positions_16th"]) or "(none)"
        print(f"{role:<8} universal positions ({info['songs_with_role']}/3 songs): {uni}")
        top = info["shared_ioi_ngrams"][:3]
        if top:
            phrases = "; ".join(f"{g['ioi_16ths']} in {g['songs']} songs x{g['count']}"
                                for g in top)
            print(f"{'':8} shared IOI phrases (16ths): {phrases}")
    print()
    for rel in profile["key_relations"]:
        print(f"keys: {rel['a']} <-> {rel['b']}: "
              f"{'SAME KEY' if rel['same_key'] else str(rel['semitone_distance']) + ' semitones, COF ' + str(rel['cof_distance'])}")


if __name__ == "__main__":
    main()
