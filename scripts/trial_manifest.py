#!/usr/bin/env python3
"""
trial_manifest.py — Manifest v2: the expanded audition questionnaire.

Three quality tiers per file (Trell's design):
    keep   worth keeping at all
    ehh    not bad, but blah / middle-of-the-road
    cream  cream of the crop — the only patterns actually wanted; a full-cream
           pack's formula gets auto-registered in the `styles` Postgres table

Plus diagnostic y/n flags. Every flag maps to a specific generator knob, so a `y`
tells the next iteration exactly what to tweak:

    fixable         one small edit from a keeper       -> iteration priority
    too busy        too many notes                     -> density target zone down
    too empty       not enough going on                -> density zone up / space cap
    too random      no clear motif or logic            -> motif repetition up, vocab tighter
    too repetitive  loops on itself too hard           -> mutation/variation rate up
    robotic         velocity/feel sounds programmed    -> velocity model + microtiming
    wrong lane      register/octave is off             -> LEAD_LANE / bass floor+ceiling
    bad landing     bar-4 resolution / loop restart    -> end-low + resolve rules

Pack-level row (file = "WHOLE PACK") adds:
    gels            parts sound like one song          -> cross-role coherence rules
    rides           has the pocket / bounce            -> the Riding Trap test
    song worthy     would actually build a song on it  -> the real KPI

Tips: cream=y implies keep=y. Diagnostics only needed where something's off —
blank means "no comment." Pack questions only on the WHOLE PACK row.
"""

import csv

FILE_COLUMNS = ["keep", "ehh", "cream", "fixable", "too busy", "too empty",
                "too random", "too repetitive", "robotic", "wrong lane", "bad landing"]
PACK_COLUMNS = ["gels", "rides", "song worthy"]


def write_manifest_csv(path, prefix, combos):
    """combos: list of manifest dicts with id/label/key/bpm/weights."""
    header = (["combo", "file", "key", "bpm", "weights"]
              + [f"{c} (y/n)" for c in FILE_COLUMNS]
              + [f"{c} (y/n)" for c in PACK_COLUMNS])
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for m in combos:
            weights = " ".join(f"{s}:{v}" for s, v in m["weights"].items())
            for kind in ("melody", "bassline", "drums"):
                w.writerow([f"{prefix} {m['id']}", f"{prefix} {m['id']} - {kind}.mid",
                            m["key"], m["bpm"], weights]
                           + [""] * len(FILE_COLUMNS) + ["", "", ""])
            w.writerow([f"{prefix} {m['id']}", "WHOLE PACK", m["key"], m["bpm"], weights]
                       + [""] * len(FILE_COLUMNS) + [""] * len(PACK_COLUMNS))
