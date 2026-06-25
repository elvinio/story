import { AudioPlayer } from './audio-player.js';
import { ScrollTracker } from './scroll-tracker.js';

const params = new URLSearchParams(location.search);
const storyId = params.get('story');

if (!storyId) {
  location.href = 'index.html';
}

let player = null;
let tracker = null;

// Bilingual state ----------------------------------------------------------
let storyMeta = null;
let queueEn = [];
let queueZh = [];
let currentLang = 'en';   // 'en' | 'zh'

const LANG_KEY   = 'story-reader:lang';
const PINYIN_KEY = 'story-reader:pinyin';

// Character + pinyin rendering (ported from the Chinese stories repo) -------
const PUNCT_RE   = /^[，。！？、：；…—“”‘’「」『』【】〔〕·～\-–—]+$/;
// Closing punctuation must not start a line — attach to the preceding token.
const CLOSING_RE = /^[，。！？、：；”’」』】〕…—]+$/;
// Opening punctuation must not end a line — attach to the following token.
const OPENING_RE = /^[“‘「『【〔]+$/;

function makeW(ch, py) {
  const w = document.createElement('span');
  w.className = 'w' + (PUNCT_RE.test(ch) ? ' punct' : '');
  const pyEl = document.createElement('span');
  pyEl.className = 'py';
  pyEl.textContent = py;
  const chEl = document.createElement('span');
  chEl.textContent = ch;
  w.appendChild(pyEl);
  w.appendChild(chEl);
  return w;
}

function appendNoBreak(parent, ...nodes) {
  const g = document.createElement('span');
  g.style.whiteSpace = 'nowrap';
  nodes.forEach(n => g.appendChild(n));
  parent.appendChild(g);
}

// Build a <p class="para-zh"> from an array of [char, pinyin] tokens.
function renderChineseParagraph(tokens) {
  const p = document.createElement('p');
  p.className = 'para-zh';
  let pending = []; // opening punctuation waiting to attach to next char
  for (const [ch, py] of tokens) {
    const w = makeW(ch, py);
    if (CLOSING_RE.test(ch) && p.lastChild) {
      const prev = p.lastChild;
      p.removeChild(prev);
      appendNoBreak(p, prev, w);
    } else if (OPENING_RE.test(ch)) {
      pending.push(w);
    } else if (pending.length) {
      appendNoBreak(p, ...pending, w);
      pending = [];
    } else {
      p.appendChild(w);
    }
  }
  pending.forEach(w => p.appendChild(w)); // flush trailing opening punctuation
  return p;
}

// Plain-text Chinese (no pinyin) for the audio-bar preview.
function zhText(tokens) {
  return tokens.map(t => t[0]).join('');
}

async function init() {
  let story;
  try {
    const resp = await fetch(`stories/${storyId}/story.json`);
    if (!resp.ok) throw new Error('Not found');
    story = await resp.json();
  } catch {
    document.getElementById('story-content').innerHTML =
      '<p style="color:var(--ui-accent);font-style:italic;padding:2rem 0">Story not found. <a href="index.html">Back to library</a></p>';
    return;
  }

  storyMeta = story.meta;
  document.title = story.meta.title + ' — Story Library';
  document.getElementById('story-title').textContent = story.meta.title;

  const content = document.getElementById('story-content');
  content.innerHTML = '';

  const tocNav = document.getElementById('toc-nav');
  const storyBase = `stories/${storyId}/`;
  queueEn = [];
  queueZh = [];
  let hasZh = false;

  for (const chapter of story.chapters) {
    const h2 = document.createElement('h2');
    h2.className = 'chapter-title';
    h2.id = 'chapter-' + chapter.id;
    if (chapter.titleZh) {
      const en = document.createElement('span');
      en.className = 't-en';
      en.textContent = chapter.title;
      const zh = document.createElement('span');
      zh.className = 't-zh';
      zh.textContent = chapter.titleZh;
      h2.append(en, zh);
    } else {
      h2.textContent = chapter.title;
    }
    content.appendChild(h2);

    const tocLink = document.createElement('a');
    tocLink.href = '#chapter-' + chapter.id;
    tocLink.textContent = chapter.title;
    tocLink.addEventListener('click', () => {
      if (window.innerWidth <= 640) {
        document.getElementById('chapter-toc').classList.remove('toc-open');
      }
    });
    tocNav.appendChild(tocLink);

    for (const node of chapter.nodes) {
      if (node.zh) hasZh = true;
      const el = await renderNode(node, storyBase, chapter.id);
      content.appendChild(el);

      if (node.audio) {
        let previewText = '';
        if (node.type === 'paragraph') previewText = node.text;
        else if (node.type === 'diagram') previewText = node.caption || '';
        else if (node.type === 'callout') previewText = [node.label, node.text].filter(Boolean).join('. ');
        else if (node.type === 'list') previewText = (node.items || []).join('. ');
        queueEn.push({ id: node.id, audioSrc: storyBase + node.audio, text: previewText });
      }
      if (node.audioZh && node.zh) {
        queueZh.push({ id: node.id, audioSrc: storyBase + node.audioZh, text: zhText(node.zh) });
      }
    }
  }

  player = new AudioPlayer();
  setupAudioBar();
  setupLanguageControls(hasZh);

  tracker = new ScrollTracker(storyId, story.version);
  tracker.observe(content);

  const saved = tracker.getSavedPosition();
  if (saved) {
    const el = content.querySelector(`[data-node-id="${CSS.escape(saved.nodeId)}"]`);
    if (el) {
      el.classList.add('is-resume-point');
      setTimeout(() => el.scrollIntoView({ behavior: 'smooth', block: 'center' }), 300);
    }
  }
}

async function renderNode(node, base, chapterId) {
  const wrapper = document.createElement('section');
  wrapper.className = `story-node node-${node.type}`;
  wrapper.dataset.nodeId = node.id;
  wrapper.dataset.chapterId = chapterId;

  if (node.type === 'paragraph') {
    const p = document.createElement('p');
    p.className = 'para-en';
    p.textContent = node.text;
    wrapper.appendChild(p);

    if (node.zh) {
      wrapper.appendChild(renderChineseParagraph(node.zh));
    }

  } else if (node.type === 'diagram') {
    const fig = document.createElement('figure');

    if (node.svgFile) {
      const svgWrapper = document.createElement('div');
      svgWrapper.className = 'diagram-svg-wrapper';
      await loadInlineSVG(base + node.svgFile, svgWrapper);
      fig.appendChild(svgWrapper);
    }

    if (node.caption) {
      const cap = document.createElement('figcaption');
      cap.textContent = node.caption;
      fig.appendChild(cap);
    }

    if (node.altText) {
      fig.setAttribute('aria-label', node.altText);
    }

    wrapper.appendChild(fig);

  } else if (node.type === 'callout') {
    const aside = document.createElement('aside');
    aside.className = 'callout-box';

    if (node.label) {
      const label = document.createElement('p');
      label.className = 'callout-label';
      label.textContent = node.label;
      aside.appendChild(label);
    }

    if (node.text) {
      const p = document.createElement('p');
      p.className = 'callout-text';
      p.textContent = node.text;
      aside.appendChild(p);
    }

    wrapper.appendChild(aside);

  } else if (node.type === 'list') {
    const list = document.createElement(node.ordered ? 'ol' : 'ul');
    list.className = 'story-list';
    for (const item of node.items || []) {
      const li = document.createElement('li');
      li.textContent = item;
      list.appendChild(li);
    }
    wrapper.appendChild(list);
  }

  if (node.audio || node.audioZh) {
    const btn = document.createElement('button');
    btn.className = 'play-from-here';
    btn.setAttribute('aria-label', 'Play from here');
    btn.innerHTML = '&#9654;';
    btn.addEventListener('click', () => {
      player?.playFrom(node.id);
      document.getElementById('audio-bar').removeAttribute('hidden');
      document.body.classList.add('audio-active');
    });
    wrapper.appendChild(btn);
  }

  return wrapper;
}

async function loadInlineSVG(url, container) {
  try {
    const resp = await fetch(url);
    if (!resp.ok) return;
    const text = await resp.text();
    const parser = new DOMParser();
    const doc = parser.parseFromString(text, 'image/svg+xml');

    const parseError = doc.querySelector('parsererror');
    if (parseError) return;

    // Extract and defer script execution until after SVG is in the DOM
    const scripts = [...doc.querySelectorAll('script')];
    const scriptContents = scripts.map(s => s.textContent);
    scripts.forEach(s => s.remove());

    const svg = doc.documentElement;

    // Safari requires explicit width/height attributes to compute the intrinsic
    // aspect ratio used by height:auto — derive them from viewBox if absent
    if (!svg.hasAttribute('width') || !svg.hasAttribute('height')) {
      const vb = svg.getAttribute('viewBox');
      if (vb) {
        const parts = vb.trim().split(/[\s,]+/);
        if (parts.length === 4) {
          if (!svg.hasAttribute('width'))  svg.setAttribute('width',  parts[2]);
          if (!svg.hasAttribute('height')) svg.setAttribute('height', parts[3]);
        }
      }
    }

    // adoptNode moves the element into this document before insertion (required
    // when appending nodes parsed by DOMParser into a different document)
    container.appendChild(document.adoptNode(svg));

    // Execute extracted scripts now that SVG elements are in the page DOM
    scriptContents.forEach(src => {
      const el = document.createElement('script');
      el.textContent = src;
      document.body.appendChild(el);
    });
  } catch {}
}

function setupAudioBar() {
  const bar = document.getElementById('audio-bar');
  const playPauseBtn = document.getElementById('audio-play-pause');
  const prevBtn = document.getElementById('audio-prev');
  const nextBtn = document.getElementById('audio-next');
  const speedSelect = document.getElementById('playback-speed');
  const progressFill = document.getElementById('audio-progress-fill');
  const progressBar = document.getElementById('audio-progress-bar');
  const preview = document.getElementById('audio-node-preview');

  playPauseBtn.addEventListener('click', () => player?.togglePlayPause());
  prevBtn.addEventListener('click', () => player?.prev());
  nextBtn.addEventListener('click', () => player?.next());
  speedSelect.addEventListener('change', () => player?.setSpeed(Number(speedSelect.value)));

  document.addEventListener('audioplayer:nodestart', ({ detail }) => {
    const { nodeId, nodeText } = detail;
    bar.removeAttribute('hidden');
    document.body.classList.add('audio-active');

    document.querySelectorAll('.story-node.is-narrating')
      .forEach(el => el.classList.remove('is-narrating'));

    const active = document.querySelector(`[data-node-id="${CSS.escape(nodeId)}"]`);
    if (active) {
      active.classList.add('is-narrating');
      active.classList.remove('is-resume-point');
      const rect = active.getBoundingClientRect();
      const visible = rect.top >= 60 && rect.bottom <= window.innerHeight - 70;
      if (!visible) active.scrollIntoView({ behavior: 'smooth', block: 'center' });

      const svgAnim = active.querySelector('svg[data-anim-fn]');
      if (svgAnim) {
        const fn = window[svgAnim.getAttribute('data-anim-fn')];
        if (typeof fn === 'function') fn();
      }
    }

    const short = nodeText.length > 65
      ? nodeText.slice(0, 62) + '…'
      : nodeText;
    preview.textContent = short;
  });

  document.addEventListener('audioplayer:playerstate', ({ detail }) => {
    if (detail.playing) {
      playPauseBtn.innerHTML = '&#9646;&#9646;';
      playPauseBtn.setAttribute('aria-label', 'Pause');
    } else {
      playPauseBtn.innerHTML = '&#9654;';
      playPauseBtn.setAttribute('aria-label', 'Play');
    }
    if (detail.audioMissing) {
      preview.textContent = '(Audio file not available — add MP3 files to enable narration)';
    }
  });

  document.addEventListener('audioplayer:progress', ({ detail }) => {
    progressFill.style.width = detail.percent + '%';
    progressBar.setAttribute('aria-valuenow', Math.round(detail.percent));
  });

  document.addEventListener('audioplayer:storycomplete', () => {
    playPauseBtn.innerHTML = '&#9654;';
    playPauseBtn.setAttribute('aria-label', 'Play');
    preview.textContent = 'End of story';
    document.querySelectorAll('.story-node.is-narrating')
      .forEach(el => el.classList.remove('is-narrating'));
    progressFill.style.width = '100%';
  });
}

// ── Language / pinyin controls ───────────────────────
function applyQueue() {
  player?.loadQueue(currentLang === 'zh' ? queueZh : queueEn);
}

function setLanguage(lang) {
  currentLang = lang === 'zh' ? 'zh' : 'en';
  document.body.classList.toggle('lang-zh', currentLang === 'zh');

  const useZh = currentLang === 'zh' && storyMeta?.titleZh;
  const title = useZh ? storyMeta.titleZh : (storyMeta?.title || '');
  document.getElementById('story-title').textContent = title;
  document.title = title + ' — Story Library';

  const btn = document.getElementById('lang-toggle');
  if (btn) {
    // The button shows the language you'll switch TO.
    btn.textContent = currentLang === 'zh' ? 'EN' : '中';
    btn.setAttribute('aria-pressed', String(currentLang === 'zh'));
  }

  applyQueue();
  try { localStorage.setItem(LANG_KEY, currentLang); } catch {}
}

function setPinyin(on) {
  document.body.classList.toggle('show-pinyin', on);
  const btn = document.getElementById('pinyin-toggle');
  if (btn) btn.setAttribute('aria-pressed', String(on));
  try { localStorage.setItem(PINYIN_KEY, on ? '1' : '0'); } catch {}
}

function setupLanguageControls(hasZh) {
  if (!hasZh) {
    // English-only story: keep the English queue, leave toggles hidden.
    applyQueue();
    return;
  }

  const langBtn = document.getElementById('lang-toggle');
  const pinyinBtn = document.getElementById('pinyin-toggle');
  langBtn.hidden = false;
  pinyinBtn.hidden = false;

  let savedLang = null, savedPinyin = null;
  try { savedLang = localStorage.getItem(LANG_KEY); } catch {}
  try { savedPinyin = localStorage.getItem(PINYIN_KEY); } catch {}

  // Chinese stories default to Chinese with pinyin shown.
  const lang = savedLang === 'en' ? 'en' : 'zh';
  const pinyinOn = savedPinyin === null ? true : savedPinyin === '1';

  setLanguage(lang);
  setPinyin(pinyinOn);

  langBtn.addEventListener('click', () =>
    setLanguage(currentLang === 'zh' ? 'en' : 'zh'));
  pinyinBtn.addEventListener('click', () =>
    setPinyin(!document.body.classList.contains('show-pinyin')));
}

// TOC toggle
document.getElementById('toc-toggle')?.addEventListener('click', () => {
  const toc = document.getElementById('chapter-toc');
  if (window.innerWidth <= 640) {
    toc.removeAttribute('hidden');
    toc.classList.toggle('toc-open');
  } else {
    if (toc.hasAttribute('hidden')) {
      toc.removeAttribute('hidden');
    } else {
      toc.setAttribute('hidden', '');
    }
  }
});

init().catch(console.error);
