#!/usr/bin/env python3
"""Turn lecture audio into timestamped transcripts, and clean up ASR term errors.

This is the last tier of the text ladder: bili_fetch.py fetches the video's own
subtitles when they exist, and anything still missing is transcribed here on this
machine with faster-whisper (GPU first, CPU fallback, no torch required).

    python transcribe.py --check                       # verify device + model, then stop
    python transcribe.py downloads/ -o transcripts      # transcribe a directory
    python transcribe.py --apply-glossary terms.json -o transcripts --dry-run
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

AUDIO_EXTS = {".m4a", ".mp3", ".wav", ".flac", ".aac", ".opus", ".webm", ".mp4", ".mkv"}
TEXT_EXTS = (".md", ".txt", ".srt")

# turbo is the accuracy/speed sweet spot for lecture audio; small is the CPU default
# because turbo on CPU is slower than a 2-hour-lecture budget allows.
MODEL_GPU, MODEL_CPU = "large-v3-turbo", "small"

# The Hub is unreachable from mainland China, and its newer Xet storage backend has no
# mirror, so the mirror alone is not enough -- Xet must be off. Every user there hits
# this on the first run, so the failure says what to do instead of dumping a traceback.
DOWNLOAD_HINT = """[hint] could not download the model weights. If you are in mainland China:
       PowerShell:  $env:HF_ENDPOINT='https://hf-mirror.com'; $env:HF_HUB_DISABLE_XET='1'
       bash:        export HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1
       Or pick a smaller --model (e.g. small) / use --device cpu."""


# --------------------------------------------------------------------------- local

def pick_device(requested: str) -> tuple[str, str]:
    """Return (device, compute_type). 8 GB VRAM fits int8_float16, not float16."""
    import ctranslate2

    if requested == "cpu":
        return "cpu", "int8"
    try:
        if ctranslate2.get_cuda_device_count() < 1:
            raise RuntimeError("no CUDA device visible to CTranslate2")
        return "cuda", "int8_float16"
    except Exception as e:
        if requested == "cuda":
            raise
        print(f"[warn] CUDA unusable ({e}); falling back to CPU", file=sys.stderr)
        return "cpu", "int8"


def _is_cuda_error(e: Exception) -> bool:
    s = str(e).lower()
    return any(k in s for k in ("cublas", "cudnn", "cuda", "no kernel image"))


def load_model(model_name: str | None, device: str, compute_type: str, cpu_threads: int | None):
    from faster_whisper import WhisperModel

    name = model_name or (MODEL_GPU if device == "cuda" else MODEL_CPU)
    print(f"[info] loading {name} on {device}/{compute_type}", flush=True)
    t0 = time.time()
    try:
        model = WhisperModel(name, device=device, compute_type=compute_type, cpu_threads=cpu_threads or 0)
    except Exception as e:
        if device != "cuda" or not _is_cuda_error(e):
            if "connect" in str(e).lower() or "snapshot" in str(e).lower():
                print(DOWNLOAD_HINT, file=sys.stderr)
            raise
        # Missing cublas64_12.dll is the usual cause; see README.
        print(f"[warn] CUDA load failed ({e}); falling back to CPU int8", file=sys.stderr)
        name, device, compute_type = MODEL_CPU, "cpu", "int8"
        model = WhisperModel(name, device=device, compute_type=compute_type, cpu_threads=cpu_threads or 0)
    print(f"[info] loaded in {time.time() - t0:.1f}s", flush=True)
    return model, name, device


def local_segments(model, audio: Path, language: str | None):
    """Yield (seconds, text) pairs, printing progress as it goes."""
    segments, info = model.transcribe(
        str(audio),
        language=language,
        vad_filter=True,  # also skips silence, so long lectures get faster
        condition_on_previous_text=False,  # breaks Whisper's repetition loops
        beam_size=5,
    )
    total = info.duration or 0.0
    for seg in segments:
        text = seg.text.strip()
        if text:
            pct = f"{seg.end / total * 100:5.1f}%" if total else "  ?  "
            print(f"\r  {pct} {hms(seg.end)}/{hms(total)}", end="", flush=True)
            yield seg.start, text


# --------------------------------------------------------------------------- glossary

def load_glossary(path: Path, min_len: int) -> list[tuple[str, str, bool]]:
    """Load {wrong: right} or {wrong: {replace: ..., regex: true}} term corrections.

    Keys shorter than min_len are dropped: for Chinese, single-character replacements
    match inside unrelated words and silently corrupt the transcript. The upstream tool
    this format comes from has no such guard.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit(f"[error] {path} must be a JSON object of wrong -> right mappings")
    rules = []
    for key, value in raw.items():
        if key.startswith("_"):
            continue  # allow "_readme"/"_notes" free-text comments inside the glossary
        if isinstance(value, dict):
            if not value.get("regex"):
                raise SystemExit(f"[error] {path}: object form is only valid with \"regex\": true ({key!r})")
            rules.append((key, str(value.get("replace", "")), True))
        elif isinstance(value, str):
            if len(key) < min_len:
                print(f"[warn] skipping {key!r}: shorter than {min_len} chars", file=sys.stderr)
                continue
            rules.append((re.escape(key), value, False))
        else:
            raise SystemExit(f"[error] {path}: value for {key!r} must be a string or an object")
    return rules


def apply_rules(text: str, rules: list[tuple[str, str, bool]]) -> tuple[str, list[tuple[str, int]]]:
    hits = []
    for pattern, repl, _ in rules:
        text, n = re.subn(pattern, repl, text)
        if n:
            hits.append((pattern, n))
    return text, hits


def run_glossary(args) -> int:
    rules = load_glossary(Path(args.apply_glossary), args.glossary_min_len)
    files = []
    for raw in args.inputs or [str(args.outdir)]:
        p = Path(raw)
        if p.is_dir():
            files += sorted(f for f in p.iterdir() if f.suffix.lower() in TEXT_EXTS)
        elif p.is_file():
            files.append(p)
    if not files:
        raise SystemExit("[error] no .md/.txt/.srt files to correct")
    total_hits = 0
    for f in files:
        original = f.read_text(encoding="utf-8")
        fixed, hits = apply_rules(original, rules)
        total_hits += sum(n for _, n in hits)
        detail = ", ".join(f"{p}×{n}" for p, n in sorted(hits, key=lambda x: -x[1]))
        # A term replaced far more often than its share of the text usually means the
        # pattern is matching inside longer words -- report it instead of hiding it.
        # The bar is high on purpose: some entries are legitimately frequent (ψ alone
        # appears hundreds of times in a lecture), so only outliers are worth flagging.
        loud = [p for p, n in hits if n > 200]
        print(f"{f.name}: {sum(n for _, n in hits)} hit(s){' -- ' + detail if detail else ''}")
        if loud:
            print(f"  [warn] suspiciously frequent, check these patterns: {', '.join(loud)}", file=sys.stderr)
        if not args.dry_run and fixed != original:
            f.write_text(fixed, encoding="utf-8")
    if args.dry_run:
        print(f"[dry-run] {total_hits} replacement(s) in {len(files)} file(s); nothing written")
    else:
        print(f"[done] {total_hits} replacement(s) in {len(files)} file(s)")
    return 0


# --------------------------------------------------------------------------- shared

def hms(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def write_outputs(stem: str, segments: list[tuple[float, str]], outdir: Path) -> None:
    md = [f"# {stem}\n"]
    txt = []
    for start, text in segments:
        md.append(f"[{hms(start)}] {text}")
        txt.append(text)
    if not txt:
        raise SystemExit(f"[error] no speech detected in {stem}")
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / f"{stem}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (outdir / f"{stem}.txt").write_text("\n".join(txt) + "\n", encoding="utf-8")
    print(f"\r  done {len(txt)} lines -> {stem}.md, {stem}.txt")


def collect_audio(inputs: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in inputs:
        p = Path(raw)
        if p.is_dir():
            files += sorted(f for f in p.iterdir() if f.suffix.lower() in AUDIO_EXTS)
        elif p.is_file():
            files.append(p)
        else:
            print(f"[warn] skipping missing path {raw}", file=sys.stderr)
    return files


# --------------------------------------------------------------------------- main

def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="*", help="audio files and/or directories")
    ap.add_argument("-o", "--outdir", default="transcripts", help="where .md/.txt go (default: transcripts)")
    ap.add_argument("--engine", choices=["local"], default="local", help=argparse.SUPPRESS)
    ap.add_argument("--model", help=f"faster-whisper model (default: {MODEL_GPU} on GPU, {MODEL_CPU} on CPU)")
    ap.add_argument("--device", choices=["auto", "cuda", "cpu"], default="auto")
    ap.add_argument("--language", default="zh", help="'auto' to detect (default: zh)")
    ap.add_argument("--cpu-threads", type=int, help="default: all cores")
    ap.add_argument("--force", action="store_true", help="redo files that already have transcripts")
    ap.add_argument("--check", action="store_true", help="verify the local model loads, then exit")
    ap.add_argument("--apply-glossary", metavar="TERMS.json",
                    help="standalone mode: apply term corrections to existing .md/.txt/.srt and exit")
    ap.add_argument("--glossary-min-len", type=int, default=2, help="shortest replaceable key (default: 2)")
    ap.add_argument("--dry-run", action="store_true", help="report glossary hits without writing")
    args = ap.parse_args()

    if args.apply_glossary:
        return run_glossary(args)

    language = None if args.language == "auto" else args.language
    outdir = Path(args.outdir)

    model = name = None
    if args.check:
        device, compute_type = pick_device(args.device)
        model, name, device = load_model(args.model, device, compute_type, args.cpu_threads)
        import numpy as np

        model.transcribe(np.zeros(16000, dtype=np.float32), beam_size=1)
        print(f"[ok] {name} on {device}/{compute_type} can transcribe")
        return 0

    # Decide what still needs work before paying for a model load: re-running over an
    # already-transcribed directory should be instant, not a 1.6 GB download.
    files = collect_audio(args.inputs)
    if not files:
        ap.error("no audio files given (pass files or a directory)")
    todo = [f for f in files if args.force or not (outdir / f"{f.stem}.txt").exists()]
    if not todo:
        print(f"[info] nothing to do: all {len(files)} file(s) already transcribed in {outdir}/")
        return 0
    if model is None:
        device, compute_type = pick_device(args.device)
        model, name, device = load_model(args.model, device, compute_type, args.cpu_threads)

    print(f"[info] engine: local {name}; {len(files)} file(s), {len(files) - len(todo)} already done, {len(todo)} to go")
    started = time.time()
    for i, f in enumerate(todo, 1):
        print(f"\n[{i}/{len(todo)}] {f.name}", flush=True)
        t0 = time.time()
        segments = list(local_segments(model, f, language))
        write_outputs(f.stem, segments, outdir)
        print(f"  elapsed {hms(time.time() - t0)}")
    if len(todo) > 1:
        print(f"\n[done] {len(todo)} file(s) in {hms(time.time() - started)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
