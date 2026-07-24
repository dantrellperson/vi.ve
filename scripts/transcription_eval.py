#!/usr/bin/env python3
"""
transcription_eval.py — the ground-truth harness for audio->MIDI quality.

Trell exports, from a beat he produced (into songs_to_load/ground_truth/):
  - the MIDI clip per part            = the ANSWER KEY (he wrote these notes)
  - a solo audio bounce per part      = what the transcriber hears, isolated
  - the full mix                      = what the Demucs pipeline starts from

Three tests:
  A. CLEAN-STEM TEST — transcribe each solo bounce directly (no separation)
     and score against the answer key. Isolates pure transcription error.
  B. FULL-PIPELINE TEST — full mix -> Demucs -> transcribe stems, scored the
     same way. The A-vs-B gap = how much quality the separation stage costs.
  C. AUDIO-LIKENESS TEST (compare_audio) — for songs with NO answer key:
     bounce the extracted MIDI through instruments and compare that audio to
     the original song (chroma = harmonic likeness, onset envelope = rhythm
     likeness). Trell's idea; the score is relative, best used to compare
     pipeline versions against each other on the same song.

Scoring: mir_eval note matching — a predicted note matches ground truth if
pitch is exact and onset lands within +/-50ms. Precision = how much of what we
transcribed is real; recall = how much of the real notes we caught; F1 blends
both. Pitch-class-only F1 is also reported: a big gap between it and exact F1
means octave errors. Split-rate counts extra predictions landing inside one
ground-truth note (the flute-trill failure mode).

Alignment: bounces are full-song length while MIDI clips are short loops, so
each comparison grid-searches a bar-aligned offset (clip may enter late) and
evaluates one clip-span window at the best offset.

Usage:
    python3 scripts/transcription_eval.py            # tests A + B on ground_truth/
    python3 scripts/transcription_eval.py --skip-demucs   # test A only (fast)
"""

import json
import re
import sys
import tempfile
from pathlib import Path

import librosa
import mido
import numpy as np
import mir_eval

sys.path.append(str(Path(__file__).resolve().parent))
from audio_to_midi import CONFIG, separate_stems, transcribe_stem

GT_DIR = Path("/Users/trell/trell_music_life/songs_to_load/ground_truth")
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

ONSET_TOL = 0.05          # seconds — mir_eval default window for a "hit"
DRUM_WORDS = {"kick", "snare", "clap", "hat", "hihat", "perc", "rim"}


# ------------------------------------------------------------------ ground truth

def clean(name):
    # strip track numbers/take digits but KEEP "808" — it identifies the bass part
    s = re.sub(r"\(\d+\)|\b(?!808\b)\d+\b", " ", name.lower())
    return " ".join(s.replace("-", " ").split())


def load_gt_midi(path, fallback_bpm):
    """MIDI clip -> (onsets_s, pitches, span_s). Uses the file's tempo if present."""
    mid = mido.MidiFile(path)
    tempo = next((m.tempo for t in mid.tracks for m in t if m.type == "set_tempo"),
                 mido.bpm2tempo(fallback_bpm))
    spt = tempo / 1e6 / mid.ticks_per_beat      # seconds per tick
    onsets, pitches, end = [], [], 0.0
    for trk in mid.tracks:
        tick = 0
        for m in trk:
            tick += m.time
            if m.type == "note_on" and m.velocity > 0:
                onsets.append(tick * spt)
                pitches.append(m.note)
            end = max(end, tick * spt)
    order = np.argsort(onsets)
    return np.array(onsets)[order], np.array(pitches)[order], end


def discover(gt_dir):
    """Pair answer-key MIDIs with their solo bounces; find the full mix."""
    mids = {clean(p.stem): p for p in gt_dir.glob("*.mid")}
    mixes = [p for p in gt_dir.glob("*.mp3")
             if re.fullmatch(r".*\bBPM [\d.]+\s*", p.stem, re.I)]
    if not mixes:
        raise SystemExit("no full mix found (expect a bounce named like 'TITLE BPM 151.mp3')")
    mix = mixes[0]
    bpm = float(re.search(r"bpm ([\d.]+)", mix.stem, re.I).group(1))
    prefix = mix.stem.strip()

    pairs, unpaired = {}, []
    for wav in gt_dir.glob("*.mp3"):
        if wav == mix:
            continue
        tail = clean(wav.stem.replace(prefix, " ").strip())
        best, best_score = None, 0
        for key in mids:
            score = len(set(key.split()) & set(tail.split()))
            if score > best_score:
                best, best_score = key, score
        if best:
            pairs[best] = {"midi": mids[best], "bounce": wav}
        else:
            unpaired.append(wav.name)
    return {"title": prefix, "bpm": bpm, "mix": mix, "pairs": pairs, "unpaired": unpaired}


# ------------------------------------------------------------------ prediction

def predict_melodic(wav_path):
    notes = transcribe_stem(wav_path)
    return (np.array([n[0] for n in notes]), np.array([n[2] for n in notes]))


def predict_onsets(wav_path):
    y, sr = librosa.load(str(wav_path), sr=None, mono=True)
    t = librosa.onset.onset_detect(y=y, sr=sr, units="time", backtrack=True,
                                   delta=CONFIG["drum_onset_delta"])
    return np.array(t)


# ------------------------------------------------------------------ scoring

def _hits_at(gt_on, pred_on, off, span):
    window = pred_on[(pred_on >= off - ONSET_TOL) & (pred_on <= off + span + ONSET_TOL)] - off
    if len(window) == 0:
        return 0
    return sum(1 for g in gt_on if np.any(np.abs(window - g) <= ONSET_TOL))


def best_offset(gt_on, pred_on, bpm, span):
    """Coarse bar-aligned search (the clip may enter late), then a fine +/-250ms
    sweep: bounces carry constant latency (mp3 delay + slow 808 attacks) that is
    an export artifact, not a transcription error — it must not eat the score."""
    bar = 240 / bpm
    coarse, best_hits = 0.0, -1
    for k in range(0, 128):
        off = k * bar / 2
        hits = _hits_at(gt_on, pred_on, off, span)
        if hits > best_hits:
            best_hits, coarse = hits, off
    best = coarse
    for fine in np.arange(-0.25, 0.25, 0.01):
        hits = _hits_at(gt_on, pred_on, coarse + fine, span)
        if hits > best_hits:
            best_hits, best = hits, coarse + fine
    return best


def eval_melodic(gt, pred, bpm):
    gt_on, gt_pitch, span = gt
    pred_on, pred_pitch = pred
    if len(pred_on) == 0 or len(gt_on) == 0:
        return {"precision": 0, "recall": 0, "f1": 0, "n_gt": len(gt_on), "n_pred": 0}
    off = best_offset(gt_on, pred_on, bpm, span)
    sel = (pred_on >= off - ONSET_TOL) & (pred_on <= off + span + ONSET_TOL)
    p_on, p_pitch = np.maximum(pred_on[sel] - off, 0.0), pred_pitch[sel]

    def f(ref_p, est_p):
        if len(p_on) == 0:
            return 0, 0, 0
        gt_iv = np.column_stack([gt_on, gt_on + 0.1])
        est_iv = np.column_stack([p_on, p_on + 0.1])
        pr, rc, f1, _ = mir_eval.transcription.precision_recall_f1_overlap(
            gt_iv, librosa.midi_to_hz(ref_p), est_iv, librosa.midi_to_hz(est_p),
            onset_tolerance=ONSET_TOL, offset_ratio=None)
        return pr, rc, f1

    pr, rc, f1 = f(gt_pitch, p_pitch)
    _, _, f1_pc = f(gt_pitch % 12 + 60, p_pitch % 12 + 60)   # octave-blind score

    # sampler-trigger MIDI (e.g. C3 triggers an F1 808) sits a constant transposition
    # from sounding pitch — find the majority shift among time-matched pairs and
    # rescore with it. The shift itself is the fold needed to land in Trell's frame.
    shifts = []
    for g_t, g_p in zip(gt_on, gt_pitch):
        near = np.abs(p_on - g_t) <= ONSET_TOL
        if near.any():
            shifts.extend((p_pitch[near] - g_p).tolist())
    shift = int(np.bincount(np.array(shifts) - min(shifts)).argmax() + min(shifts)) if shifts else 0
    _, _, f1_shift = f(gt_pitch + shift, p_pitch)

    onset_f1, _, _ = mir_eval.onset.f_measure(gt_on, np.unique(p_on), window=ONSET_TOL)

    per_gt = [np.sum((p_on >= g) & (p_on < g_end)) for g, g_end in
              zip(gt_on, np.append(gt_on[1:], span))]
    return {"precision": round(pr, 2), "recall": round(rc, 2), "f1": round(f1, 2),
            "onset_f1": round(onset_f1, 2),
            "f1_pitch_class": round(f1_pc, 2),
            "f1_transposed": round(f1_shift, 2), "detected_shift_semis": shift,
            "split_rate": round(float(np.mean([max(0, c - 1) for c in per_gt])), 2),
            "offset_s": round(off, 2),
            "n_gt": len(gt_on), "n_pred": int(sel.sum())}


def eval_drums(gt, pred_on, bpm):
    gt_on, _, span = gt
    if len(pred_on) == 0 or len(gt_on) == 0:
        return {"f1": 0, "n_gt": len(gt_on), "n_pred": len(pred_on)}
    off = best_offset(gt_on, pred_on, bpm, span)
    sel = (pred_on >= off - ONSET_TOL) & (pred_on <= off + span + ONSET_TOL)
    p_on = pred_on[sel] - off
    f1, pr, rc = mir_eval.onset.f_measure(gt_on, p_on, window=ONSET_TOL)
    return {"precision": round(pr, 2), "recall": round(rc, 2), "f1": round(f1, 2),
            "offset_bars": round(off / (240 / bpm), 1),
            "n_gt": len(gt_on), "n_pred": int(sel.sum())}


# ------------------------------------------------------------------ test C: audio likeness

def compare_audio(original_path, recreation_path):
    """Trell's test: how alike does a bounced recreation sound to the original?
    Chroma similarity = harmonic content; onset-envelope correlation = rhythm.
    Scores are relative — use them to compare pipeline versions on the same song."""
    ya, sra = librosa.load(str(original_path), mono=True)
    yb, srb = librosa.load(str(recreation_path), sr=sra, mono=True)
    n = min(len(ya), len(yb))
    ya, yb = ya[:n], yb[:n]
    ca = librosa.feature.chroma_cqt(y=ya, sr=sra)
    cb = librosa.feature.chroma_cqt(y=yb, sr=sra)
    m = min(ca.shape[1], cb.shape[1])
    chroma_sim = float(np.mean(np.sum(ca[:, :m] * cb[:, :m], axis=0) /
                               (np.linalg.norm(ca[:, :m], axis=0) *
                                np.linalg.norm(cb[:, :m], axis=0) + 1e-9)))
    oa = librosa.onset.onset_strength(y=ya, sr=sra)
    ob = librosa.onset.onset_strength(y=yb, sr=sra)
    m = min(len(oa), len(ob))
    rhythm_corr = float(np.corrcoef(oa[:m], ob[:m])[0, 1])
    return {"harmonic_likeness": round(chroma_sim, 3),
            "rhythm_likeness": round(rhythm_corr, 3)}


# ------------------------------------------------------------------ driver

def run(skip_demucs=False):
    song = discover(GT_DIR)
    bpm = song["bpm"]
    print(f"ground truth: {song['title']}  ({len(song['pairs'])} paired parts)")
    if song["unpaired"]:
        print(f"  unpaired bounces (no matching MIDI): {song['unpaired']}")

    results = {"song": song["title"], "bpm": bpm, "clean_stem": {}, "full_pipeline": {}}

    # ---- Test A: clean solo bounces
    print("\nTEST A — clean-stem transcription (no separation):")
    gts = {}
    for part, files in song["pairs"].items():
        gt = load_gt_midi(files["midi"], bpm)
        gts[part] = gt
        drum = bool(set(part.split()) & DRUM_WORDS)
        r = (eval_drums(gt, predict_onsets(files["bounce"]), bpm) if drum
             else eval_melodic(gt, predict_melodic(files["bounce"]), bpm))
        results["clean_stem"][part] = r
        print(f"  {part:<16} {r}")

    # ---- Test B: full mix -> demucs -> transcribe
    if not skip_demucs:
        print("\nTEST B — full pipeline (mix -> Demucs -> transcribe)…")
        cache = GT_DIR / "_stems_cache"
        stem_dir = cache / CONFIG["demucs_model"] / song["mix"].stem
        if not stem_dir.exists() or not list(stem_dir.glob("*.wav")):
            separate_stems(song["mix"], cache)
        stems = {p.stem: p for p in stem_dir.glob("*.wav")}
        if True:
            drum_parts = [p for p in gts if set(p.split()) & DRUM_WORDS]
            mel_parts = [p for p in gts if p not in drum_parts]
            bass_part = next((p for p in mel_parts if "808" in p or "bass" in p), None)

            if bass_part and "bass" in stems:
                r = eval_melodic(gts[bass_part], predict_melodic(stems["bass"]), bpm)
                results["full_pipeline"][bass_part] = r
                print(f"  bass stem  vs {bass_part:<14} {r}")
            others = [p for p in mel_parts if p != bass_part]
            if others and "other" in stems:
                pred = predict_melodic(stems["other"])
                for part in others:
                    r = eval_melodic(gts[part], pred, bpm)
                    results["full_pipeline"][part] = r
                    print(f"  other stem vs {part:<14} {r}")
            if drum_parts and "drums" in stems:
                pred = predict_onsets(stems["drums"])
                gt_all = np.sort(np.concatenate([gts[p][0] for p in drum_parts]))
                span = max(gts[p][2] for p in drum_parts)
                r = eval_drums((gt_all, None, span), pred, bpm)
                results["full_pipeline"]["all drums (union)"] = r
                print(f"  drum stem  vs all drums      {r}")

    out = DATA_DIR / f"transcription_eval_{song['title'].replace(' ', '_')}.json"
    out.write_text(json.dumps(results, indent=1))
    print(f"\nwrote {out}")
    return results


if __name__ == "__main__":
    run(skip_demucs="--skip-demucs" in sys.argv)
