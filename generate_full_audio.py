#!/usr/bin/env python3
"""
Generate a single continuous MP3 of an entire story for Spotify upload.

Narrates: story title, optional subtitle, author credit, then each chapter
heading followed by all its nodes (paragraph, diagram, callout, list) in order,
with configurable silence gaps between sections.

Usage:
    python generate_full_audio.py stories/<id>/story.json

Environment variables:
    STORY_TTS_API_KEY   API key for the TTS endpoint

Options:
    --api-key KEY          API key (overrides env var)
    --url URL              TTS endpoint URL
    --voice VOICE          Kokoro voice (default: af_heart)
    --speed FLOAT          Speech speed, 0.5-2.0 (default: 0.9)
    --output PATH          Output MP3 path (default: <story-dir>/<story-id>.mp3)
    --title-pause FLOAT    Silence after title block in seconds (default: 2.5)
    --chapter-pause FLOAT  Silence between chapters in seconds (default: 2.5)
    --para-pause FLOAT     Silence between paragraphs in seconds (default: 0.8)
    --workers N            Parallel TTS workers (default: 3)
    --dry-run              Print segment list without calling the API

Examples:
    STORY_TTS_API_KEY=abc123 python generate_full_audio.py stories/the-shy-gas-a-nitrogen-story/story.json
    python generate_full_audio.py stories/my-story/story.json --output my-story-audiobook.mp3
    python generate_full_audio.py stories/my-story/story.json --dry-run
"""

import argparse
import io
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: 'requests' is not installed. Run: pip install requests", file=sys.stderr)
    sys.exit(1)

try:
    from pydub import AudioSegment
except ImportError:
    print("ERROR: 'pydub' is not installed. Run: pip install pydub", file=sys.stderr)
    print("       Also requires ffmpeg: https://ffmpeg.org/download.html", file=sys.stderr)
    sys.exit(1)

DEFAULT_URL         = "https://elvinio--kokoro-tts-fastapi-app.modal.run/tts"
DEFAULT_VOICE       = "af_heart"
DEFAULT_SPEED       = 0.9
DEFAULT_TITLE_PAUSE = 2.5
DEFAULT_CHAP_PAUSE  = 2.5
DEFAULT_PARA_PAUSE  = 0.8
MAX_RETRIES         = 3
RETRY_DELAYS        = [2, 5, 10]


# ── Text normalisation (same logic as generate_audio.py) ─────────────────────

_SUBSCRIPT = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")

_CHEM_RE = re.compile(
    r"(?<![a-z])(?:[A-Z][a-z]?\d*){2,}[+\-]?(?![a-zA-Z])"
    r"|(?<![a-z])[A-Z]\d+[+\-]?(?![a-zA-Z])"
)


def _expand_chem(m: re.Match) -> str:
    parts = []
    s = m.group()
    i = 0
    while i < len(s):
        ch = s[i]
        if ch.isupper():
            if i + 1 < len(s) and s[i + 1].islower():
                parts.append(s[i : i + 2])
                i += 2
            else:
                parts.append(ch)
                i += 1
        elif ch.isdigit():
            j = i + 1
            while j < len(s) and s[j].isdigit():
                j += 1
            parts.append(s[i:j])
            i = j
        elif ch == "-":
            parts.append("minus")
            i += 1
        elif ch == "+":
            parts.append("plus")
            i += 1
        else:
            parts.append(ch)
            i += 1
    return " ".join(parts)


def normalize_tts_text(text: str) -> str:
    text = text.translate(_SUBSCRIPT)
    text = text.replace("⁻", "-").replace("⁺", "+")
    for sup, asc in zip("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789"):
        text = text.replace(sup, asc)
    return _CHEM_RE.sub(_expand_chem, text)


def _english_text(node: dict) -> str:
    if node["type"] == "paragraph":
        return node.get("text", "").strip()
    if node["type"] == "diagram":
        return node.get("caption", "").strip()
    if node["type"] == "callout":
        label = node.get("label", "").strip()
        body  = node.get("text", "").strip()
        return (label + ". " + body) if label and body else (label or body)
    if node["type"] == "list":
        items = [i.strip() for i in node.get("items", []) if i.strip()]
        if node.get("ordered"):
            words = ["One", "Two", "Three", "Four", "Five", "Six", "Seven",
                     "Eight", "Nine", "Ten", "Eleven", "Twelve", "Thirteen",
                     "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen",
                     "Nineteen", "Twenty"]
            items = [f"{words[i] if i < len(words) else i + 1}: {item}"
                     for i, item in enumerate(items)]
        return ". ".join(items)
    return ""


# ── Segment model ─────────────────────────────────────────────────────────────

@dataclass
class Segment:
    index: int
    label: str
    text: str
    pause_ms: int


def build_segments(story: dict, args) -> list:
    segs = []
    idx = 0

    title_pause_ms = int(args.title_pause * 1000)
    chap_pause_ms  = int(args.chapter_pause * 1000)
    para_pause_ms  = int(args.para_pause * 1000)

    meta     = story.get("meta", {})
    title    = meta.get("title", "").strip()
    subtitle = meta.get("subtitle", "").strip()

    if title:
        segs.append(Segment(idx, "title", normalize_tts_text(title), title_pause_ms))
        idx += 1

    if subtitle:
        segs.append(Segment(idx, "subtitle", normalize_tts_text(subtitle), 500))
        idx += 1

    chapters = story.get("chapters", [])
    for ch_num, chapter in enumerate(chapters, start=1):
        ch_title = chapter.get("title", "").strip()
        heading  = f"Chapter {ch_num}: {ch_title}" if ch_title else f"Chapter {ch_num}"
        segs.append(Segment(idx, f"ch{ch_num} heading", normalize_tts_text(heading), chap_pause_ms))
        idx += 1

        nodes = [n for n in chapter.get("nodes", []) if _english_text(n)]
        for n_num, node in enumerate(nodes):
            text = normalize_tts_text(_english_text(node))
            is_last = (n_num == len(nodes) - 1)
            pause = chap_pause_ms if is_last else para_pause_ms
            label = f"ch{ch_num}/{node['id']} ({node['type']})"
            segs.append(Segment(idx, label, text, pause))
            idx += 1

    return segs


# ── TTS API ───────────────────────────────────────────────────────────────────

def call_tts(text: str, args, session) -> bytes:
    payload = {
        "text":   text,
        "voice":  args.voice,
        "format": "mp3",
        "speed":  args.speed,
    }
    headers = {"X-API-Key": args.api_key} if args.api_key else {}

    for attempt, delay in enumerate(RETRY_DELAYS, start=1):
        try:
            resp = session.post(args.url, json=payload, headers=headers, timeout=60)
            resp.raise_for_status()
            return resp.content
        except requests.exceptions.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else "?"
            if code == 401:
                raise RuntimeError("401 Unauthorized - check your API key") from exc
            if code == 422:
                body = exc.response.text[:200] if exc.response is not None else ""
                raise RuntimeError(f"422 Unprocessable - payload rejected: {body}") from exc
            if attempt == len(RETRY_DELAYS):
                raise RuntimeError(f"HTTP {code} after {MAX_RETRIES} attempts") from exc
        except requests.exceptions.RequestException as exc:
            if attempt == len(RETRY_DELAYS):
                raise RuntimeError(f"Network error after {MAX_RETRIES} attempts: {exc}") from exc
        print(f"  retry in {delay}s...", file=sys.stderr)
        time.sleep(delay)


def fetch_segment(seg: Segment, args, session, cache_dir: Path) -> tuple:
    cache_file = cache_dir / f"{seg.index:04d}.mp3"
    if cache_file.exists():
        return seg.index, cache_file.read_bytes(), True
    data = call_tts(seg.text, args, session)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_bytes(data)
    return seg.index, data, False


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a single continuous MP3 audiobook from a Story Reader story.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("story_json", help="Path to story.json")
    parser.add_argument("--api-key",       default=os.getenv("STORY_TTS_API_KEY"),
                        help="TTS API key (env: STORY_TTS_API_KEY)")
    parser.add_argument("--url",           default=DEFAULT_URL)
    parser.add_argument("--voice",         default=DEFAULT_VOICE,
                        help=f"Kokoro voice (default: {DEFAULT_VOICE})")
    parser.add_argument("--speed",         type=float, default=DEFAULT_SPEED,
                        help=f"Speech speed 0.5-2.0 (default: {DEFAULT_SPEED})")
    parser.add_argument("--output",        default=None,
                        help="Output MP3 path (default: <story-dir>/<story-id>.mp3)")
    parser.add_argument("--title-pause",   type=float, default=DEFAULT_TITLE_PAUSE,
                        dest="title_pause",
                        help=f"Silence after title block in seconds (default: {DEFAULT_TITLE_PAUSE})")
    parser.add_argument("--chapter-pause", type=float, default=DEFAULT_CHAP_PAUSE,
                        dest="chapter_pause",
                        help=f"Silence between chapters in seconds (default: {DEFAULT_CHAP_PAUSE})")
    parser.add_argument("--para-pause",    type=float, default=DEFAULT_PARA_PAUSE,
                        dest="para_pause",
                        help=f"Silence between paragraphs in seconds (default: {DEFAULT_PARA_PAUSE})")
    parser.add_argument("--workers",       type=int, default=3,
                        help="Parallel TTS workers (default: 3)")
    parser.add_argument("--cache-dir",     default=None, dest="cache_dir",
                        help="Directory to cache per-segment MP3s (default: <story-dir>/.segment-cache)")
    parser.add_argument("--dry-run",       action="store_true", dest="dry_run",
                        help="Print segment list without calling the API")
    args = parser.parse_args()

    story_path = Path(args.story_json).resolve()
    if not story_path.exists():
        print(f"ERROR: story.json not found: {story_path}", file=sys.stderr)
        sys.exit(1)

    with story_path.open(encoding="utf-8") as f:
        story = json.load(f)

    story_dir = story_path.parent
    story_id  = story.get("id", story_dir.name)
    title     = story.get("meta", {}).get("title", story_id)

    output_path = Path(args.output) if args.output else story_dir / f"{story_id}.mp3"
    cache_dir   = Path(args.cache_dir) if args.cache_dir else story_dir / ".segment-cache"

    segments = build_segments(story, args)
    if not segments:
        print("No narratable content found in story.json.")
        sys.exit(0)

    total_silence_s = sum(s.pause_ms for s in segments) / 1000

    print(f"\nStory:    {title}")
    print(f"Segments: {len(segments)}")
    print(f"Voice:    {args.voice}  speed={args.speed}")
    print(f"Output:   {output_path}")
    print(f"Cache:    {cache_dir}")
    print(f"Pauses:   title={args.title_pause}s  chapter={args.chapter_pause}s  para={args.para_pause}s")
    print(f"          (~{total_silence_s:.0f}s of silence total)")
    print()

    if args.dry_run:
        print("DRY RUN - segment list:\n")
        for s in segments:
            pause_s = s.pause_ms / 1000
            preview = s.text[:80] + ("..." if len(s.text) > 80 else "")
            print(f"  [{s.index:>3}] +{pause_s:.1f}s  {s.label}")
            print(f"         {preview}")
            print()
        print(f"Total: {len(segments)} segments")
        return

    if not args.api_key:
        print("ERROR: No API key. Set STORY_TTS_API_KEY or use --api-key.", file=sys.stderr)
        sys.exit(1)

    mp3_map = {}
    errors = 0

    cached_count = sum(1 for s in segments if (cache_dir / f"{s.index:04d}.mp3").exists())
    if cached_count:
        print(f"Fetching segments ({cached_count}/{len(segments)} already cached)...")
    else:
        print(f"Fetching {len(segments)} segments from TTS API...")

    with requests.Session() as session:
        if args.workers == 1:
            for i, seg in enumerate(segments, 1):
                print(f"  [{i:>3}/{len(segments)}] {seg.label}", end=" ", flush=True)
                try:
                    _, data, from_cache = fetch_segment(seg, args, session, cache_dir)
                    mp3_map[seg.index] = data
                    tag = "cached" if from_cache else f"{len(data) // 1024} KB"
                    print(f"({tag})")
                except RuntimeError as exc:
                    print(f"ERROR: {exc}")
                    errors += 1
        else:
            futures = {}
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                for seg in segments:
                    fut = pool.submit(fetch_segment, seg, args, session, cache_dir)
                    futures[fut] = seg

                done = 0
                for fut in as_completed(futures):
                    done += 1
                    seg = futures[fut]
                    try:
                        idx, data, from_cache = fut.result()
                        mp3_map[idx] = data
                        tag = "cached" if from_cache else f"{len(data) // 1024} KB"
                        print(f"  [{done:>3}/{len(segments)}] {seg.label} ({tag})")
                    except RuntimeError as exc:
                        print(f"  [{done:>3}/{len(segments)}] ERROR {seg.label}: {exc}")
                        errors += 1

    if errors:
        print(f"\n{errors} segment(s) failed. No output written.", file=sys.stderr)
        sys.exit(1)

    print(f"\nStitching {len(segments)} segments...")
    combined = AudioSegment.empty()
    for seg in segments:
        audio   = AudioSegment.from_file(io.BytesIO(mp3_map[seg.index]), format="mp3")
        silence = AudioSegment.silent(duration=seg.pause_ms)
        combined += audio + silence

    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.export(str(output_path), format="mp3", bitrate="128k")

    duration_min = len(combined) / 1000 / 60
    size_mb      = output_path.stat().st_size / (1024 * 1024)
    print(f"\nDone: {output_path}")
    print(f"      {duration_min:.1f} min  |  {size_mb:.1f} MB")


if __name__ == "__main__":
    main()
