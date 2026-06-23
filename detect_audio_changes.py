#!/usr/bin/env python3
"""
Compare a story.json against its previous git commit to find chapters
whose narrated text changed and therefore need audio regeneration.

Outputs a space-separated list of chapter IDs (empty string if none).

Usage:
    python detect_audio_changes.py stories/<id>/story.json [--base COMMIT]
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path


def narrated_text(node: dict) -> str:
    t = node.get("type", "")
    if t == "paragraph":
        return node.get("text", "")
    if t == "diagram":
        return node.get("caption", "")
    if t == "callout":
        label = node.get("label", "")
        body = node.get("text", "")
        return f"{label}. {body}" if label else body
    if t == "list":
        items = node.get("items", [])
        if node.get("ordered"):
            words = ["One", "Two", "Three", "Four", "Five", "Six", "Seven",
                     "Eight", "Nine", "Ten"]
            return ". ".join(
                f"{words[i]}: {item}" if i < len(words) else item
                for i, item in enumerate(items)
            )
        return ". ".join(items)
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("story_json", help="Path to story.json")
    parser.add_argument(
        "--base",
        default="HEAD~1",
        help="Git ref to compare against (default: HEAD~1)",
    )
    args = parser.parse_args()

    story_path = args.story_json

    # Fetch previous version from git
    result = subprocess.run(
        ["git", "show", f"{args.base}:{story_path}"],
        capture_output=True,
        text=True,
    )

    new_story = json.loads(Path(story_path).read_text())

    if result.returncode != 0:
        # File is new — all chapters need audio
        chapter_ids = [ch["id"] for ch in new_story.get("chapters", [])]
        print(" ".join(chapter_ids))
        return

    old_story = json.loads(result.stdout)

    # Index old nodes by (chapter_id, node_id)
    old_nodes: dict[tuple[str, str], dict] = {}
    for ch in old_story.get("chapters", []):
        for node in ch.get("nodes", []):
            old_nodes[(ch["id"], node["id"])] = node

    changed: set[str] = set()
    for ch in new_story.get("chapters", []):
        ch_id = ch["id"]
        for node in ch.get("nodes", []):
            new_text = narrated_text(node)
            if not new_text:
                continue
            key = (ch_id, node["id"])
            old_text = narrated_text(old_nodes[key]) if key in old_nodes else None
            if old_text != new_text:
                changed.add(ch_id)

    print(" ".join(sorted(changed)))


if __name__ == "__main__":
    main()
