# vi.ve — Assistant Music Producer

**Dataset:** `midi_university` — a database of hand-played MIDI files I created.

---

## Problem Statement

My goal for this project is to create an **assistant music producer**, fueled by my
`midi_university` database, that helps me catch my vibe while producing music faster.

The core idea: **"pocket" is measurable.** The way I think about it is similar to NLP and
sentiment analysis — just for music. In sentiment analysis you turn raw text into tokens,
extract features, and score a document's feeling. Here we turn raw MIDI into notes and rests,
extract rhythm/relationship features, and score a pattern's *pocket*.

| NLP / Sentiment Analysis | vi.ve |
| --- | --- |
| Document | Song (MIDI pack) |
| Sentence | Instrument pattern (bassline, kick, hats…) |
| Token | Note event (pitch, position, duration, velocity) |
| Stop words / whitespace | **Rest / space** (just as meaningful as notes) |
| Sentiment score | Pocket / vibe metrics |
| Language model | Weighted style maps that generate new MIDI |

## Impact

This model will assist me with:

- Analyzing the **"pocket"** of music
- Creating MIDI based on my specifications using **weighted variables**
- Adding FX / ear candy to finished tracks

## Stakeholder

Me

## Systems Used

Python, Jupyter Lab, NumPy, mido, Supervised Learning: Classification, Matplotlib,
Yellowbrick, Seaborn, Gradient Descent, PostgreSQL

---

## The Dataset: `midi_university`

Location: `/Users/trell/Music/Ableton/User Library/midi_university/`

I broke 3 songs I like down piece by piece and replayed the main parts **by hand**.

> **Provenance note (2026-07-12):** these first 3 packs were created mostly by drawing and
> by using the laptop keyboard as a MIDI piano (real MIDI keyboard cable is broken). So
> **velocity is not scoreable** for most files — parser analysis confirmed 15 of 19 files
> sit at one constant velocity. Exceptions with real velocity data:
> `morning - chord progression` (41–95) and `morning - hihat` (23–127).
> Timing: kicks/snares/claps/basslines are quantized; hats and melodies carry real deviation.

**Naming conventions:**

- Pack folders: `song title` → `key` → `bpm` (e.g., `morning key Em bpm 71.66`)
- Files: `song title - part` (e.g., `morning - bassline`, `morning - kick`)
- Parts with more than one unique pattern get an extra identifier for the song section
  (e.g., `out there - chorus bassline` vs `out there - verse bassline`)
- Each song features **(2) 4-bar sections**. If a part has no section identifier,
  the pattern is used in both 4-bar sections.

**Current packs (19 files):**

| Song | Key | BPM | Parts |
| --- | --- | --- | --- |
| morning | Em | 71.66 | chord progression, bassline, kick, snare, clap, hihat |
| out there | Ebm | 80 | verse keys, verse bassline, chorus bassline, kick, snare, clap, hihat |
| sicko mode | Ebm | 77.67 | main melody, brkdwn melody, bassline, kick, snare, hihat |

---

## Analysis Framework

### 1. Intra-pack analysis — how the parts of one song complement each other

Questions to explore (each becomes a true/false identifier or a measurable factor):

- Does the kick follow the bassline?
- Does the kick sometimes play notes *leading into* a bassline hit?
- Does the kick hit every time a note from the bassline plays?
- How does the bassline follow/complement the chord progression or melody?
- **How much space is being left between notes?**
- Are sections of the hi-hat pattern doing rolls right before another instrument does something?
- What parts of each pattern **don't change** across the (2) 4-bar sections? What parts **do**?

> Space is just as important to the pocket as what's being played — space in a track
> lets the artist's brain decide how to rap or sing on it. We record the empty space
> mathematically, not just the notes.

### 2. Cross-song analysis — trends that establish style

- Mathematically record the trends instruments follow **across** songs
  (e.g., "a hi-hat roll always plays right before the 3rd beat, counting 1-e-and-ah…")
- Record how closely related the keys of the songs are

### 3. Metrics / KPIs

Everything measurable gets standardized into factors used to calculate metrics.
**Scoring rule (decided 2026-07-12):** metrics are scored against a **target zone** learned
from the packs (inverted-U, per Witek), not "higher/lower is better."

| Metric | Definition |
| --- | --- |
| **hat-business** | How simplistic or busy the hats are — unique pitches, roll density, velocity spread |
| **KTB family** (upgraded from simple ratio) | kick↔bass **hit ratio** + **co-hit rate** (how often they land together) + **lead/lag direction** (who's early, in ticks/ms) + **lag consistency** |
| **space-ratio** | % of the pattern with nothing sounding — space is recorded as a first-class feature |
| **syncopation index** | Published formula (Longuet-Higgins & Lee, as used by Witek) per pattern, scored against a style target zone |
| **groove layer** | Per-note timing deviation (ticks + ms) and velocity vs. the quantized grid — **weighted per style**: low weight for trap/quantized styles, high for neo-soul/melodic parts |
| **section stability** | What stays constant vs. changes between the (2) 4-bar sections |

### 4. Weighted style maps → generation

Everything recorded, measured, and observed forms a **directional map** for creating MIDI:

- Each map weights the variables/factors extracted from each pattern and song
- The generated MIDI leans toward whichever variables are weighted heavier
- **Weights must sum to 1** — e.g., the kick pattern from "morning" at `0.3` + the style
  of "sicko mode" at `0.4` + …

### 4b. Default variables for missing channels

When a file lacks usable information in a channel (flat velocity, fully quantized timing),
the final style map must not learn from garbage — it falls back to **style defaults**:

- Every feature channel gets a **reliability flag** computed from the data
  (e.g., `velocity_reliable = False` when a file is one constant velocity)
- Unreliable channels are excluded from learned style weights
- Generation substitutes defaults from `config/style_defaults.json`
  (starter values pulled from confirmed production principles — e.g., hats velocity 30–118,
  ghost kicks 50–70, microtiming deviation capped ~25 ms per the Senn findings)
- Defaults are per instrument role, editable as taste evolves

### 5. Storage — PostgreSQL

Analysis results are stored in Postgres (local) so scripts can access old analysis.

**Long format** table design:

| Column | Contents |
| --- | --- |
| `song` | which song the observation came from |
| `style` | style label |
| `metric` | text label identifying which metric/KPI this row references |
| `value` | the observed value |

---

## Research Foundations (reviewed 2026-07-12)

Studies found and reviewed against project goals — decisions recorded:

1. **[GrooVAE / Learning to Groove](https://magenta.withgoogle.com/groovae)** (Gillick et al., ICML 2019) —
   a performance = **score** (quantized pattern) + **groove** (per-note velocity + microtiming
   deviation). Built on hand-played drum data, same philosophy as midi_university.
   → **Decision: AGREE.** vi.ve stores every note as grid position + deviation + velocity.
2. **[Witek et al. 2014](https://pmc.ncbi.nlm.nih.gov/articles/PMC3989225/)** — inverted-U between
   syncopation and pleasure/desire to move; medium syncopation grooves hardest.
   → **Decision: AGREE.** Metrics get target zones, not directions.
3. **[Senn et al. 2016](https://pmc.ncbi.nlm.nih.gov/articles/PMC5050221/)** — quantized versions
   rated as groovy as human-timed; exaggerated deviations (~25ms+) kill groove.
   → **Decision: PARTIALLY.** True for trap (quantized hats groove fine); hand-played feel
   matters in neo-soul/melodic parts. Microtiming weight is **per-style**.
4. **[Danielsen beat-bin theory](https://academic.oup.com/mts/article/45/2/181/7234305)** (developed
   on D'Angelo) — the beat has *width*; between-instrument asynchrony (bass dragging the kick)
   IS the pocket. → **Decision: UPGRADE KTB** to the alignment family above.
5. **[REMI / MidiTok tokenization](https://github.com/Natooz/MidiTok)** — state-of-the-art MIDI
   generation treats music literally as language (notes → tokens → sequence models), validating
   the NLP framing. → n-gram analysis of rhythm phrases is a cheap early win for cross-song trends.

---

## Key Milestones

### Failures:

- 2026-07-13 — **Trial 07: all 8 basslines failed.** Post-mortem found the math: every
  failed bassline contained bars from "out there"'s verse bassline (the +8/octave/octave/+5
  counter-melody structure). P(pattern in a 4-bar collage) = 1-(1-w)^4 ≈ 87% at w=0.4, the
  score never penalized the source, the v7 octave-fold laundered the shape past its own
  detector, and fix-check rerolls of flagged (out-heavy) recipes pushed out-there bass-bar
  share 25% → 37.5% → 47% across trials 5–7. Fix (trial 08): out there removed from the
  kick+bass anchor pool; retired structure is now a score penalty; no more flagged-recipe
  rerolls.

- 2026-07-13 — **Trial 01 (bar-collage generation): 0/24 keep rate.** Melodies sound like
  channel surfing. Root cause isolated in `notebooks/trial_01_review.ipynb`: the melody
  pool mixes three incompatible sources (dense chord progression / plucky arp / sparse
  lead) — between-song spread ~2× any other role in density, space, and register.
  Basslines and drums were NOT the failure. Fix for trial 2: melody must be *generated*
  from the style grammar, not collaged; bass/drums keep the collage.

### Successes:

- 2026-07-13 — **Trial 05: 24/24 keep, 18/24 cream. Three full-cream packs (v01, v03, v04)
  auto-registered in `styles`.** The "cursed" v04 weight recipe was exonerated — same
  weights with a new seed produced a full-cream pack, so per-run dice variance is real
  and recipes are not dead zones. New bottleneck: basslines (4/8 cream; wrong-lane and
  bad-landing flags concentrate on high-register "out there" bass DNA and loop resolution).
- 2026-07-13 — **Trial 02 (grammar melody + collage bass/drums): 11/24 kept (46%) vs 0/24.**
  Drums 5/8, basslines 4/8, melodies 2/8 — and kept melodies only "in the direction of
  usable." Key patterns: melody keeps happened ONLY on pure single-song combos (blended
  vocab still mixes dialects); v03 pure-sicko was the first fully-kept pack (3/3);
  combos v04–v06 were rejected wholesale, suggesting a cross-role coherence problem in
  blends beyond just melody. Verdicts accumulate in the `trial_results` Postgres table.

- 2026-07-12 — Repo created and pushed to GitHub; project structure established
- 2026-07-12 — Research review completed; core representation (score/feel split), target-zone
  scoring, per-style microtiming weights, and KTB upgrade decided
- 2026-07-13 — **First named style: "Riding Trap"** — a love letter to those who love
  thumping basslines and riding in the car; basslines live in the sub lane (808s / low
  register). Exemplar v04, registered in the `styles` Postgres table with a full recipe
  (weights, key, bpm, per-bar source map) so it can be recreated without re-explaining.
  Drums validated by ear as complementing the 808.

---

## Tasks

1. ✅ Turn vi.ve into a git repository, push to GitHub
2. ✅ Reorganize readme from mindDump into actionable structure
3. ✅ Research: find studies related to pocket/groove quantification, relate them to
   these goals, agree/disagree review, refine metrics
4. ⏳ `parse_packs.py` — load all 20 MIDIs into a normalized structure
   (song, part, note events, bar-normalized positions, score/feel split)
5. ✅ Intra-pack analysis script (kick↔bass relationship, space measurement, section A/B comparison)
   — `scripts/intra_pack_analysis.py` → `data/intra_pack_metrics.csv` (179 long-format rows)
6. ✅ Cross-song trends — `scripts/cross_song_trends.py` → `data/style_profile.json`
   (position consensus, shared rhythm n-grams, metric target zones, key relatedness)
7. ✅ Postgres schema + writer — `scripts/load_postgres.py` → local `vive` database
   (Postgres.app, port 5431), tables `metrics` (long format + run_date history) and
   `style_profiles` (jsonb profile per run)
8. ✅ Weighted style maps + MIDI generation v1 — `scripts/generate_vibes.py` (bar collage),
   24 files → Trial 01, plus `scripts/register_style.py` + `styles` table (style registry)
9. ✅ Trial 01 review notebook — `notebooks/trial_01_review.ipynb` (scorecard, Postgres
   storage tour, root-cause analysis of the melody failure, style registry demo)
10. ✅ Trial 02 generator built — `scripts/generate_vibes_v2.py` (motif AA'BA melody engine,
    one register, target-zone density/space); bass + drums keep the collage engine

## Recommendations

First findings from cross-song analysis (2026-07-12):

- **The kick grammar is the tresillo.** The dotted-8th chain (IOI `[3,3]` in 16ths) is the
  #1 shared kick phrase in ALL 3 songs (36 occurrences). Universal kick positions: the 1,
  2-and, 3-and, 4-e — the 1 plus syncopated offbeats. Generation should build kicks from
  tresillo cells, not from a straight grid.
- **Bass shares the kick's DNA**: universal positions 1, 3-and, 4-e with `[3,1]`/`[3,3]`
  phrases — consistent with the high kick↔bass co-hit rates (0.64–1.0).
- **Hats are position-agnostic**: every 16th position is used in all 3 songs. Hat style
  lives in rolls + velocity, not placement — so hat generation cares about the groove
  layer, kick/bass generation cares about the score layer.
- **Snare placement is song-specific** (zero universal positions) — a free variable per
  song, while claps lean on 2 and 4.
- **Key spread**: out there & sicko mode are the same key (Ebm); morning (Em) is
  1 semitone but 5 circle-of-fifths steps away — semitone-close ≠ harmonically close.
