#!/usr/bin/env python3
"""Single meeting-pipeline script: transcribe recordings + lint minutes.

Subcommands:
    transcribe <recording> [options]   — meeting recording (webm/mp4/mkv/audio) → text transcript
    lint <file.md> [...]               — check the minutes' YAML frontmatter (type: meeting-note)
    check-setup [--model X]            — is the one-time setup (venv + model) done? exit 0/1

The transcribe pipeline (local, CPU-only, the recording never leaves the machine):
  1. audio extraction — the input (incl. Yandex Telemost `.webm` video) is decoded
     into normalized 16 kHz mono wav (PyAV, no system ffmpeg needed);
  2. transcription — faster-whisper (CTranslate2 engine, large-v3 model by default);
     the result is timestamped segments in `meetings/.transcripts/<recording-name>.md`.
     The language is auto-detected unless forced with --language.

No diarization: the transcript is flat `[HH:MM:SS] text` with no speaker labels.
Attributing utterances to participants is done via the roster when assembling the
minutes (that is the agent's job).

The script sets up its own environment: when dependencies are missing it creates a
managed venv in ~/.cache/meeting-skill/venv (override: $MEETING_VENV), installs the
dependencies (faster-whisper, pyyaml) and re-executes itself from it. No separate
setup command is needed. The large-v3 model (~3 GB) is pulled on the first transcribe.

The meetings folder is `meetings/` at the repo root (override: $MEETINGS_DIR).

Exit codes: 0 — success, ≠0 — error (with a clear message on stderr).
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import os
import subprocess
import sys
import venv as venv_mod
import wave
from pathlib import Path

DEPS = ("faster-whisper", "pyyaml")
VENV = Path(os.environ.get("MEETING_VENV") or Path.home() / ".cache" / "meeting-skill" / "venv")
MEETINGS_DIR = os.environ.get("MEETINGS_DIR", "meetings")

# Modules each subcommand needs: the bootstrap doesn't pull in the heavy
# faster-whisper when the system pyyaml is enough for lint.
NEEDED_MODULES = {
    "transcribe": ("faster_whisper", "numpy"),
    "lint": ("yaml",),
}


def _die(msg: str, code: int = 1) -> "NoReturn":  # type: ignore[valid-type]
    print(f"✗ {msg}", file=sys.stderr)
    raise SystemExit(code)


def _hms(seconds: float) -> str:
    """Seconds → HH:MM:SS."""
    s = int(round(seconds))
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def repo_root() -> Path:
    """Git repository root; outside a repo — the current directory."""
    r = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True
    )
    return Path(r.stdout.strip()) if r.returncode == 0 else Path.cwd()


def ensure_deps(modules: tuple[str, ...]) -> None:
    """Guarantee the modules are importable; bootstrap the managed venv if not.

    Creates a venv at $MEETING_VENV, installs DEPS and re-executes the script from
    it. Re-entering after the restart with the same modules missing is an error
    (broken environment).
    """
    missing = [m for m in modules if importlib.util.find_spec(m) is None]
    if not missing:
        return
    if os.environ.get("_MEETING_BOOTSTRAPPED"):
        _die(
            f"modules still missing after installing dependencies: {', '.join(missing)}.\n"
            f"  Broken environment? Recreate it: rm -rf {VENV}"
        )

    vpy = VENV / "bin" / "python"
    if not vpy.exists():
        print(f"· creating environment {VENV}…", file=sys.stderr)
        VENV.parent.mkdir(parents=True, exist_ok=True)
        venv_mod.EnvBuilder(with_pip=True).create(VENV)
    print(f"· installing dependencies: {', '.join(DEPS)}…", file=sys.stderr)
    subprocess.run([str(vpy), "-m", "pip", "install", "-q", *DEPS], check=True)

    os.environ["_MEETING_BOOTSTRAPPED"] = "1"
    os.execv(str(vpy), [str(vpy), str(Path(__file__).resolve()), *sys.argv[1:]])


# ── transcribe ───────────────────────────────────────────────────────────────

def extract_audio(src: Path, sample_rate: int):
    """Stage 1: decode the recording (incl. .webm video) into 16 kHz mono audio.

    Returns (float32 numpy array, path to the saved wav). Decoding goes through
    PyAV (a faster-whisper dependency), so no system ffmpeg is required and video
    containers (.webm/.mp4/.mkv) are read the same way as audio files.
    """
    import numpy as np
    from faster_whisper.audio import decode_audio

    print(f"· extracting audio track from {src.name} → {sample_rate} Hz mono…", file=sys.stderr)
    audio = decode_audio(str(src), sampling_rate=sample_rate)  # float32 [-1..1], mono

    wav_path = src.with_name(f"{src.stem}.16k.wav")
    pcm16 = (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm16.tobytes())
    print(f"· audio track saved: {wav_path}", file=sys.stderr)
    return audio, wav_path


def run_whisper(audio, model_name: str, language: str | None, compute_type: str):
    """Stage 2: transcribe the audio array with faster-whisper. Returns (segments, info).

    language=None lets Whisper auto-detect the language from the audio.
    """
    from faster_whisper import WhisperModel

    lang_label = language or "auto"
    print(f"· transcribing (model={model_name}, lang={lang_label}, cpu/{compute_type})…", file=sys.stderr)
    model = WhisperModel(model_name, device="cpu", compute_type=compute_type)
    segments, info = model.transcribe(audio, language=language, vad_filter=True)
    # segments is a lazy generator; materialize it (this is where recognition runs).
    return list(segments), info


def write_transcript(out_path: Path, segments, info, src: Path) -> None:
    duration = getattr(info, "duration", 0.0) or 0.0
    lang = getattr(info, "language", "?")
    lines = [
        f"# Transcript: {src.name}",
        "",
        f"- Duration: ~{_hms(duration)}",
        f"- Language: {lang}",
        f"- Segments: {len(segments)}",
        "",
        "> Draft transcript **with no speaker labels** (no diarization was performed).",
        "> Utterances are attributed to participants via the roster when assembling the minutes.",
        "",
        "---",
        "",
    ]
    for seg in segments:
        text = (seg.text or "").strip()
        if text:
            lines.append(f"[{_hms(seg.start)}] {text}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"✓ transcript written: {out_path}  (segments: {len(segments)})", file=sys.stderr)


def cmd_transcribe(args: argparse.Namespace) -> int:
    src = Path(args.audio)
    if not src.is_file():
        _die(f"recording file not found: {src}")
    ensure_deps(NEEDED_MODULES["transcribe"])

    out_path = (
        Path(args.out)
        if args.out
        else repo_root() / MEETINGS_DIR / ".transcripts" / f"{src.stem}.md"
    )
    audio, _wav = extract_audio(src, args.sample_rate)
    segments, info = run_whisper(audio, args.model, args.language, args.compute_type)
    write_transcript(out_path, segments, info, src)
    return 0


# ── check-setup ──────────────────────────────────────────────────────────────

def model_cache_dir(model_name: str) -> Path:
    """HF hub cache folder where faster-whisper stores the model."""
    repo = model_name if "/" in model_name else f"Systran/faster-whisper-{model_name}"
    hub = Path(
        os.environ.get("HF_HUB_CACHE")
        or Path(os.environ.get("HF_HOME") or Path.home() / ".cache" / "huggingface") / "hub"
    )
    return hub / ("models--" + repo.replace("/", "--"))


def cmd_check_setup(args: argparse.Namespace) -> int:
    """Fast dependency-free probe: has the one-time setup already happened?

    The venv alone is not a valid signal — lint bootstraps the same venv without
    ever pulling the Whisper model, and the ~3 GB model download is what the user
    must be warned about before the first transcribe.
    """
    venv_ok = (VENV / "bin" / "python").exists()
    mdir = model_cache_dir(args.model)
    # a snapshot symlink to model.bin appears only after the download completes
    model_ok = any(mdir.glob("snapshots/*/model.bin"))
    print(f"venv ({VENV}): {'ok' if venv_ok else 'missing'}")
    print(f"model {args.model} ({mdir}): {'ok' if model_ok else 'missing'}")
    if venv_ok and model_ok:
        print("✓ setup complete — transcribe will start right away")
        return 0
    print("✗ first run pending: the next transcribe will install dependencies and/or download the ~3 GB model")
    return 1


# ── lint ─────────────────────────────────────────────────────────────────────

# Required frontmatter fields of a meeting minutes file (template — meetings/README.md).
REQUIRED_FIELDS = {
    "title", "type", "meeting_type", "status", "date", "participants", "author", "related",
}
MEETING_TYPES = {"tech", "product"}
# planned — pre-meeting draft (agenda present, content empty);
# final — filled in from the transcript after the meeting.
MEETING_STATUSES = {"planned", "final"}
LIST_FIELDS = ("related", "participants", "decisions", "action_items")


def _as_date(value):
    """Coerce the value to a date, or return None if it isn't one."""
    if isinstance(value, dt.date):  # yaml unwraps `2026-07-17` into a date
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def check_protocol(path: Path) -> list[str]:
    """Check one minutes file; return a list of errors (empty — all clean)."""
    import yaml

    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return ["no frontmatter (meeting minutes must have one)"]

    parts = text.split("---", 2)
    if len(parts) < 3:
        return ["frontmatter not closed by a second '---'"]

    try:
        data = yaml.safe_load(parts[1])
    except yaml.YAMLError as exc:
        return [f"YAML does not parse: {str(exc).splitlines()[0]}"]
    if not isinstance(data, dict):
        return ["frontmatter is not a key-value mapping"]

    errors: list[str] = []
    if data.get("type") != "meeting-note":
        errors.append(f"type={data.get('type')!r}, expected 'meeting-note'")

    missing = sorted(REQUIRED_FIELDS - data.keys())
    if missing:
        errors.append("missing required fields: " + ", ".join(missing))

    if data.get("meeting_type") not in MEETING_TYPES:
        errors.append(f"meeting_type={data.get('meeting_type')!r}, expected one of {sorted(MEETING_TYPES)}")
    if data.get("status") not in MEETING_STATUSES:
        errors.append(f"status={data.get('status')!r}, expected one of {sorted(MEETING_STATUSES)}")
    if "date" in data and _as_date(data.get("date")) is None:
        errors.append(f"date is not a date: {data.get('date')!r}")

    for field in LIST_FIELDS:
        if field in data and not isinstance(data[field], list):
            errors.append(f"{field} must be a list, not {type(data[field]).__name__}")

    return errors


def cmd_lint(args: argparse.Namespace) -> int:
    targets = [Path(p) for p in args.files if Path(p).name != "README.md"]
    if not targets:
        print("Nothing to check — only README/an empty list was given.")
        return 0
    ensure_deps(NEEDED_MODULES["lint"])

    bad = 0
    for path in targets:
        if not path.is_file():
            print(f"  ❌ {path}\n       • file not found")
            bad += 1
            continue
        errors = check_protocol(path)
        if errors:
            bad += 1
            print(f"  ❌ {path}")
            for e in errors:
                print(f"       • {e}")
        else:
            print(f"  ✅ {path}")

    print(f"\nTotal: OK — {len(targets) - bad}, errors — {bad}")
    return 1 if bad else 0


# ── main ─────────────────────────────────────────────────────────────────────

def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        prog="meeting.py",
        description="Meeting pipeline: transcribe recordings and lint minutes.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("transcribe", help="meeting recording → text transcript")
    t.add_argument("audio", help="path to the recording (webm/mp4/mkv/mp3/m4a/wav/…)")
    t.add_argument("--language", default=None, help="recognition language code, e.g. ru (default: auto-detect)")
    t.add_argument("--model", default="large-v3", help="Whisper model (default: large-v3)")
    t.add_argument("--out", default=None, help=f"where to write the transcript (.md); default: {MEETINGS_DIR}/.transcripts/")
    t.add_argument("--compute-type", default="int8", help="CTranslate2 compute type (CPU: int8)")
    t.add_argument("--sample-rate", type=int, default=16000, help="extracted audio sample rate (Hz)")
    t.set_defaults(fn=cmd_transcribe)

    l = sub.add_parser("lint", help="check the minutes' frontmatter (type: meeting-note)")
    l.add_argument("files", nargs="+", help="minutes .md files")
    l.set_defaults(fn=cmd_lint)

    c = sub.add_parser("check-setup", help="is the one-time setup (venv + Whisper model) done? exit 0/1")
    c.add_argument("--model", default="large-v3", help="Whisper model to check the cache for (default: large-v3)")
    c.set_defaults(fn=cmd_check_setup)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
