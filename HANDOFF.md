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
| Audio→MIDI pipeline | ✅ v1 built + harness-tuned round 1 |
| Ground-truth eval harness | ✅ working, latency+transposition compensated, stems cached |
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
  (tuned: onset 0.8 / frame 0.45 / min 60ms) + onset/band drum classify (delta 0.02) →
  packs + `data/songs_loaded.csv` log.
- Harness-verified quality (his beat "HML" ground truth): clean-stem drums 0.80–1.00,
  horn 0.86, keys 0.46 (keys-only prefers min_len 200 — per-stem overrides TODO);
  through the mix: keys 0.54, drum recall 0.57, horn ~0.04 (WALL — see below).
- His ear test on 3 real songs matched the numbers: piano melodies best, sampled
  flute/horn leads worst (trill splitting), drums failed (separation recall + classifier).

## Open threads, in priority order

1. **Quiet the audio_to_midi notebook run cell** — Trell asked; interrupted by this
   handoff. Silence Demucs/coremltools/librosa noise; keep per-song success lines only.
2. **Trial 9 is ungraded** in `vibes forever/` — remind him gently, don't nag.
3. **808 round**: CREPE (or similar) for sub-bass, wider onset tolerance for slow attacks,
   and use the harness's `detected_shift` to auto-fold extracted bass into the C3 frame.
4. **Sampled-lead wall**: horns/flutes in a mix are destroyed by all Demucs variants.
   Ideas: Basic Pitch straight on the full mix (untested), vocal-specialist separators
   (BS-Roformer via `audio-separator`), or accept-and-document.
5. **Drum upgrade**: recall stuck ~0.57 (quiet hats buried) and the kick/snare/hat
   classifier is homemade — a trained drum-transcription model (madmom / E-GMD family)
   is the named next candidate, judged by the harness.
6. **Extracted-songs Postgres table** — Trell's spec: once he deems quality adequate,
   store extraction info so vi.ve can build styles from real songs. Not before he says so.
7. **Re-run the 3 test songs** with tuned config (`force=True`) for his ear-acceptance test.
8. **Growing `midi_university`** with new hand-played packs (MIDI keyboard cable was
   broken; may be fixed by now) → new styles via the established loop.
9. Long-term: `vive` package → ask-for-what-you-want generation → producer bot.

## How to work with Trell (the short version)

Propose → deliver → iterate. Give real numbers, real files, a clear pick. He will tell
you precisely what's wrong; turn every criticism into a named rule or metric and show
him the before/after. Log failures honestly in readme milestones — the trial-7 post-mortem
(measure, don't guess) is the house style. Commit and push after each meaningful unit
of work; he treats the git history as part of the record.
