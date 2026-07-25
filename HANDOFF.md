# vi.ve — Handoff / Progress Summary

**For the next assistant.** Read this + CHANGELOG.md + readme.md before doing anything.
Trell's producer profile, vocabulary, and communication rules live OUTSIDE this repo at
`/Users/trell/trell_music_life/README.md` — read that too; it's load-bearing (concrete
numbers, 3–4 options with a "my pick 🥇", no options paralysis, no over-narrating,
deliver MIDI not descriptions).

## What vi.ve is

Trell's assistant music producer: analyze his hand-played MIDI packs → quantify "pocket" →
generate new MIDI via weighted style maps → he grades everything → grades become rules.
End goal: a `vive` Python package that generates on request, then an AI producer bot,
plus waveform analysis (mixing help, audio→MIDI). He is a sr. data analyst (soon
analytics manager) — talk data to him; he grades harshly and precisely, and his feedback
is the tuning signal. **Style established so far: "riding trap."**

## Scorecard (as of 2026-07-24)

| Chapter | State |
|---|---|
| Analysis of hand-played packs | ✅ done — metrics in Postgres, style profile extracted |
| Generation trials 1–8 | ✅ done — 0% → validated; **riding trap ESTABLISHED** (trial 8 ruleset) |
| Self-serve loop | ✅ `notebooks/run_generator.ipynb` (Trell runs trials himself) |
| Trial 9 | ⚠️ generated (by notebook validation), **ungraded** |
| Audio→MIDI pipeline | ✅ v1 + tuning round 1 (pitched) + round 2 (drums, BPM) |
| Ground-truth eval harness | ✅ latency+transposition compensated, stems cached, **per-class drum scoring** |
| Extracted-songs Postgres table | ⏳ NOT built — gated on Trell accepting extraction quality |
| `vive` package / bot | ⏳ future (seed: `scripts/vive_engine.py`) |

## Infrastructure facts (memorize these)

- **Postgres: Postgres.app, port 5431, trust auth, NO password.** Database `vive`.
  Nothing listens on 5432. Tables: `metrics` (long format: song/style/scope/metric/value +
  run_date + source_file), `style_profiles` (jsonb per run), `styles` (name + jsonb recipe;
  'riding trap' = ESTABLISHED; cream packs auto-register as `cream-t{N}-v{XX}` for renaming),
  `trial_results` (every graded file: keep/ehh/cream + diagnostic flags + weights columns).
- **Python: `/Users/trell/anaconda3/bin/python3`** (has mido, librosa, demucs, basic-pitch
  (CoreML), mir_eval, psycopg2, seaborn, nbformat/jupyter).
- **Paths**: hand-played ground truth `~/Music/Ableton/User Library/midi_university/`
  (NEVER modify); machine extractions `~/.../midi_university_auto/`; generated loops
  `~/.../vibes forever/` (folders `t{N} v{XX} key {Key} bpm {bpm}` + dna.txt);
  input songs `/Users/trell/trell_music_life/songs_to_load/` (+ `ground_truth/` with his
  HML exports and `_stems_cache/`).
- **MIDI conventions**: TPQ 480, tempo meta always, Ableton note naming (C3 = MIDI 60).
- Repo is **public** — never commit secrets; run history scans before visibility changes.

## The taste rules that took 8 trials to learn (do not relearn them the hard way)

1. **808 frame**: bass is played on an 808 sample rooted at C3 (MIDI 60). Basslines are
   delivered in that frame. Bar 1 mostly ≤ C4. Bars end on root or b7 (if bar opens on
   root) — never a full octave below root. Loop's final note = root; bar 4 = low point
   (the drop). High↔low register shifting = "bounce" (wanted).
2. **Retired structure**: any bar shaped "+8/octave/octave/octave/+5 above root"
   (= "out there" verse-bass DNA). It is EXCLUDED at the source — "out there" is banned
   from the kick+bass pool (fine for hats/snare/clap/melody vocab). **Curation beats
   down-weighting: P(source appears in 4 bars) = 1-(1-w)⁴.**
3. **Kick+bass locked**: same song supplies both, per bar (co-hit 0.64–1.0 is the style).
4. **Melody**: ONE song's vocabulary per pattern, AA'BA motif, register clamp (≤16-semi
   span) in lead lane E4–E5, pickups/tails across barlines, no overlapping notes.
5. **Weights are probabilities of inheritance, not mix ratios**; dice variance is real →
   every generator runs a best-of-6 candidate gate against a scored rubric.
6. **Grading language**: keep / ehh (blah) / cream (the only real bar). Full-cream pack ⇒
   formula stored. Diagnostic flags map to knobs (wrong lane → register rules, bad
   landing → resolution rules, too random/repetitive → vocab/variation, robotic → feel).

## Audio→MIDI current state

- Pipeline: Demucs (`htdemucs` — bake-off says keep it) → Basic Pitch per melodic stem
  (tuned: onset 0.8 / frame 0.45 / min 60ms) + **per-band drum detection** → packs +
  `data/songs_loaded.csv` log (graded).
- Harness-verified (his beat "HML"): horn 0.86, keys 0.46 clean / 0.54 mixed, horn
  ~0.04 through the mix (WALL). **Drums per-class macro F1 0.77** — kick 0.88,
  hihat 0.84, **snare 0.58 (the weak lane)**.
- **Grades so far**: melody 3.2–4.4 (piano best, sampled leads worst), bassline 3.8 flat
  across all songs, drums 0/5 *before* the round-2 fixes.

## Two traps this project has now fallen into TWICE — check for them first

1. **Optimising against a metric that cannot see the failure.** Trial 7 was weights vs
   curation. Round 1 tuned drums against union-onset recall (0.52→0.57, "improving")
   while Trell graded the same packs **0/5** — the metric never asked *which drum*.
   Before tuning anything, confirm the metric can distinguish the thing being graded.
2. **Blaming the model for a clock error.** Extracted packs looked 15–21% on-grid, which
   reads as bad transcription. It was `librosa.beat_track` being ~1% off: harmless in a
   4-bar loop, fatal over 40+ bars, where it accumulates into a full 16th of drift.
   `refine_bpm()` fixes it and lifts drums, melody and bass at once. **When timing looks
   bad across every part at once, suspect the tempo before the transcriber.**

## Open threads, in priority order

1. **Trell's ear test on the round-2 packs** — first extraction where the tempo is
   actually right. His grades decide everything below. 5 songs now (COSTLY. and Drake
   "What Would Pluto Do" joined; both ungraded).
2. **Bassline is 3.8 on every song** — a flat score across different songs is a
   systematic ceiling, not a song problem. Nothing folds extracted bass into the C3/808
   frame yet; the harness's `detected_shift_semis` is exactly that fold. Likely the
   cheapest remaining point of grade.
3. **Snare lane 0.58** — predicted snares land kick 96 / snare 92 / hihat 83, near a coin
   flip. Giving snare the 1500–6000 Hz band was TESTED and made it worse (0.58→0.47,
   hat bleed). A trained model (madmom / E-GMD) is the named candidate — note madmom is
   NOT installed and its last PyPI release predates Python 3.11 (env is 3.11.5, numpy
   1.24.3, which is in range), so budget an install fight. Judge it by per-class macro F1.
4. **Kick lane is timing-jittery** — 26–36% on a 16th grid vs snare 81–91%, hat 81–94%.
   A constant shift recovers 1–2 points, so it is jitter, not lag: onsets inside a
   20–150 Hz band are smeared because the waveform period there is 7–50ms. It passes the
   harness (±50ms, F1 0.88) and fails the grid (±15ms); both metrics are right.
   **Fix: detect the transient broadband, use the low band only to attribute it** —
   snap kick times to the nearest full-spectrum onset.
5. **Hi-hat recall 0.73** — quiet hats buried by separation, not by the classifier.
6. **Trial 9 is ungraded** in `vibes forever/` — remind him gently, don't nag.
7. **Sampled-lead wall**: horns/flutes in a mix are destroyed by all Demucs variants.
   Ideas: Basic Pitch straight on the full mix (untested), vocal-specialist separators
   (BS-Roformer via `audio-separator`), or accept-and-document.
8. **Extracted-songs Postgres table** — Trell's spec: once he deems quality adequate,
   store extraction info so vi.ve can build styles from real songs. Not before he says so.
9. **Per-stem Basic Pitch overrides** — keys-only prefers min_note_len 200 (0.53 vs 0.46)
   but that ZEROES the horn. Round 1 left this as a known refinement.
10. **Growing `midi_university`** with new hand-played packs (MIDI keyboard cable was
   broken; may be fixed by now) → new styles via the established loop.
11. Long-term: `vive` package → ask-for-what-you-want generation → producer bot.

## How to work with Trell (the short version)

Propose → deliver → iterate. Give real numbers, real files, a clear pick. He will tell
you precisely what's wrong; turn every criticism into a named rule or metric and show
him the before/after. Log failures honestly in readme milestones — the trial-7 post-mortem
(measure, don't guess) is the house style. Commit and push after each meaningful unit
of work; he treats the git history as part of the record.
