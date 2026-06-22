# Story Format Prompt

Use this document to ask an AI model to write a story for the Story Reader app.
Paste it into your conversation, then describe the story you want.

---

## Your task

Write a children's story in the JSON format described below.
The story is for the **Story Reader app**, which displays it to primary school children aged 7–10.

---

## JSON schema

```json
{
  "id": "kebab-case-story-id",
  "version": 1,
  "meta": {
    "title": "Story Title",
    "subtitle": "Optional subtitle",
    "author": "Author Name",
    "coverImage": "assets/cover.svg",
    "ageRange": "7-10",
    "wordCount": 0,
    "estimatedMinutes": 5,
    "tags": ["adventure", "animals"]
  },
  "chapters": [
    {
      "id": "ch1",
      "title": "Chapter Title",
      "nodes": [
        {
          "type": "paragraph",
          "id": "p1",
          "text": "The paragraph text goes here.",
          "audio": "audio/ch1-p1.opus"
        },
        {
          "type": "diagram",
          "id": "d1",
          "caption": "Caption shown below the diagram",
          "altText": "Description of the diagram for screen readers",
          "svgFile": "diagrams/my-diagram.svg",
          "audio": "audio/ch1-d1.opus"
        }
      ]
    }
  ]
}
```

---

## Rules

### IDs
- `id` at the top level: a lowercase kebab-case slug, e.g. `the-old-lighthouse`
- Every `chapter` must have a unique `id` like `ch1`, `ch2`, `ch3`
- Every `node` must have a unique `id` within the whole story
  - Paragraphs: `p1`, `p2`, `p3` … (sequential across all chapters)
  - Diagrams: `d1`, `d2` …
- Audio paths follow the pattern `audio/<chapter-id>-<node-id>.opus`
  - Example: chapter `ch2`, paragraph `p5` → `audio/ch2-p5.opus`
  - Diagram caption audio: `audio/ch1-d1.opus`

### Node types

**`paragraph`** — a block of text read aloud:
```json
{
  "type": "paragraph",
  "id": "p1",
  "text": "Full paragraph text here. Can be multiple sentences.",
  "audio": "audio/ch1-p1.opus"
}
```

**`diagram`** — an illustration or interactive graphic (you describe it; the SVG is created separately):
```json
{
  "type": "diagram",
  "id": "d1",
  "caption": "Short caption shown under the diagram",
  "altText": "Detailed description for screen readers — describe what is shown as if explaining to someone who cannot see it",
  "svgFile": "diagrams/diagram-id.svg",
  "audio": "audio/ch1-d1.opus"
}
```

### `version`
Always set to `1` for a new story. Increment when you revise a story that has already been distributed.

### `wordCount` and `estimatedMinutes`
Count the words in all paragraph `text` fields. Estimate 100 words per minute for a child reading at a comfortable pace, then round up.

---

## Writing guidelines

**Audience:** Primary school children, ages 7–10. Write as you would for a capable young reader who enjoys stories.

**Paragraphs:**
- Each `paragraph` node is one paragraph — typically 2–4 sentences
- Keep each paragraph to 40–80 words
- Short sentences are better than long ones for this age group
- Avoid jargon; if you use a new word, let context explain it

**Chapters:**
- 3–5 chapters per story is ideal
- Each chapter should have a clear mini-arc: something happens, changes, or is discovered
- A good chapter count of nodes: 3–6 paragraphs, optionally 1 diagram

**Diagrams:**
- Use a `diagram` node when something visual would help: a map, a cross-section, a labelled object, a timeline
- The caption should be one short sentence
- The `altText` should describe the diagram fully — it will be read by screen readers and used by a human to draw the SVG

**Tone:**
- Engaging, curious, warm
- Use action and dialogue to move the story forward
- Avoid scary themes; mild jeopardy is fine (storms, getting lost, a challenge to overcome)
- End on a positive, resolved note

---

## Output instructions

1. Output **only the JSON** — no preamble, no explanation, no markdown code fences
2. Validate: every `id` is unique, every `audio` path follows the naming convention, `wordCount` is accurate
3. Set `"coverImage": "assets/cover.svg"` (the cover art is created separately)
4. For diagram nodes, set `"svgFile": "diagrams/<diagram-id>.svg"` where `<diagram-id>` is a descriptive kebab-case name

---

## Example (abbreviated — two chapters, four nodes)

```json
{
  "id": "the-lost-kite",
  "version": 1,
  "meta": {
    "title": "The Lost Kite",
    "subtitle": "A windy day adventure",
    "author": "Your Name",
    "coverImage": "assets/cover.svg",
    "ageRange": "7-10",
    "wordCount": 320,
    "estimatedMinutes": 4,
    "tags": ["adventure", "friendship", "outdoors"]
  },
  "chapters": [
    {
      "id": "ch1",
      "title": "Up and Away",
      "nodes": [
        {
          "type": "paragraph",
          "id": "p1",
          "text": "Mia had waited all week for a windy day. When Saturday finally came, she grabbed her red kite and ran to the top of Barley Hill as fast as her legs would carry her.",
          "audio": "audio/ch1-p1.opus"
        },
        {
          "type": "diagram",
          "id": "d1",
          "caption": "The parts of a kite",
          "altText": "A labelled diagram showing the main parts of a diamond kite: the spine (vertical stick), the spreader (horizontal stick), the sail (the fabric), the bridle (the strings from the kite to the flying line), and the tail.",
          "svgFile": "diagrams/kite-parts.svg",
          "audio": "audio/ch1-d1.opus"
        },
        {
          "type": "paragraph",
          "id": "p2",
          "text": "The wind caught the kite at once, pulling the string tight. Mia let out more line, hand over hand, until the kite was just a red dot high above the green fields.",
          "audio": "audio/ch1-p2.opus"
        }
      ]
    },
    {
      "id": "ch2",
      "title": "Gone!",
      "nodes": [
        {
          "type": "paragraph",
          "id": "p3",
          "text": "Then the string snapped. Mia stared as the kite tumbled and spun and disappeared behind the tall oak trees at the far end of the field. She took a deep breath. She was going to find it.",
          "audio": "audio/ch2-p3.opus"
        }
      ]
    }
  ]
}
```
