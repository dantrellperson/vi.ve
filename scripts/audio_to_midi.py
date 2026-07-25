#!/usr/bin/env python3
"""
audio_to_midi.py — turn full songs into midi_university-style MIDI packs.

The pipeline (plain english):
  1. STEM SEPARATION — Demucs (a neural net) splits the song into 4 stems:
     vocals / drums / bass / other, so each instrument is transcribed alone.
  2. KEY + BPM DETECTION — librosa estimates tempo from onsets and key from
     the average chroma (Krumhansl-Schmuckler profile correlation).
  3. PITCH -> NOTES — Spotify's Basic Pitch model reads each melodic stem's
     spectrogram and outputs note events (start, end, pitch, loudness).
  4. DRUMS -> HITS — onset detection on the drum stem; each hit is classified
     kick / snare / hihat by where its energy sits in the frequency spectrum.
  5. MIDI PACK — everything is written as a midi_university-convention folder:
     "{title} key {Key} bpm {bpm}" with "{title} - part.mid" files (TPQ 480,
     tempo meta included), in the SEPARATE auto library so machine-extracted
     packs never mix with the hand-played ground truth.
  6. SONG LOG — every processed song is appended to data/songs_loaded.csv
     (title, key, bpm, source, note counts, and empty quality columns for
     Trell's grading). The log later graduates to a Postgres table.

Tuning knobs live in CONFIG — adjust after quality testing.
"""

import csv
import logging
import subprocess
import sys
import tempfile
import warnings
from datetime import date
from pathlib import Path

# keep notebook output to the necessary success messages only
warnings.filterwarnings("ignore")
logging.getLogger().setLevel(logging.ERROR)

import librosa
import mido
import numpy as np

SONGS_DIR = Path("/Users/trell/trell_music_life/songs_to_load")
AUTO_LIB = Path.home() / "Music" / "Ableton" / "User Library" / "midi_university_auto"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LOG_CSV = DATA_DIR / "songs_loaded.csv"

AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".flac", ".aiff", ".aif", ".ogg"}
TPQ = 480

# Defaults tuned 2026-07-24 by harness grid-search vs HML ground truth
# (data/tuning_round_01.json): keys 0.34->0.46, horn 0.72->0.86, drum recall 0.52->0.57.
# Separator bake-off kept htdemucs: 6s scored worse, ft scored equal at 4x the runtime.
CONFIG = {
    "onset_threshold": 0.8,    # Basic Pitch: higher = fewer, more confident note starts
    "frame_threshold": 0.45,   # Basic Pitch: pitch confidence per frame
    "min_note_len_ms": 60,     # drop blips shorter than this (keys-only would prefer 200)
    "min_amplitude_vel": 30,   # velocity floor for quietest kept note
    "drum_onset_delta": 0.02,  # legacy whole-stem onset sensitivity (harness union metric)
    "drum_delta_k": 0.35,      # per-band peak threshold = median + k*(p95 - median)
    "drum_band_floor": 0.04,   # band must carry this share of peak onset strength
    # Band's share of onset energy required to claim a hit. Grid-searched against the
    # harness's per-class macro F1 (data/drum_tuning_round_02.json): 0.65 -> 0.77.
    # Chosen from the middle of a broad plateau, not its edge, so they travel.
    "drum_share_kick": 0.40,
    "drum_share_snare": 0.20,
    "drum_share_hihat": 0.05,
    "drum_gap_kick_ms": 80,    # minimum spacing per role — kills double-triggers
    "drum_gap_snare_ms": 80,
    "drum_gap_hihat_ms": 40,   # low enough to keep 32nd-note hat rolls
    "demucs_model": "htdemucs",
}

MELODIC_STEMS = {"bass": "bassline", "other": "melody", "vocals": "vocal melody"}

KRUMHANSL_MAJOR = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
KRUMHANSL_MINOR = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
NOTE_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]


# ------------------------------------------------------------------ analysis

def detect_bpm(y, sr):
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(np.atleast_1d(tempo)[0])
    while bpm > 100:           # trap lives in halved-tempo land; fold 140 -> 70
        bpm /= 2
    return round(bpm * 2, 2) if bpm < 50 else round(bpm, 2)


def refine_bpm(y, sr, coarse_bpm):
    """Sharpen librosa's tempo estimate by fitting onsets to a 16th-note grid.

    beat_track is only accurate to about 1%, which is invisible in a 4-bar loop and
    fatal in a 40-bar pack: the error accumulates until the MIDI has slid a full 16th
    away from the grid, so the pack starts in time and progressively drifts out.
    Measured on the five loaded songs, correcting an error this small moved on-grid
    alignment from 15-21% to 61-86% — Aye Tay was logged at 76.00 when it is 77.00.

    Onsets are already the pipeline's most reliable signal, so pick the tempo that
    puts the most of them on a 16th grid. Returns the coarse estimate unchanged when
    there is too little evidence to improve on it.
    """
    onsets = librosa.onset.onset_detect(y=y, sr=sr, units="time", backtrack=True)
    if len(onsets) < 32:
        return coarse_bpm
    phases = np.arange(0, 0.25, 0.01)
    best_bpm, best_score = coarse_bpm, -1.0
    for bpm in np.arange(coarse_bpm * 0.97, coarse_bpm * 1.03, coarse_bpm * 0.0002):
        beats = onsets * bpm / 60.0
        # distance to the nearest 16th, for every candidate phase at once
        frac = ((beats[None, :] - phases[:, None]) * 4) % 1.0
        score = np.minimum(frac, 1 - frac).__lt__(0.08).mean(axis=1).max()
        if score > best_score:
            best_bpm, best_score = float(bpm), float(score)
    return round(best_bpm, 2)


def detect_key(y, sr):
    chroma = librosa.feature.chroma_cqt(y=librosa.effects.harmonic(y), sr=sr).mean(axis=1)
    best, best_r = "C", -2
    for shift in range(12):
        rolled = np.roll(chroma, -shift)
        for profile, suffix in ((KRUMHANSL_MAJOR, ""), (KRUMHANSL_MINOR, "m")):
            r = np.corrcoef(rolled, profile)[0, 1]
            if r > best_r:
                best_r, best = r, NOTE_NAMES[shift] + suffix
    return best


# ------------------------------------------------------------------ stems

def separate_stems(audio_path, workdir):
    """Demucs 4-stem separation. Returns {stem_name: wav_path}."""
    cmd = [sys.executable, "-m", "demucs", "-n", CONFIG["demucs_model"],
           "-o", str(workdir), str(audio_path)]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    stem_dir = workdir / CONFIG["demucs_model"] / audio_path.stem
    return {p.stem: p for p in stem_dir.glob("*.wav")}


# ------------------------------------------------------------------ transcription

def transcribe_stem(wav_path):
    """Basic Pitch: spectrogram -> note events (start_s, end_s, midi_pitch, velocity)."""
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        from basic_pitch.inference import predict    # import inside: its warnings stay quiet too
        _, _, note_events = predict(
            str(wav_path),
            onset_threshold=CONFIG["onset_threshold"],
            frame_threshold=CONFIG["frame_threshold"],
            minimum_note_length=CONFIG["min_note_len_ms"],
        )
    notes = []
    for ev in note_events:
        start, end, pitch, amplitude = ev[0], ev[1], int(ev[2]), float(ev[3])
        vel = int(CONFIG["min_amplitude_vel"] + amplitude * (115 - CONFIG["min_amplitude_vel"]))
        notes.append((float(start), float(end), pitch, min(vel, 115)))
    return sorted(notes)


# Band edges (Hz) per drum role, contiguous so onset_strength_multi slices the mel
# channels in one pass. The 1500-6000 channel is deliberately unclaimed: giving it to
# the snare (a clap's crack lives there) was TESTED and made things worse — snare F1
# 0.58 -> 0.47, because the band carries more hi-hat bleed than clap. Body only.
DRUM_BAND_EDGES_HZ = [20, 150, 1500, 6000]
DRUM_BAND_CHANNEL = {"kick": (0,), "snare": (1,), "hihat": (3,)}


def transcribe_drums(wav_path):
    """Per-band onset envelopes -> an INDEPENDENT detector per drum.

    Replaces the original single-frame `if low / elif high / else` classifier, which
    had three measured failures (see notebooks + CHANGELOG 2026-07-24):
      1. One onset could only ever become ONE drum -> 0 co-hits across all three
         test songs. Kick+hat and snare+hat land together constantly in trap, so
         those hits were not misclassified, they were deleted.
      2. The kick test `low(<150Hz) > 0.35` almost never fired, because Demucs
         routes 808/sub energy to the BASS stem — 4 kicks in 43 bars on one song.
         Everything fell through to the hat lane (16.6 hats/bar).
      3. No minimum spacing -> one transient could fire twice (74% of one song's
         hat intervals were shorter than a 32nd note).

    Each band now peak-picks its own onset-strength envelope, so simultaneous hits
    are representable; thresholds are drawn from the song's own envelope statistics
    rather than fixed spectral fractions; `wait` enforces per-role minimum spacing.
    """
    return pick_drum_hits(drum_envelopes(wav_path))


def drum_envelopes(wav_path):
    """The expensive half of drum transcription: per-band + full-spectrum onset
    strength. Split out so the tuner can compute it once and sweep thresholds."""
    y, sr = librosa.load(wav_path, sr=None, mono=True)
    hop = 512
    n_mels = 128
    mel_f = librosa.mel_frequencies(n_mels=n_mels, fmin=0, fmax=sr / 2)
    edges = [int(np.argmin(np.abs(mel_f - hz))) for hz in DRUM_BAND_EDGES_HZ] + [n_mels]
    edges = sorted(set(edges))
    envs = librosa.onset.onset_strength_multi(y=y, sr=sr, hop_length=hop,
                                              channels=edges)
    env_full = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    return {"envs": envs, "env_full": env_full, "sr": sr, "hop": hop}


def pick_drum_hits(env_pack):
    """The cheap half: CONFIG thresholds -> {role: [(time_s, loudness)]}."""
    envs, env_full = env_pack["envs"], env_pack["env_full"]
    sr, hop = env_pack["sr"], env_pack["hop"]
    # Absolute reference: a band-local peak is only a real hit if the band actually
    # carries energy. Without this gate, normalising a near-silent band turns its
    # noise floor into "hits" — a solo kick bounce scored 3003 hi-hats before this.
    floor = CONFIG["drum_band_floor"] * float(env_full.max())
    # Every drum is broadband at its transient — a kick's body reaches into the snare
    # band, a snare excites all four. Absolute energy alone therefore fires every lane
    # on every hit (measured: kick precision 0.37). What separates the roles is which
    # band is disproportionately excited, so gate on each band's SHARE of the onset
    # energy at that instant. Simultaneity survives: a real kick+hat co-hit lifts the
    # low and high shares together while the mid share stays put.
    share_of = envs / (envs.sum(axis=0, keepdims=True) + 1e-9)

    frame_ms = hop / sr * 1000
    hits = {}
    for role, chans in DRUM_BAND_CHANNEL.items():
        chans = [c for c in chans if c < len(envs)]
        if not chans:
            hits[role] = []
            continue
        raw = envs[list(chans)].sum(axis=0)
        share = share_of[list(chans)].sum(axis=0)
        env = raw / (raw.max() + 1e-9)
        med = float(np.median(env))
        # threshold relative to this song's own dynamics, not an absolute fraction
        delta = med + CONFIG["drum_delta_k"] * (float(np.percentile(env, 95)) - med)
        wait = max(1, int(round(CONFIG[f"drum_gap_{role}_ms"] / frame_ms)))
        peaks = librosa.util.peak_pick(env, pre_max=3, post_max=3, pre_avg=5,
                                       post_avg=5, delta=delta, wait=wait)
        peaks = [p for p in peaks
                 if raw[p] >= floor and share[p] >= CONFIG[f"drum_share_{role}"]]
        times = librosa.frames_to_time(np.array(peaks), sr=sr, hop_length=hop)
        hits[role] = [(float(t), float(env[p])) for t, p in zip(times, peaks)]
    return hits


# ------------------------------------------------------------------ midi writing

def write_note_midi(notes, bpm, out_path, name):
    """notes: (start_s, end_s, pitch, vel). Seconds -> ticks at the detected tempo."""
    spb = 60 / bpm
    mid = mido.MidiFile(ticks_per_beat=TPQ)
    trk = mido.MidiTrack()
    trk.append(mido.MetaMessage("track_name", name=name, time=0))
    trk.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))
    events = []
    for (s, e, p, v) in notes:
        events.append((int(round(s / spb * TPQ)), 1, "note_on", p, v))
        events.append((int(round(max(e, s + 0.03) / spb * TPQ)), 0, "note_off", p, 0))
    events.sort(key=lambda ev: (ev[0], ev[1]))
    prev = 0
    for (tick, _, kind, p, v) in events:
        trk.append(mido.Message(kind, note=p, velocity=v, time=tick - prev))
        prev = tick
    trk.append(mido.MetaMessage("end_of_track", time=0))
    mid.tracks.append(trk)
    mid.save(out_path)


def write_drum_midi(hits, bpm, out_path, name, pitch):
    if not hits:
        return 0
    louds = [l for _, l in hits]
    lo, hi = min(louds), max(louds) or 1
    notes = [(t, t + 0.05, pitch,
              int(40 + (l - lo) / (hi - lo + 1e-9) * 80)) for (t, l) in hits]
    write_note_midi(notes, bpm, out_path, name)
    return len(notes)


# ------------------------------------------------------------------ driver

def logged_titles():
    if not LOG_CSV.exists():
        return set()
    with LOG_CSV.open() as f:
        return {r["source_file"] for r in csv.DictReader(f)}


def append_log(row):
    fields = ["date", "title", "key", "bpm", "source_file", "bassline_notes",
              "melody_notes", "vocal_melody_notes", "kick_hits", "snare_hits",
              "hihat_hits", "quality (fill in)", "notes (fill in)"]
    new = not LOG_CSV.exists()
    with LOG_CSV.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new:
            w.writeheader()
        w.writerow(row)


def process_song(audio_path, config=None):
    """Full pipeline for one song. Returns a summary dict (also appended to the log)."""
    if config:
        CONFIG.update(config)
    audio_path = Path(audio_path)
    title = audio_path.stem.lower()
    print(f"▶ {title}")

    y, sr = librosa.load(str(audio_path), mono=True)
    coarse = detect_bpm(y, sr)
    bpm = refine_bpm(y, sr, coarse)
    key = detect_key(y, sr)
    drift = "" if bpm == coarse else f"  (refined from {coarse:g}, {(bpm/coarse-1)*100:+.2f}%)"
    print(f"  detected key {key}, bpm {bpm:g}{drift}")

    with tempfile.TemporaryDirectory() as td:
        print("  separating stems (Demucs — takes a few minutes per song on CPU)…")
        stems = separate_stems(audio_path, Path(td))

        folder = AUTO_LIB / f"{title} key {key} bpm {bpm:g}"
        folder.mkdir(parents=True, exist_ok=True)
        counts = {}

        for stem, part in MELODIC_STEMS.items():
            if stem not in stems:
                counts[part] = 0
                continue
            print(f"  transcribing {stem} → {part}")
            notes = transcribe_stem(stems[stem])
            counts[part] = len(notes)
            if notes:
                write_note_midi(notes, bpm, folder / f"{title} - {part}.mid", part)

        print("  slicing drums → kick / snare / hihat")
        hits = transcribe_drums(stems["drums"]) if "drums" in stems else {}
        for role, pitch in (("kick", 36), ("snare", 38), ("hihat", 42)):
            counts[role] = write_drum_midi(hits.get(role, []), bpm,
                                           folder / f"{title} - {role}.mid", role, pitch)

    append_log({"date": str(date.today()), "title": title, "key": key, "bpm": bpm,
                "source_file": audio_path.name,
                "bassline_notes": counts.get("bassline", 0),
                "melody_notes": counts.get("melody", 0),
                "vocal_melody_notes": counts.get("vocal melody", 0),
                "kick_hits": counts.get("kick", 0), "snare_hits": counts.get("snare", 0),
                "hihat_hits": counts.get("hihat", 0),
                "quality (fill in)": "", "notes (fill in)": ""})
    print(f"  ✔ pack written: {folder.name}")
    return {"title": title, "key": key, "bpm": bpm, **counts, "folder": str(folder)}


def process_all(force=False):
    """Process every audio file in songs_to_load not already in the log."""
    done = set() if force else logged_titles()
    songs = [p for p in sorted(SONGS_DIR.iterdir())
             if p.suffix.lower() in AUDIO_EXTS and p.name not in done]
    if not songs:
        print(f"no new songs found in {SONGS_DIR}")
        return []
    return [process_song(p) for p in songs]


if __name__ == "__main__":
    process_all(force="--force" in sys.argv)
