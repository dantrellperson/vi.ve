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
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

import librosa
import mido
import numpy as np

SONGS_DIR = Path("/Users/trell/trell_music_life/songs_to_load")
AUTO_LIB = Path.home() / "Music" / "Ableton" / "User Library" / "midi_university_auto"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LOG_CSV = DATA_DIR / "songs_loaded.csv"

AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".flac", ".aiff", ".aif", ".ogg"}
TPQ = 480

CONFIG = {
    "onset_threshold": 0.5,    # Basic Pitch: higher = fewer, more confident note starts
    "frame_threshold": 0.3,    # Basic Pitch: pitch confidence per frame
    "min_note_len_ms": 60,     # drop blips shorter than this
    "min_amplitude_vel": 30,   # velocity floor for quietest kept note
    "drum_onset_delta": 0.06,  # drum hit sensitivity (lower = more hits)
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
    from basic_pitch.inference import predict
    with contextlib.redirect_stdout(io.StringIO()):   # silence CoreML debug spam
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


def transcribe_drums(wav_path):
    """Onset detection + frequency-band classification -> kick/snare/hihat hits."""
    y, sr = librosa.load(wav_path, sr=None, mono=True)
    onsets = librosa.onset.onset_detect(y=y, sr=sr, units="time", backtrack=True,
                                        delta=CONFIG["drum_onset_delta"])
    hits = {"kick": [], "snare": [], "hihat": []}
    n_fft = 2048
    for t in onsets:
        i = int(t * sr)
        frame = y[i:i + n_fft]
        if len(frame) < n_fft:
            frame = np.pad(frame, (0, n_fft - len(frame)))
        spec = np.abs(np.fft.rfft(frame * np.hanning(n_fft)))
        freqs = np.fft.rfftfreq(n_fft, 1 / sr)
        total = spec.sum() + 1e-9
        low = spec[freqs < 150].sum() / total
        high = spec[freqs > 4000].sum() / total
        loud = float(np.sqrt((frame ** 2).mean()))
        if low > 0.35:
            hits["kick"].append((t, loud))
        elif high > 0.30:
            hits["hihat"].append((t, loud))
        else:
            hits["snare"].append((t, loud))
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
    bpm = detect_bpm(y, sr)
    key = detect_key(y, sr)
    print(f"  detected key {key}, bpm {bpm}")

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
