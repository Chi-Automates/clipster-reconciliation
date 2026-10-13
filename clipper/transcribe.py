"""Local transcription with faster-whisper (word-level timestamps), cached per video."""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

_MODEL = None
_MODEL_NAME = None


def _model(name: str):
    global _MODEL, _MODEL_NAME
    if _MODEL is None or _MODEL_NAME != name:
        from faster_whisper import WhisperModel

        log.info("Loading Whisper model %s (first run downloads it once)", name)
        _MODEL = WhisperModel(name, device="auto", compute_type="int8")
        _MODEL_NAME = name
    return _MODEL


def load_audio(media: Path, sample_rate: int = 16000) -> np.ndarray:
    """Decode with ffmpeg to 16 kHz mono float32. Avoids depending on PyAV's API, which changes often."""
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(media),
         "-vn", "-ac", "1", "-ar", str(sample_rate), "-f", "f32le", "-"],
        capture_output=True, timeout=3600,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg could not decode {media.name}: {proc.stderr.decode(errors='ignore')[-300:]}")
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()


def transcribe(media: Path, cache_path: Path, model_name: str) -> dict:
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    segments_iter, info = _model(model_name).transcribe(
        load_audio(media), word_timestamps=True, vad_filter=True, beam_size=5,
    )
    segments = []
    for seg in segments_iter:
        words = [
            {"start": round(w.start, 2), "end": round(w.end, 2), "word": w.word.strip()}
            for w in (seg.words or []) if w.word.strip()
        ]
        if words:
            segments.append({"start": round(seg.start, 2), "end": round(seg.end, 2),
                             "text": seg.text.strip(), "words": words})
    data = {"language": info.language, "duration": info.duration, "segments": segments}
    tmp = cache_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(cache_path)
    return data


def words_between(transcript: dict, start: float, end: float) -> list[dict]:
    return [w for s in transcript["segments"] for w in s["words"] if w["start"] >= start - 0.05 and w["end"] <= end + 0.05]
