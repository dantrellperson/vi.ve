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

I broke 3 songs I like down piece by piece and replayed the main parts **by hand**
(so the human timing/velocity is preserved — this is the ground truth for pocket).

**Naming conventions:**

- Pack folders: `song title` → `key` → `bpm` (e.g., `morning key Em bpm 71.66`)
- Files: `song title - part` (e.g., `morning - bassline`, `morning - kick`)
- Parts with more than one unique pattern get an extra identifier for the song section
  (e.g., `out there - chorus bassline` vs `out there - verse bassline`)
- Each song features **(2) 4-bar sections**. If a part has no section identifier,
  the pattern is used in both 4-bar sections.

**Current packs (20 files):**

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

Everything measurable gets standardized into factors used to calculate metrics. Candidates so far:

| Metric | Definition |
| --- | --- |
| **hat-business** | How simplistic or busy the hats are — multiple pitches or one, rolls present, velocity spread |
| **KTB (kick-to-bass ratio)** | How many times the kick hits relative to the bassline being played |
| *(more to come from research + analysis)* | |

### 4. Weighted style maps → generation

Everything recorded, measured, and observed forms a **directional map** for creating MIDI:

- Each map weights the variables/factors extracted from each pattern and song
- The generated MIDI leans toward whichever variables are weighted heavier
- **Weights must sum to 1** — e.g., the kick pattern from "morning" at `0.3` + the style
  of "sicko mode" at `0.4` + …

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

## Key Milestones

### Failures:

*(logged as they happen)*

### Successes:

- 2026-07-12 — Repo created and pushed to GitHub; project structure established

---

## Tasks

1. ✅ Turn vi.ve into a git repository, push to GitHub
2. ✅ Reorganize readme from mindDump into actionable structure
3. ⏳ Research: find studies related to pocket/groove quantification, relate them to
   these goals, agree/disagree review, refine metrics
4. ⏳ `parse_packs.py` — load all 20 MIDIs into a normalized structure
   (song, part, note events, bar-normalized positions)
5. ⏳ Intra-pack analysis script (kick↔bass relationship, space measurement, section A/B comparison)
6. ⏳ Postgres schema + writer
7. ⏳ Weighted style maps + MIDI generation

## Recommendations

*(filled in as analysis produces findings)*
