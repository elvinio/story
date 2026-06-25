#!/usr/bin/env python3
"""
Generate audio narration for a Story Reader story using a Kokoro TTS endpoint.

Generates audio for paragraph, diagram, callout, and list nodes.
Callout text is spoken as "label. body". List items are joined with ". ".

Bilingual stories: a node may also carry a `zh` token array (an array of
[character, pinyin] pairs). When present, a second Chinese clip is generated
from the characters using the Chinese voice and written to the node's `audioZh`
field (path: audio/<chapter>-<node>.zh.<fmt>).

Usage:
    python generate_audio.py stories/my-story/story.json

Environment variables:
    STORY_TTS_API_KEY   API key for the TTS endpoint

Options:
    --api-key KEY        API key (overrides env var)
    --url URL            TTS endpoint URL (default: https://elvinio--kokoro-tts-fastapi-app.modal.run/tts)
    --voice VOICE        Kokoro voice for English text (default: af_heart)
    --voice-zh VOICE     Kokoro voice for Chinese text (default: zf_xiaobei)
    --speed FLOAT        Speech speed, 0.5–2.0 (default: 0.9)
    --format FORMAT      Audio format: opus or mp3 (default: opus)
    --chapter ID [ID …]  Only process these chapter IDs (default: all chapters)
    --force              Overwrite existing audio files
    --dry-run            Print what would be generated without calling the API
    --workers N          Parallel workers (default: 3)

Examples:
    python generate_audio.py stories/the-old-lighthouse/story.json
    python generate_audio.py stories/the-old-lighthouse/story.json --voice af_sky --speed 1.0
    python generate_audio.py stories/the-old-lighthouse/story.json --chapter ch2 ch3
    python generate_audio.py stories/the-old-lighthouse/story.json --dry-run
    STORY_TTS_API_KEY=abc123 python generate_audio.py stories/the-old-lighthouse/story.json
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
except ImportError:
    print("ERROR: 'requests' is not installed. Run: pip install requests", file=sys.stderr)
    sys.exit(1)

DEFAULT_URL      = "https://elvinio--kokoro-tts-fastapi-app.modal.run/tts"
DEFAULT_VOICE    = "af_heart"
DEFAULT_VOICE_ZH = "zf_xiaobei"
DEFAULT_SPEED    = 0.9
DEFAULT_FMT   = "opus"
MAX_RETRIES   = 3
RETRY_DELAYS  = [2, 5, 10]

# Unicode subscript digits (₀–₉) → ASCII digits
_SUBSCRIPT = str.maketrans('₀₁₂₃₄₅₆₇₈₉', '0123456789')

# Chemical formula pattern — matches after subscript normalisation:
#   • Two or more element groups: NO, NO2, NH3, NO3-, DNA, etc.
#   • Single element + number: O2, N2, O3
# Negative lookbehind/ahead for lowercase letters prevents mid-word matches.
_CHEM_RE = re.compile(
    r'(?<![a-z])(?:[A-Z][a-z]?\d*){2,}[+\-]?(?![a-zA-Z])'
    r'|(?<![a-z])[A-Z]\d+[+\-]?(?![a-zA-Z])'
)


def _expand_chem(m: re.Match) -> str:
    """Space-separate element symbols and numbers so TTS reads them letter-by-letter."""
    parts = []
    s = m.group()
    i = 0
    while i < len(s):
        ch = s[i]
        if ch.isupper():
            if i + 1 < len(s) and s[i + 1].islower():
                parts.append(s[i:i + 2])
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
        elif ch == '-':
            parts.append('minus')
            i += 1
        elif ch == '+':
            parts.append('plus')
            i += 1
        else:
            parts.append(ch)
            i += 1
    return ' '.join(parts)


def normalize_tts_text(text: str) -> str:
    """Expand Unicode subscripts/superscripts and chemical notation for TTS.

    Converts e.g. "NO₂" → "N O 2", "NO₃⁻" → "N O 3 minus", "N₂" → "N 2".
    """
    text = text.translate(_SUBSCRIPT)
    text = text.replace('⁻', '-').replace('⁺', '+')
    for sup, asc in zip('⁰¹²³⁴⁵⁶⁷⁸⁹', '0123456789'):
        text = text.replace(sup, asc)
    return _CHEM_RE.sub(_expand_chem, text)


def _english_text(node: dict) -> str:
    """Extract the English narration text for a node (paragraph/diagram/callout/list)."""
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
            _words = ["One","Two","Three","Four","Five","Six","Seven","Eight",
                      "Nine","Ten","Eleven","Twelve","Thirteen","Fourteen",
                      "Fifteen","Sixteen","Seventeen","Eighteen","Nineteen","Twenty"]
            items = [f"{_words[i] if i < len(_words) else i+1}: {item}"
                     for i, item in enumerate(items)]
        return ". ".join(items)
    return ""


def _chinese_text(node: dict) -> str:
    """Join the characters of a node's `zh` token array into a TTS string."""
    return "".join(tok[0] for tok in node.get("zh", []))


def collect_nodes(story: dict, args, chapters: list[str] | None = None) -> list[dict]:
    """Return all per-language audio tasks, in chapter order.

    Each node can produce up to two tasks: an English one (from its text) and a
    Chinese one (from its `zh` token array). If *chapters* is given, only nodes
    from those chapter IDs are included.
    """
    fmt = args.format
    tasks = []
    for chapter in story.get("chapters", []):
        chapter_id = chapter["id"]
        if chapters and chapter_id not in chapters:
            continue
        for node in chapter.get("nodes", []):
            # English narration
            en_text = _english_text(node)
            if en_text:
                audio_path = node.get("audio") or f"audio/{chapter_id}-{node['id']}.{fmt}"
                tasks.append({
                    "id":         node["id"],
                    "type":       node["type"],
                    "chapter_id": chapter_id,
                    "audio_path": audio_path,
                    "text":       en_text,
                    "lang":       "en",
                    "voice":      args.voice,
                    "json_field": "audio",
                })
            # Chinese narration (any node carrying a `zh` token array)
            zh_text = _chinese_text(node)
            if zh_text:
                audio_path = node.get("audioZh") or f"audio/{chapter_id}-{node['id']}.zh.{fmt}"
                tasks.append({
                    "id":         node["id"],
                    "type":       node["type"],
                    "chapter_id": chapter_id,
                    "audio_path": audio_path,
                    "text":       zh_text,
                    "lang":       "zh",
                    "voice":      args.voice_zh,
                    "json_field": "audioZh",
                })
    return tasks


def call_tts(text: str, audio_path: Path, voice: str, args, session: requests.Session) -> None:
    """Call the TTS endpoint and write the result to audio_path."""
    payload = {
        "text":   text,
        "voice":  voice,
        "format": args.format,
        "speed":  args.speed,
    }
    headers = {"X-API-Key": args.api_key} if args.api_key else {}

    for attempt, delay in enumerate(RETRY_DELAYS, start=1):
        try:
            resp = session.post(args.url, json=payload, headers=headers, timeout=60)
            resp.raise_for_status()
            audio_path.parent.mkdir(parents=True, exist_ok=True)
            audio_path.write_bytes(resp.content)
            return
        except requests.exceptions.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else "?"
            if code == 401:
                raise RuntimeError("401 Unauthorized — check your API key") from exc
            if code == 422:
                body = exc.response.text[:200] if exc.response is not None else ""
                raise RuntimeError(f"422 Unprocessable — payload rejected: {body}") from exc
            if attempt == len(RETRY_DELAYS):
                raise RuntimeError(f"HTTP {code} after {MAX_RETRIES} attempts") from exc
        except requests.exceptions.RequestException as exc:
            if attempt == len(RETRY_DELAYS):
                raise RuntimeError(f"Network error after {MAX_RETRIES} attempts: {exc}") from exc
        print(f"    ↻ attempt {attempt} failed, retrying in {delay}s…", file=sys.stderr)
        time.sleep(delay)


def process_node(node: dict, story_dir: Path, args, session: requests.Session) -> tuple[str, str, str]:
    """
    Generate audio for one node.
    Returns (node_id, status, message) where status is 'ok' | 'skip' | 'error'.
    """
    audio_path = story_dir / node["audio_path"]

    # Ensure extension matches requested format
    if audio_path.suffix.lstrip(".").lower() != args.format:
        audio_path = audio_path.with_suffix("." + args.format)

    # Chemical/subscript normalisation only applies to English narration.
    tts_text = normalize_tts_text(node["text"]) if node["lang"] == "en" else node["text"]
    tag = node["lang"]
    label = f"[{node['chapter_id']}/{node['id']}·{tag}] {tts_text[:50]}{'…' if len(tts_text) > 50 else ''}"

    if not args.force and audio_path.exists():
        return node["id"], "skip", f"skip   {label}"

    if args.dry_run:
        return node["id"], "ok", f"dry-run {label}  →  {audio_path.relative_to(story_dir)}"

    try:
        call_tts(tts_text, audio_path, node["voice"], args, session)
        rel = audio_path.relative_to(story_dir)
        size_kb = audio_path.stat().st_size // 1024
        return node["id"], "ok", f"ok     {label}  →  {rel} ({size_kb} KB)"
    except RuntimeError as exc:
        return node["id"], "error", f"ERROR  {label}  →  {exc}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate TTS audio for story nodes (paragraph, diagram, callout, list) in a Story Reader story.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("story_json", help="Path to story.json")
    parser.add_argument("--api-key",  default=os.getenv("STORY_TTS_API_KEY"),
                        help="TTS API key (env: STORY_TTS_API_KEY)")
    parser.add_argument("--url",      default=DEFAULT_URL,  help=f"TTS endpoint URL (default: {DEFAULT_URL})")
    parser.add_argument("--voice",    default=DEFAULT_VOICE, help=f"Kokoro voice for English text (default: {DEFAULT_VOICE})")
    parser.add_argument("--voice-zh", dest="voice_zh", default=DEFAULT_VOICE_ZH,
                        help=f"Kokoro voice for Chinese text (default: {DEFAULT_VOICE_ZH})")
    parser.add_argument("--speed",    type=float, default=DEFAULT_SPEED,
                        help=f"Speech speed 0.5–2.0 (default: {DEFAULT_SPEED})")
    parser.add_argument("--format",   default=DEFAULT_FMT, choices=["opus", "mp3"],
                        help=f"Output audio format (default: {DEFAULT_FMT})")
    parser.add_argument("--chapter",  nargs="+", metavar="CHAPTER_ID",
                        help="Only generate audio for these chapter IDs (default: all chapters)")
    parser.add_argument("--force",    action="store_true", help="Overwrite existing audio files")
    parser.add_argument("--dry-run",  action="store_true", help="Show plan without calling the API")
    parser.add_argument("--workers",  type=int, default=3,
                        help="Parallel workers (default: 3, set to 1 to disable)")
    args = parser.parse_args()

    # Validate story.json
    story_path = Path(args.story_json).resolve()
    if not story_path.exists():
        print(f"ERROR: story.json not found: {story_path}", file=sys.stderr)
        sys.exit(1)

    with story_path.open(encoding="utf-8") as f:
        story = json.load(f)

    story_dir = story_path.parent
    title = story.get("meta", {}).get("title", story_path.parent.name)

    # Validate --chapter IDs if provided
    if args.chapter:
        known = {ch["id"] for ch in story.get("chapters", [])}
        bad = [c for c in args.chapter if c not in known]
        if bad:
            print(f"ERROR: Unknown chapter ID(s): {', '.join(bad)}", file=sys.stderr)
            print(f"       Available: {', '.join(sorted(known))}", file=sys.stderr)
            sys.exit(1)

    nodes = collect_nodes(story, args, chapters=args.chapter)
    if not nodes:
        print("No audio nodes found in story.json (no narratable text or `zh` tokens).")
        sys.exit(0)

    en_count = sum(1 for n in nodes if n["lang"] == "en")
    zh_count = sum(1 for n in nodes if n["lang"] == "zh")

    print(f"\nStory:   {title}")
    if args.chapter:
        print(f"Chapters: {', '.join(args.chapter)}")
    print(f"Tasks:   {len(nodes)} audio clips ({en_count} EN, {zh_count} ZH)")
    print(f"Voice:   EN={args.voice}  ZH={args.voice_zh}  speed={args.speed}  format={args.format}")
    print(f"Output:  {story_dir / 'audio'}/")
    if args.force:
        print("Mode:    FORCE (overwriting existing files)")
    elif args.dry_run:
        print("Mode:    DRY RUN")
    print()

    if not args.dry_run and not args.api_key:
        print("ERROR: No API key provided. Set STORY_TTS_API_KEY env var or use --api-key.", file=sys.stderr)
        sys.exit(1)

    ok_count = skip_count = error_count = 0

    with requests.Session() as session:
        if args.workers == 1:
            # Sequential — easier to read logs in order
            for i, node in enumerate(nodes, 1):
                print(f"[{i:>2}/{len(nodes)}] ", end="", flush=True)
                _, status, msg = process_node(node, story_dir, args, session)
                print(msg)
                if status == "ok":    ok_count    += 1
                elif status == "skip": skip_count  += 1
                else:                  error_count += 1
        else:
            # Parallel
            futures = {}
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                for node in nodes:
                    fut = pool.submit(process_node, node, story_dir, args, session)
                    futures[fut] = node["id"]

                completed = 0
                for fut in as_completed(futures):
                    completed += 1
                    _, status, msg = fut.result()
                    print(f"[{completed:>2}/{len(nodes)}] {msg}")
                    if status == "ok":    ok_count    += 1
                    elif status == "skip": skip_count  += 1
                    else:                  error_count += 1

    # Write audio paths back into story.json for any fields that weren't set.
    if not args.dry_run:
        # key by (chapter_id, node_id, json_field) — node IDs can repeat across chapters
        path_map = {(n["chapter_id"], n["id"], n["json_field"]): n["audio_path"] for n in nodes}
        changed = False
        for chapter in story.get("chapters", []):
            for node in chapter.get("nodes", []):
                for field in ("audio", "audioZh"):
                    key = (chapter["id"], node["id"], field)
                    if key in path_map and not node.get(field):
                        node[field] = path_map[key]
                        changed = True
        if changed:
            with story_path.open("w", encoding="utf-8") as f:
                json.dump(story, f, indent=2, ensure_ascii=False)
                f.write("\n")
            print(f"Updated {story_path.name} with audio paths.")

    # Summary
    print()
    parts = []
    if ok_count:    parts.append(f"{ok_count} generated")
    if skip_count:  parts.append(f"{skip_count} skipped (already exist)")
    if error_count: parts.append(f"{error_count} FAILED")
    print("Done: " + ", ".join(parts) + ".")

    if error_count:
        print("\nSome files failed. Re-run with --force to retry them, or check the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
