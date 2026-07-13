#!/usr/bin/env python3
"""
intra_pack_analysis.py — How the parts of each song complement each other.

Answers the mindDump questions with numbers:
  - KTB family (upgraded 2026-07-12): kick<->bass hit ratio, co-hit rate,
    lead/lag direction + consistency, kick-leads-into-bass rate
  - Space: space ratio, onset density, longest gap
  - Syncopation: Longuet-Higgins & Lee index on the 16th grid (target-zone metric)
  - Hats: business score, roll detection (32nd-ish runs), do rolls precede other hits?
  - Harmony: how much the bassline agrees with the chords/keys
  - Sections: what stays constant vs. changes across the (2) 4-bar sections
  - Reliability flags: velocity/timing channels marked unusable when degenerate
    (first 3 packs were drawn / laptop-keyboard played -> flat velocity is expected)

Reads  : vi.ve/data/parsed_packs.json   (produced by parse_packs.py)
Writes : vi.ve/data/intra_pack_metrics.csv  in long format:
         song, style, scope, metric, value
         (scope = one part, or "partA|partB" for relationship metrics)

Usage:
    python3 scripts/intra_pack_analysis.py
"""

import csv
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PACKS_JSON = DATA_DIR / "parsed_packs.json"
OUT_CSV = DATA_DIR / "intra_pack_metrics.csv"

BEATS_PER_BAR = 4
STEPS_PER_BAR = 16

# Style labels per song — edit these as the library grows.
SONG_STYLE = {"morning": "hip-hop", "out there": "hip-hop", "sicko mode": "hip-hop"}

# part name -> instrument role
ROLES = {
    "bassline": "bass", "kick": "kick", "snare": "snare", "clap": "clap",
    "hihat": "hat", "chord progression": "chords", "keys": "chords", "melody": "melody",
}

# LHL-style metrical weights for each 16th position in a 4/4 bar
# (the 1 is strongest, then beat 3, then beats 2/4, then 8th offbeats, then 16ths)
METRICAL_WEIGHT = [5, 1, 2, 1, 3, 1, 2, 1, 4, 1, 2, 1, 3, 1, 2, 1]


# ---------------------------------------------------------------- helpers

def pattern_bars(part):
    """Patterns are 4 or 8 bars by convention; last-note estimates can undershoot."""
    n = part["summary"].get("n_bars", 4)
    return 4 if n <= 4 else 8


def pattern_ticks(part, tpq):
    return pattern_bars(part) * BEATS_PER_BAR * tpq


def onsets(part):
    return [n["start_tick"] for n in part["notes"]]


def tile(ticks, own_len, target_len):
    """Repeat a looping pattern's onset ticks to cover target_len ticks."""
    out, offset = [], 0
    while offset < target_len:
        out.extend(t + offset for t in ticks if t + offset < target_len)
        offset += own_len
    return sorted(out)


def velocity_reliable(part):
    s = part["summary"]
    return s["n_notes"] > 1 and s["velocity_min"] != s["velocity_max"]


def timing_played(part):
    return part["summary"].get("max_abs_deviation_ms", 0) > 1.0


# ---------------------------------------------------------------- per-part metrics

def part_metrics(part, tpq):
    s = part["summary"]
    bars = pattern_bars(part)
    total = pattern_ticks(part, tpq)
    rows = {
        "space_ratio": s["space_ratio"],
        "onset_density_per_bar": round(s["n_notes"] / bars, 2),
        "velocity_reliable": int(velocity_reliable(part)),
        "timing_played": int(timing_played(part)),
        "mean_abs_deviation_ms": s.get("mean_abs_deviation_ms", 0),
    }

    ticks = onsets(part)
    if len(ticks) >= 2:
        gaps = [b - a for a, b in zip(ticks, ticks[1:])]
        gaps.append(total - ticks[-1] + ticks[0])  # loop-around gap
        rows["longest_gap_beats"] = round(max(gaps) / tpq, 2)

    rows["syncopation_lhl"] = syncopation(part)
    return rows


def syncopation(part):
    """Normalized LHL syncopation: onset on a weak position with a rest on the
    following stronger position scores (strong weight - weak weight)."""
    positions = {n["grid16_in_bar"] + (n["bar"] % 4) * STEPS_PER_BAR for n in part["notes"]}
    if not positions:
        return 0.0
    n_steps = pattern_bars(part) * STEPS_PER_BAR
    if pattern_bars(part) == 8:
        positions = {(n["grid16_in_bar"] + n["bar"] * STEPS_PER_BAR) for n in part["notes"]}
        n_steps = 8 * STEPS_PER_BAR
    score = 0
    for p in positions:
        w = METRICAL_WEIGHT[p % STEPS_PER_BAR]
        for ahead in range(1, STEPS_PER_BAR):
            q = (p + ahead) % n_steps
            wq = METRICAL_WEIGHT[q % STEPS_PER_BAR]
            if wq > w:
                if q not in positions:  # rest on the stronger beat = syncopation
                    score += wq - w
                break
    return round(score / len(positions), 3)


# ---------------------------------------------------------------- hat rolls

def hat_rolls(part, tpq, other_parts):
    """Detect roll runs (>=3 same-pitch onsets tighter than a 16th) and check
    whether each roll resolves into another instrument's hit within an 8th note."""
    tick16 = tpq / 4
    notes = sorted(part["notes"], key=lambda n: n["start_tick"])
    rolls, run = [], [notes[0]] if notes else []
    for prev, cur in zip(notes, notes[1:]):
        if (cur["start_tick"] - prev["start_tick"]) < 0.7 * tick16 and cur["pitch"] == prev["pitch"]:
            run.append(cur)
        else:
            if len(run) >= 3:
                rolls.append(run)
            run = [cur]
    if len(run) >= 3:
        rolls.append(run)

    result = {
        "roll_count": len(rolls),
        "rolls_per_4_bars": round(len(rolls) / (pattern_bars(part) / 4), 2),
    }
    if rolls:
        own_len = pattern_ticks(part, tpq)
        resolves = 0
        end_beats = []
        for r in rolls:
            end = r[-1]["start_tick"]
            end_beats.append(round((end / tpq) % BEATS_PER_BAR + 1, 2))  # musician count: 1-4
            window = (end, end + tpq / 2)  # within an 8th after the roll ends
            for op in other_parts:
                tiled = tile(onsets(op), pattern_ticks(op, tpq), own_len)
                if any(window[0] < t <= window[1] for t in tiled):
                    resolves += 1
                    break
        result["roll_resolves_into_hit_rate"] = round(resolves / len(rolls), 2)
        result["roll_end_beats"] = end_beats  # reported in text, not CSV math
    return result


def hat_business(part):
    """Composite busyness: onset density + roll presence + velocity spread (if usable)."""
    s = part["summary"]
    density = s["n_notes"] / pattern_bars(part) / STEPS_PER_BAR  # 1.0 = every 16th
    vel_spread = (s["velocity_max"] - s["velocity_min"]) / 127 if velocity_reliable(part) else None
    pitch_variety = (len(s["unique_pitches"]) - 1) / 4
    parts_avail = [min(density, 1.0), min(pitch_variety, 1.0)]
    if vel_spread is not None:
        parts_avail.append(vel_spread)
    return round(sum(parts_avail) / len(parts_avail), 3)


# ---------------------------------------------------------------- pair metrics

def alignment(part_a, part_b, tpq, tol_ticks):
    """KTB-family alignment between two onset patterns (a = reference, e.g. kick).

    Returns hit ratio, co-hit rates, mean signed lag of b vs a (positive = b late/behind),
    lag consistency, and a-leads-into-b rate (a hits in the 8th before a b onset)."""
    len_a, len_b = pattern_ticks(part_a, tpq), pattern_ticks(part_b, tpq)
    span = max(len_a, len_b)
    a = tile(onsets(part_a), len_a, span)
    b = tile(onsets(part_b), len_b, span)
    if not a or not b:
        return None

    co, lags = 0, []
    for t in b:
        nearest = min(a, key=lambda x: abs(x - t))
        d = t - nearest
        if abs(d) <= tol_ticks:
            co += 1
            lags.append(d)

    eighth = tpq / 2
    leads = sum(1 for t in b if any(t - eighth <= x < t - tol_ticks for x in a))

    rows = {
        "hit_ratio": round(len(a) / len(b), 2),
        "co_hit_rate": round(co / len(b), 2),          # share of b onsets with an a partner
        "lead_in_rate": round(leads / len(b), 2),       # a plays just before a b hit
    }
    if lags:
        mean_lag = sum(lags) / len(lags)
        ms = (60_000 / part_a.get("_bpm", 120)) / tpq
        rows["mean_lag_ticks"] = round(mean_lag, 2)
        rows["mean_lag_ms"] = round(mean_lag * ms, 2)
        if len(lags) > 1:
            var = sum((l - mean_lag) ** 2 for l in lags) / (len(lags) - 1)
            rows["lag_std_ticks"] = round(var ** 0.5, 2)
    return rows


def harmony_agreement(bass, harmonic, tpq):
    """Share of bass onsets whose pitch class appears in the harmonic part within a
    beat-wide window around the onset (instantaneous matching is too strict when the
    harmonic part is a short-note arp), and share landing on that window's lowest
    pitch class (the root move)."""
    len_b, len_h = pattern_ticks(bass, tpq), pattern_ticks(harmonic, tpq)
    span = max(len_b, len_h)

    h_events = []
    offset = 0
    while offset < span:
        for n in harmonic["notes"]:
            s = n["start_tick"] + offset
            if s < span:
                h_events.append((s, s + n["duration_ticks"], n["pitch"]))
        offset += len_h

    in_chord = on_root = counted = 0
    offset = 0
    while offset < span:
        for n in bass["notes"]:
            t = n["start_tick"] + offset
            if t >= span:
                continue
            lo, hi = t - tpq / 2, t + tpq / 2
            sounding = [p for (s, e, p) in h_events if s < hi and e > lo]
            if not sounding:
                continue
            counted += 1
            if n["pitch"] % 12 in {p % 12 for p in sounding}:
                in_chord += 1
            if n["pitch"] % 12 == min(sounding) % 12:
                on_root += 1
        offset += len_b
    if not counted:
        return None
    return {"bass_chord_tone_rate": round(in_chord / counted, 2),
            "bass_on_root_rate": round(on_root / counted, 2)}


# ---------------------------------------------------------------- sections

def section_grid(notes, bar_lo, bar_hi):
    return {(n["bar"] - bar_lo) * STEPS_PER_BAR + n["grid16_in_bar"]
            for n in notes if bar_lo <= n["bar"] < bar_hi}


def section_comparison(grid_a, grid_b):
    """Jaccard stability of two 4-bar onset grids + what changed."""
    union = grid_a | grid_b
    if not union:
        return None
    inter = grid_a & grid_b
    return {
        "section_stability": round(len(inter) / len(union), 2),
        "steps_only_in_A": len(grid_a - grid_b),
        "steps_only_in_B": len(grid_b - grid_a),
    }


# ---------------------------------------------------------------- main

def main():
    data = json.loads(PACKS_JSON.read_text())
    rows = []       # (song, style, scope, metric, value)
    highlights = []

    def emit(song, scope, metric, value):
        rows.append((song, SONG_STYLE.get(song, "unlabeled"), scope, metric, value))

    for song, pack in data["songs"].items():
        parts = pack["parts"]
        tpq_of = {p["file"]: p["ticks_per_beat"] for p in parts}
        for p in parts:
            p["_bpm"] = pack["bpm"]

        def named(role, section=None):
            found = [p for p in parts if ROLES.get(p["part"]) == role]
            if section:
                found = [p for p in found if p["section"] in (section, "both")]
            return found

        # ---- per-part metrics
        for p in parts:
            tpq = p["ticks_per_beat"]
            scope = p["part"] if p["section"] in ("both",) else f"{p['section']} {p['part']}"
            for metric, value in part_metrics(p, tpq).items():
                emit(song, scope, metric, value)
            if ROLES.get(p["part"]) == "hat":
                emit(song, scope, "hat_business", hat_business(p))
                others = [o for o in parts if o is not p and ROLES.get(o["part"]) in
                          ("kick", "snare", "clap", "bass")]
                for metric, value in hat_rolls(p, tpq, others).items():
                    if metric == "roll_end_beats":
                        highlights.append(f"{song}: hat rolls end at beats {value}")
                        continue
                    emit(song, scope, metric, value)

        # ---- kick <-> bass alignment (per bass variant), plus snare/clap vs bass
        kicks = named("kick")
        for bass in named("bass"):
            b_scope = bass["part"] if bass["section"] == "both" else f"{bass['section']} {bass['part']}"
            for kick in kicks:
                tpq = kick["ticks_per_beat"]
                tol = tpq / 8  # within half a 16th counts as together
                al = alignment(kick, bass, tpq, tol)
                if al:
                    for metric, value in al.items():
                        emit(song, f"kick|{b_scope}", f"ktb_{metric}", value)

            # ---- bass vs harmony
            for harm in named("chords", bass["section"]):
                ha = harmony_agreement(bass, harm, bass["ticks_per_beat"])
                if ha:
                    for metric, value in ha.items():
                        emit(song, f"{b_scope}|{harm['part']}", metric, value)

        # ---- section comparisons
        for p in parts:
            bars = pattern_bars(p)
            scope = p["part"]
            if bars == 8:  # one file spanning both 4-bar sections
                cmp = section_comparison(section_grid(p["notes"], 0, 4),
                                         section_grid(p["notes"], 4, 8))
                if cmp:
                    for metric, value in cmp.items():
                        emit(song, scope, metric, value)
        # verse vs chorus variants of the same part
        by_part = {}
        for p in parts:
            by_part.setdefault(p["part"], []).append(p)
        for part_name, variants in by_part.items():
            secs = {p["section"]: p for p in variants}
            if "verse" in secs and "chorus" in secs:
                cmp = section_comparison(section_grid(secs["verse"]["notes"], 0, 4),
                                         section_grid(secs["chorus"]["notes"], 0, 4))
                if cmp:
                    for metric, value in cmp.items():
                        emit(song, f"verse {part_name}|chorus {part_name}", metric, value)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["song", "style", "scope", "metric", "value"])
        w.writerows(rows)
    print(f"Wrote {len(rows)} metric rows -> {OUT_CSV}\n")

    # readable digest of the relationship metrics
    print(f"{'song':<12} {'scope':<34} {'metric':<28} {'value':>8}")
    print("-" * 84)
    for song, style, scope, metric, value in rows:
        if "|" in scope or metric in ("space_ratio", "syncopation_lhl", "hat_business",
                                      "rolls_per_4_bars", "section_stability"):
            print(f"{song:<12} {scope:<34} {metric:<28} {value:>8}")
    for h in highlights:
        print("\n" + h)


if __name__ == "__main__":
    main()
