# CLAUDE.md

Guidance for working in this repository.

## What this is

A **static, dependency-free HTML story reader** for children. There is no build
step, no framework, and no server-side code — just hand-written HTML, CSS, and
ES modules that run directly in the browser. Stories are plain JSON files with
per-paragraph audio narration.

Because the app `fetch`es JSON, SVG, and audio at runtime, it **must be served
over HTTP** — opening `index.html` as a `file://` URL will fail (CORS/fetch).

```bash
python3 -m http.server 8080   # then open http://localhost:8080
# or: npx serve .
```

## Page flow

Two HTML pages, each loading the same settings dialog markup:

- **`index.html`** — the library. Loads `js/library.js`, which fetches
  `stories/index.json` and renders one card per story. Each card links to
  `reader.html?story=<id>`.
- **`reader.html`** — the reader. Loads `js/reader.js`, which reads the `?story=`
  query param, fetches `stories/<id>/story.json`, renders the nodes, wires up the
  audio bar, and restores the saved scroll position.

## Directory layout

```
index.html              Library page
reader.html             Reader page
css/
  base.css              Shared variables, settings dialog, base typography
  library.css           Library grid + cards
  reader.css            Reader layout, nodes, audio bar, TOC
js/
  library.js            Builds the library grid from stories/index.json
  reader.js             Renders a story, owns page wiring (entry point)
  audio-player.js       AudioPlayer class: queue + playback + format fallback
  scroll-tracker.js     ScrollTracker class: saves/restores reading position
  settings.js           SettingsManager: reading prefs -> CSS variables
stories/
  index.json            Library manifest — EVERY story must be listed here
  <story-id>/
    story.json          Story content + structure
    assets/cover.svg    Cover art (referenced by index.json + story.json meta)
    audio/              One audio file per narrated node
    diagrams/           Interactive SVGs referenced by diagram nodes
generate_audio.py       TTS narration generator (Kokoro endpoint)
story-format-prompt.md  Prompt for asking an AI to author a new story.json
README.md               User-facing overview
```

## How a story is defined

### `stories/index.json` (the manifest)

An array of cards. A story does **not** appear in the library until it is listed
here, even if its folder exists. Each entry:

```json
{
  "id": "the-old-lighthouse",
  "title": "The Old Lighthouse",
  "author": "Mira Chen",
  "coverImage": "stories/<id>/assets/cover.svg",
  "ageRange": "7–10",
  "estimatedMinutes": 5,
  "tags": ["adventure", "sea", "courage"]
}
```

Note: in `index.json`, `coverImage` is relative to the **site root**
(`stories/<id>/...`), whereas inside a story's own `story.json` the `coverImage`
is relative to the **story folder** (`assets/cover.svg`). A missing cover image
degrades gracefully — `library.js` hides a broken `<img>` via `onerror`.

### `stories/<id>/story.json` (the content)

```
{ id, version, meta: { title, subtitle, author, coverImage, ageRange,
                       wordCount, estimatedMinutes, tags },
  chapters: [ { id, title, nodes: [ ...nodes ] } ] }
```

`version` matters: the saved reading position stores the version it was written
against, and `scroll-tracker.js` discards a saved position when the story's
version no longer matches. Bump `version` when node IDs change.

### Node types

`reader.js` (`renderNode`) currently renders **two** node types:

- **`paragraph`** — `{ type, id, text, audio }`. Rendered as a `<p>`.
- **`diagram`** — `{ type, id, caption, altText, svgFile, audio }`. The SVG is
  fetched and inlined (see "Interactive diagrams" below); `caption` becomes the
  `<figcaption>` and supplies the audio-bar preview text.

Any node with an `audio` field also gets a ▶ "play from here" button.

> **Gotcha:** `stories/the-shy-gas-a-nitrogen-story/story.json` also uses
> `callout` and `list` node types. **`reader.js` does not render these yet** —
> they currently produce empty `<section>` elements. If you want them to display,
> add `else if (node.type === 'callout')` / `'list'` branches to `renderNode` in
> `js/reader.js` (and matching styles in `css/reader.css`). The
> `generate_audio.py` collector also only produces audio for `paragraph` and
> `diagram` text, so callouts/lists are silent by design.

### Interactive diagrams

`loadInlineSVG` in `reader.js` fetches the SVG and inlines it into the DOM so its
internal `<script>` (click handlers, etc.) can run. Scripts are extracted and
re-appended to `document.body` *after* the SVG is in the page, because inline SVG
`<script>` does not auto-execute when inserted via DOMParser. Keep diagram SVGs
self-contained and trusted — their scripts run in the page context.

## Audio narration

`audio-player.js` owns playback. `reader.js` builds an ordered queue of
`{ id, audioSrc, text }` (one per node that has an `audio` path) and hands it to
`AudioPlayer.loadQueue`. Playback flows node-to-node automatically via the
`ended` event; when the queue ends it dispatches `audioplayer:storycomplete`.

Communication with the UI is via DOM `CustomEvent`s dispatched on `document`:
`audioplayer:nodestart`, `:playerstate`, `:progress`, `:storycomplete`.
`reader.js#setupAudioBar` listens for these to highlight the narrating node,
auto-scroll, update the progress bar, and toggle play/pause.

**Format fallback:** audio is authored as **Opus** (`.opus`). `resolveSrc`
probes `canPlayType` and, if the browser can't play the listed extension, swaps
to the first supported alternative (`opus` → `ogg` → `mp3`). To support older
browsers, generate an `.mp3` alongside each `.opus`.

### Generating audio: `generate_audio.py`

Calls a Kokoro TTS endpoint to produce one audio file per `paragraph`/`diagram`
node and (if missing) writes the `audio` paths back into `story.json`.

```bash
STORY_TTS_API_KEY=... python generate_audio.py stories/<id>/story.json
python generate_audio.py stories/<id>/story.json --dry-run   # plan only
python generate_audio.py stories/<id>/story.json --force      # overwrite
```

Naming convention it expects/creates: `audio/<chapter-id>-<node-id>.<fmt>`.
(The nitrogen story's files are doubled, e.g. `audio/ch1-ch1-p1.opus`, because
its node IDs already include the chapter prefix — match whatever the
`story.json` `audio` field actually says.)

## Reading settings & persistence (localStorage)

`settings.js` (`SettingsManager`) maps reading preferences onto CSS custom
properties on `<html>` (`--reader-font-size`, `--reader-font-family`,
`--reader-line-height`, `--reader-paragraph-gap`, and `--reader-bg` /
`--reader-text` derived from a "warmth" slider). It auto-mounts the settings
dialog on whichever page includes `#settings-panel`.

`scroll-tracker.js` (`ScrollTracker`) uses an `IntersectionObserver` to record
the topmost visible node, debounced by 500ms, and restores it on the next visit
(scrolling it into view and flagging it as the resume point).

| localStorage key | Contents |
|---|---|
| `story-reader:settings` | Font size, family, warmth, line height, paragraph gap |
| `story-reader:position:<story-id>` | `{ nodeId, chapterId, savedAt, storyVersion }` |

## Adding a new story (checklist)

1. Create `stories/<id>/` with `story.json` (see `story-format-prompt.md` for an
   AI-authoring prompt, or copy an existing story).
2. Add `stories/<id>/assets/cover.svg` (240×320 viewBox matches existing covers).
3. Generate narration: `python generate_audio.py stories/<id>/story.json`.
4. **Add an entry to `stories/index.json`** — otherwise the story is invisible.
5. Serve over HTTP and verify in the browser (cards, playback, resume).

## Conventions

- No dependencies, no build, no transpile. Keep it that way unless asked.
- Plain ES modules with `import`/`export`; `js/reader.js` is the reader entry point.
- Fail soft on missing assets (covers, audio) rather than throwing — match the
  existing `try/catch` + `onerror` patterns.
- Use the four standard reader CSS variables for any new node styling so user
  settings continue to apply.
