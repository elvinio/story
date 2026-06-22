# Story Library

A static HTML story reader for primary school children (ages 7–10).

## Features

- **Paragraph-level audio narration** — click ▶ on any paragraph to start reading from that point; playback continues through the rest of the story automatically
- **Interactive diagrams** — SVG diagrams with clickable areas and descriptions, embedded inline in the story
- **Sepia reading theme** — warm background, serif fonts, comfortable line height by default
- **Reading settings** — adjust font size, font family, background warmth, line height, and paragraph spacing; all settings are saved automatically
- **Reading position memory** — scroll position is saved per story; returning to a story restores where you left off
- **Playback speed** — 0.75×, 1×, 1.25×, 1.5× via the audio bar

## Running locally

The app fetches JSON and SVG files, so it must be served over HTTP (not opened as a `file://` URL).

```bash
# Python 3
python3 -m http.server 8080

# Node.js
npx serve .
```

Then open `http://localhost:8080` in a browser.

## Story format

Each story lives in its own folder under `stories/`:

```
stories/
├── index.json                   ← library manifest (all stories listed here)
└── my-story/
    ├── story.json               ← story content and structure
    ├── assets/cover.svg         ← cover image (SVG or JPG)
    ├── audio/
    │   ├── ch1-p1.mp3           ← one MP3 per paragraph node
    │   └── ...
    └── diagrams/
        └── my-diagram.svg       ← interactive SVG diagrams
```

### story.json schema

```json
{
  "id": "my-story",
  "version": 1,
  "meta": { "title": "...", "author": "...", "ageRange": "7-10", "estimatedMinutes": 5 },
  "chapters": [
    {
      "id": "ch1",
      "title": "Chapter Title",
      "nodes": [
        {
          "type": "paragraph",
          "id": "p1",
          "text": "Once upon a time...",
          "audio": "audio/ch1-p1.mp3"
        },
        {
          "type": "diagram",
          "id": "d1",
          "caption": "Caption text",
          "altText": "Description for screen readers",
          "svgFile": "diagrams/my-diagram.svg",
          "audio": "audio/ch1-d1-caption.mp3"
        }
      ]
    }
  ]
}
```

Nodes without an `audio` field are rendered but skipped silently by the audio player.

### Adding audio narration

Record one MP3 per paragraph node (or use a text-to-speech service) and save to the story's `audio/` folder. The path in `story.json` is relative to the story folder.

### Adding a new story

1. Create `stories/my-story/` with `story.json`, `assets/`, `audio/`, `diagrams/`
2. Add an entry to `stories/index.json`

## localStorage keys

| Key | Contents |
|-----|----------|
| `story-reader:settings` | Font size, font family, warmth, line height, paragraph spacing |
| `story-reader:position:<story-id>` | Last-read node ID and chapter, with story version |
