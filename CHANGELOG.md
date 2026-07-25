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

## 2026-07-24 (later) — Trell's grades, the blind metric, and the BPM discovery

- **Trell graded the tuned re-run** (recorded in `data/songs_loaded.csv`, pre-tuning
  round backfilled so the delta is visible): melody New Topic **2.8 -> 4.4**, Big 5 3.7,
  Aye Tay 3.2; bassline **~2.8 -> 3.8 on all three** (a flat score across three different
  songs = a systematic ceiling, not a song problem — nothing folds extracted bass into
  the C3/808 frame yet); **drums 0/5 on all three, unchanged**.
- **Diagnosed the drum failure by measurement**, not guesswork:
  - **0 co-hits** across all three songs and all three pairs. The classifier was
    `if low / elif high / else`, so one onset could only ever become ONE drum. Kick+hat
    and snare+hat land together constantly in trap; those hits were deleted, not
    misclassified.
  - **Class collapse**: 0.09 kicks/bar vs 16.6 hats/bar on Aye Tay (4 kicks in 43 bars).
    The kick test `low(<150Hz) > 0.35` rarely fired because Demucs routes 808/sub energy
    to the BASS stem — the kick's low end is in a different file.
  - **Double-triggers**: 74% of Aye Tay's hat intervals were shorter than a 32nd.
- **THE MEASUREMENT BLIND SPOT**: the harness reported drum recall 0.52 -> 0.57
  ("improving") while Trell graded the same packs 0/5. Both were right — the union-onset
  metric only asked *did some drum fire here*, never *was it the right drum*. Tuning
  round 1 optimised against a metric that could not see the actual failure. Same lesson
  as the trial-7 post-mortem, new location.
- **`eval_drums_per_class()`** in `transcription_eval.py` — per-lane precision/recall/F1
  + confusion matrix, one shared alignment offset so no lane can slide to flatter itself.
  Test A now also runs it per solo bounce, where the true lane is known, isolating
  classification from detection. The legacy union metric is kept for continuity.
  It immediately caught a bug in the new classifier that the union metric was blind to:
  a **solo kick bounce scoring 3003 hi-hats** (normalising a near-silent band turns its
  noise floor into hits) -> fixed with an absolute band-energy floor.
- **`transcribe_drums()` rewritten**: per-band onset-strength envelopes with an
  INDEPENDENT peak-picker per role (simultaneity is now representable), share-based
  gating (every drum is broadband at its transient, so absolute energy fires every lane;
  what separates roles is which band is *disproportionately* excited), and per-role
  minimum spacing. Split into `drum_envelopes()` (expensive) + `pick_drum_hits()` (cheap)
  so tuning sweeps thresholds without recomputing audio.
- **`scripts/tune_drums.py`** — grid-search scored by per-class macro F1
  (`data/drum_tuning_round_02.json`). **Macro F1 0.65 -> 0.77**; kick **0.54 -> 0.88**
  (predictions 330 -> 129 against 122 real kicks; "predicted kick, actually snare" -> 0);
  hihat 0.84; **snare still the weak lane at 0.58** (predicted snares land kick 96 /
  snare 92 / hihat 83 — near a coin flip). Thresholds chosen from the middle of a broad
  plateau, not its edge. Extracted packs went from 0 co-hits to 14-40% kick+hat and
  79-94% snare+hat; Aye Tay's kick lane went 4 hits -> 199.
- **Hypothesis TESTED AND REJECTED** (recorded so nobody retries it): giving the snare
  the 1500-6000 Hz band, where a clap's crack lives, dropped snare F1 0.58 -> 0.47.
  That band carries more hi-hat bleed than clap. Snare stays body-only.
- **THE BIGGER FINDING — BPM precision, not transcription, was the deliverable problem.**
  Extracted packs looked 15-21% on-grid, which reads like garbage timing. It was not:
  `librosa.beat_track` is only accurate to ~1%, and over a 40-70 bar pack that error
  accumulates until the MIDI has slid a full 16th off the grid. The pack starts in time
  and progressively drifts out. Correcting the tempo by a fraction of a percent:

  | song | logged | true | error | on-grid naive -> true |
  |---|---|---|---|---|
  | Aye Tay | 76.00 | **77.00** | +1.32% | 18% -> **78%** |
  | BIG 5 | 64.60 | 64.51 | -0.14% | 15% -> **86%** |
  | costly. | 80.75 | 80.99 | +0.30% | 21% -> **68%** |
  | New Topic | 80.75 | 81.01 | +0.32% | 19% -> **68%** |
  | Drake | 95.70 | 95.51 | -0.20% | 16% -> **61%** |

  The hits were always in the right places. Aye Tay's fit holds across both halves
  separately, so it is a detection error, not a tempo change — and it is also the song
  Trell graded lowest on melody (3.2), which the drift explains.
- **`refine_bpm()`** — fits onsets to a 16th grid to sharpen the coarse estimate.
  Cross-validated: run on the raw audio it independently recovers all five tempos that
  the grid-fit on the *extracted MIDI* had found. This sits upstream of drums, melody
  and bass, so it improves every part of every pack at once.
- **All five songs re-extracted with refined tempo.** Verification: the grid-fit now
  wants a tempo correction of **x1.000 on every song** — the estimate has nothing left
  to give. Whole-pack alignment 61–84% on-grid.
- **New finding from that verification — the kick lane is timing-jittery.** Snare 81–91%
  and hi-hat 81–94% on-grid, but kick only 26–36%. A constant shift recovers 1–2 points,
  so it is JITTER, not lag: onsets detected inside a 20–150 Hz band are inherently
  smeared, because the waveform period there is 7–50 ms. The kick therefore passes the
  harness's ±50 ms note tolerance (F1 0.88) while failing a ±15 ms grid test — the two
  metrics disagree and both are right. **Named fix: detect the transient broadband
  (sharp) and use the low band only to attribute it, i.e. snap kick times to the nearest
  full-spectrum onset.** Not yet implemented.
- Two new songs appeared in `songs_to_load` (COSTLY., Drake "What Would Pluto Do") and
  were picked up by the forced re-run; both are ungraded.
