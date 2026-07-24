# vi.ve — Changelog

All notable work, chronological. Written for handoff: a new assistant should be able to
reconstruct the project's reasoning from this file + HANDOFF.md + readme.md.

---

## 2026-07-12 — Foundation

- **Repo created** (private initially, later public) at github.com/dantrellperson/vi.ve.
  GitHub PAT that was in mindDump.txt was removed BEFORE the first commit (never leaked);
  Trell revoked it and re-authenticated via `gh auth login` + SSH.
- **readme.md reorganized** from mindDump into problem statement, NLP↔music analogy table,
  dataset docs, analysis framework, metrics plan.
- **Research review** (5 sources) with recorded decisions:
  - GrooVAE score/feel split → ADOPTED as core representation (grid position + deviation + velocity)
  - Witek inverted-U syncopation → metrics scored against TARGET ZONES, not higher/lower-better
  - Senn microtiming → per-style microtiming weight (low for trap, high for melodic)
  - Danielsen beat bins → KTB upgraded from ratio to alignment family (co-hit, lead/lag)
  - REMI/MidiTok → validated the NLP framing; n-gram rhythm analysis adopted
- **`scripts/parse_packs.py`** — parses `~/Music/Ableton/User Library/midi_university/`
  (3 hand-played packs, 19 files) into `data/parsed_packs.json` with score/feel split.
  Found: velocity flat in 15/19 files (drawn/laptop-keyboard input — cable broken), so
  velocity channel is unreliable; timing quantized except hats/melodies.
- **`scripts/intra_pack_analysis.py`** → `data/intra_pack_metrics.csv` (179 long-format rows):
  KTB family, space ratios, LHL syncopation, hat-roll detection, section stability,
  bass↔harmony agreement (beat-wide window). Key findings: kick↔bass co-hit 0.64–1.0
  (style signature), space lives in drums, rolls end right before beat 3 (morning) or the 1.
- **`scripts/cross_song_trends.py`** → `data/style_profile.json`: position consensus
  (kick universal: 1, 2-and, 3-and, 4-e), shared IOI n-grams (tresillo `[3,3]` in all songs),
  key relations. **Headline: the kick grammar is the tresillo.**
- **`config/style_defaults.json`** — fallback values for unreliable channels
  (velocity ranges per role, 25ms microtiming cap, 1 roll per 4 bars).

## 2026-07-13 — Trials 1–9: Riding Trap established

- **Postgres storage**: local **Postgres.app, port 5431, trust auth (NO password)**, db `vive`.
  `scripts/load_postgres.py` → tables `metrics` (long format + run_date) and `style_profiles`
  (jsonb per run). NOTE: 5432 has no server; an old prompt-for-password install confused setup.
- **Trial 01** (`generate_vibes.py`, weighted bar collage): 0/24 kept. Melodies "channel surf."
- **`notebooks/trial_01_review.ipynb`** — root cause: melody pool between-song spread ~2×
  any other role (density 30/10/8 per bar, three registers, zero shared phrases).
- **`styles` table** (`scripts/register_style.py`) — named style recipes as jsonb.
  First style registered: **"riding trap"** (thumping sub basslines, riding-in-the-car energy).
- **Trial 02** (grammar melody engine, AA'BA motif): 11/24 (46%).
- **Trial 03** (anchor-song kick+bass lock, winner-takes-vocabulary melody, bass register
  bounce/end-low rules): 17/24 (71%).
- **Trial 04** (melody register clamp ±8 semis around median + lead lane E4–E5 + overlap fix):
  19/24 (79%), melodies 7/8.
- **Manifest v2** (`scripts/trial_manifest.py`): keep/**ehh**/**cream** tiers + diagnostic
  flags (fixable, too busy/empty/random/repetitive, robotic, wrong lane, bad landing) +
  pack-level gels/rides/song-worthy. `scripts/load_trial_results.py` loads verdicts into
  `trial_results` and AUTO-REGISTERS full-cream packs into `styles`.
- **Trial 05** (v04-weights dice experiment): 24/24 keep, 18/24 cream, 3 full-cream packs.
  Proved per-run dice variance is real; no weight recipe is a "dead zone."
- **Trial 06** (bass lane fold, root landing, 6-candidate scoring gate): harsher standards
  arrived — bass exposed (1/8), wrong-lane flags on 7/8.
- **Trell's evolved bass standards**: 808 audio sample with **root at middle C = C3 = MIDI 60**
  (Ableton naming); bar 1 mostly ≤ C4; bars end on root or b7, never an octave below root;
  the "+8/octave/octave/+5" bar structure RETIRED.
- **Trial 07** (808 frame + pitch folds): ALL basslines failed. **Post-mortem** (the big
  lesson): every failed bass contained bars from "out there"'s verse bassline; the octave
  fold only disguised it; P(source in 4-bar collage) = 1-(1-w)⁴ ≈ 87% at w=0.4; fix-check
  rerolls of flagged recipes pushed contamination 25%→37.5%→47%. **Curation beats weighting.**
- **Trial 08** (`generate_vibes_v8.py`): "out there" REMOVED from kick+bass anchor pool
  (still supplies hats/snare/clap/melody vocab). Trell: **"riding trap established."**
- `styles.recipe` for riding trap updated to ESTABLISHED with full ruleset.
- **`scripts/vive_engine.py`** — callable API (`run_trial`, `random_combos`,
  `combos_from_style`, `next_trial_number`); seed of the future `vive` package.
- **`notebooks/run_generator.ipynb`** — self-serve loop: configure → generate → grade →
  load (with cream auto-registration). Its validation run generated **Trial 09 (ungraded)**.
- **`notebooks/style_evolution_review.ipynb`** — the 8-trial arc, contamination chart, lessons.
- **Loop folder naming**: `t{N} v{XX} key {Key} bpm {bpm}` + `dna.txt` inside each folder
  (weights, per-bar sources, bass bar-1 notes, gate scores).
- Repo made **public** after full-history secret scan (clean).

## 2026-07-24 — Audio → MIDI chapter

- **`scripts/audio_to_midi.py`** + **`notebooks/audio_to_midi.ipynb`** (flowchart + plain-english):
  songs dropped in `trell_music_life/songs_to_load/` → Demucs 4-stem separation → Basic Pitch
  (CoreML backend) per melodic stem + onset/band-classify drums → packs in
  `~/Music/Ableton/User Library/midi_university_auto/` (SEPARATE from hand-played ground truth)
  → log in `data/songs_loaded.csv` with quality columns. Vocals transcribed as "vocal melody."
- **Trell's ear test on 3 songs** (Big 5, New Topic, Aye Tay): basslines ~2.8/5,
  piano melodies best (New Topic 2.8/5), sample-based melodies worse (flute trills split
  into note spam), **drums total failure**.
- **`scripts/transcription_eval.py`** — ground-truth harness. Trell exports from his own
  beat (HML, 151bpm) to `songs_to_load/ground_truth/`: MIDI clips (answer key) + solo
  bounces + full mix. Test A = clean-stem transcription; Test B = full pipeline (Demucs
  stems cached in `ground_truth/_stems_cache/`); Test C = `compare_audio()` (chroma +
  onset-envelope likeness) for songs with no answer key — Trell's idea, not yet exercised.
  Harness auto-compensates constant bounce latency (~120ms+) and detects global pitch
  transposition (sampler-trigger vs sounding pitch).
- **Findings**: clean-stem drums 0.80–1.00 (drum failure = separation recall 0.52 + weak
  classifier, NOT onset detection); keys over-segmentation (split_rate 3.07) is a
  transcription problem (separation blameless); horn destroyed by every separator
  (0.72 clean → ~0.02 mix); 808 sampler MIDI isn't pitch-comparable (non-constant trigger
  mapping) — evaluate onsets + use detected shift to fold into the C3 frame.
- **`scripts/tune_and_bakeoff.py`** — knob grid-search + separator bake-off, all
  harness-scored (`data/tuning_round_01.json`):
  - **Adopted defaults**: onset 0.8, frame 0.45, min_note_len 60ms, drum_onset_delta 0.02
    → keys 0.34→0.46, horn 0.72→**0.86**, drum recall 0.52→0.57.
  - Keys-only would prefer min_note_len 200 (0.53) but that ZEROES the horn — per-stem
    overrides are a future refinement.
  - **Separator verdict: keep `htdemucs`** — htdemucs_6s scored worse (guitar stem absorbs
    everything), htdemucs_ft identical at 4× runtime.
- **Open request when session ended**: quiet the notebook's run cell (too much output),
  which was interrupted by this handoff request.
