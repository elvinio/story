#!/usr/bin/env python3
"""
Generate audio narration for a Story Reader story using a Kokoro TTS endpoint.

Generates audio for paragraph, diagram, callout, and list nodes.
Callout text is spoken as "label. body". List items are joined with ". ".

Usage:
    python generate_audio.py stories/my-story/story.json

Environment variables:
    STORY_TTS_API_KEY   API key for the TTS endpoint

Options:
    --api-key KEY        API key (overrides env var)
    --url URL            TTS endpoint URL (default: https://elvinio--kokoro-tts-fastapi-app.modal.run/tts)
    --voice VOICE        Kokoro voice (default: af_heart)
    --speed FLOAT        Speech speed, 0.5–2.0 (default: 0.9)
    --format FORMAT      Audio format: opus or mp3 (default: opus)
    --force              Overwrite existing audio files
    --dry-run            Print what would be generated without calling the API
    --workers N          Parallel workers (default: 3)

Examples:
    python generate_audio.py stories/the-old-lighthouse/story.json
    python generate_audio.py stories/the-old-lighthouse/story.json --voice af_sky --speed 1.0
    python generate_audio.py stories/the-old-lighthouse/story.json --dry-run
    STORY_TTS_API_KEY=abc123 python generate_audio.py stories/the-old-lighthouse/story.json
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
except ImportError:
    print("ERROR: 'requests' is not installed. Run: pip install requests", file=sys.stderr)
    sys.exit(1)

DEFAULT_URL   = "https://elvinio--kokoro-tts-fastapi-app.modal.run/tts"
DEFAULT_VOICE = "af_heart"
DEFAULT_SPEED = 0.9
DEFAULT_FMT   = "opus"
MAX_RETRIES   = 3
RETRY_DELAYS  = [2, 5, 10]


def collect_nodes(story: dict, fmt: str) -> list[dict]:
    """Return all nodes that need audio, in chapter order."""
    nodes = []
    for chapter in story.get("chapters", []):
        chapter_id = chapter["id"]
        for node in chapter.get("nodes", []):
            text = ""
            if node["type"] == "paragraph":
                text = node.get("text", "").strip()
            elif node["type"] == "diagram":
                text = node.get("caption", "").strip()
            elif node["type"] == "callout":
                label = node.get("label", "").strip()
                body  = node.get("text", "").strip()
                text  = (label + ". " + body) if label and body else (label or body)
            elif node["type"] == "list":
                items = [i.strip() for i in node.get("items", []) if i.strip()]
                text  = ". ".join(items)
            if not text:
                continue
            # Use existing audio path or derive one from chapter/node IDs
            audio_path = node.get("audio") or f"audio/{chapter_id}-{node['id']}.{fmt}"
            nodes.append({
                "id":         node["id"],
                "type":       node["type"],
                "chapter_id": chapter_id,
                "audio_path": audio_path,
                "text":       text,
            })
    return nodes


def call_tts(text: str, audio_path: Path, args, session: requests.Session) -> None:
    """Call the TTS endpoint and write the result to audio_path."""
    payload = {
        "text":   text,
        "voice":  args.voice,
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

    label = f"[{node['chapter_id']}/{node['id']}] {node['text'][:55]}{'…' if len(node['text']) > 55 else ''}"

    if not args.force and audio_path.exists():
        return node["id"], "skip", f"skip   {label}"

    if args.dry_run:
        return node["id"], "ok", f"dry-run {label}  →  {audio_path.relative_to(story_dir)}"

    try:
        call_tts(node["text"], audio_path, args, session)
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
    parser.add_argument("--voice",    default=DEFAULT_VOICE, help=f"Kokoro voice (default: {DEFAULT_VOICE})")
    parser.add_argument("--speed",    type=float, default=DEFAULT_SPEED,
                        help=f"Speech speed 0.5–2.0 (default: {DEFAULT_SPEED})")
    parser.add_argument("--format",   default=DEFAULT_FMT, choices=["opus", "mp3"],
                        help=f"Output audio format (default: {DEFAULT_FMT})")
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

    nodes = collect_nodes(story, args.format)
    if not nodes:
        print("No audio nodes found in story.json (no paragraph, diagram, callout, or list nodes with text).")
        sys.exit(0)

    print(f"\nStory:   {title}")
    print(f"Nodes:   {len(nodes)} audio nodes to process")
    print(f"Voice:   {args.voice}  speed={args.speed}  format={args.format}")
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

    # Write audio paths back into story.json for any nodes that didn't have them
    if not args.dry_run:
        node_audio_map = {n["id"]: n["audio_path"] for n in nodes}
        changed = False
        for chapter in story.get("chapters", []):
            for node in chapter.get("nodes", []):
                if node["id"] in node_audio_map and not node.get("audio"):
                    node["audio"] = node_audio_map[node["id"]]
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
