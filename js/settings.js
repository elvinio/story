const STORAGE_KEY = 'story-reader:settings';

const DEFAULTS = {
  fontSize: 18,
  fontFamily: "Georgia, 'Times New Roman', serif",
  warmth: 60,
  lineHeight: 1.85,
  paragraphGap: 1.4,
};

function lerpHex(a, b, t) {
  const parse = h => [
    parseInt(h.slice(1, 3), 16),
    parseInt(h.slice(3, 5), 16),
    parseInt(h.slice(5, 7), 16),
  ];
  const [ar, ag, ab] = parse(a);
  const [br, bg, bb] = parse(b);
  const r = Math.round(ar + (br - ar) * t).toString(16).padStart(2, '0');
  const g = Math.round(ag + (bg - ag) * t).toString(16).padStart(2, '0');
  const bv = Math.round(ab + (bb - ab) * t).toString(16).padStart(2, '0');
  return `#${r}${g}${bv}`;
}

function warmthToColors(w) {
  const t = w / 100;
  return {
    bg: lerpHex('#f8f8f6', '#ede0cc', t),
    text: lerpHex('#222222', '#3b2210', t),
  };
}

export class SettingsManager {
  constructor() {
    this.settings = { ...DEFAULTS, ...this._load() };
    this._apply();
  }

  _load() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch {
      return {};
    }
  }

  _save() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(this.settings));
    } catch {}
  }

  _apply() {
    const s = this.settings;
    const r = document.documentElement;
    r.style.setProperty('--reader-font-size', s.fontSize + 'px');
    r.style.setProperty('--reader-font-family', s.fontFamily);
    r.style.setProperty('--reader-line-height', s.lineHeight);
    r.style.setProperty('--reader-paragraph-gap', s.paragraphGap + 'em');
    const { bg, text } = warmthToColors(s.warmth);
    r.style.setProperty('--reader-bg', bg);
    r.style.setProperty('--reader-text', text);
  }

  update(key, value) {
    this.settings[key] = value;
    this._apply();
    this._save();
  }

  reset() {
    this.settings = { ...DEFAULTS };
    this._apply();
    this._save();
  }

  mount() {
    if (this._mounted) return;
    this._mounted = true;
    const panel = document.getElementById('settings-panel');
    if (!panel) return;

    document.getElementById('settings-btn')
      ?.addEventListener('click', () => panel.showModal());
    document.getElementById('settings-close')
      ?.addEventListener('click', () => panel.close());
    panel.addEventListener('click', e => { if (e.target === panel) panel.close(); });
    document.getElementById('settings-reset')
      ?.addEventListener('click', () => { this.reset(); this._syncUI(); });

    this._syncUI();
    this._wireControls();
  }

  _wireControls() {
    const wire = (id, key, transform, displayFn) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener('input', () => {
        const v = transform(el.value);
        this.update(key, v);
        const valueEl = document.getElementById(id.replace('setting-', '') + '-value');
        if (valueEl && displayFn) valueEl.textContent = displayFn(v);
      });
    };

    wire('setting-font-size', 'fontSize', Number, v => v + 'px');
    wire('setting-warmth', 'warmth', Number, v => v + '%');
    wire('setting-line-height', 'lineHeight', v => Number(v) / 10, v => v.toFixed(1));
    wire('setting-paragraph-gap', 'paragraphGap', v => Number(v) / 10, v => v.toFixed(1) + 'em');

    const ff = document.getElementById('setting-font-family');
    ff?.addEventListener('change', () => this.update('fontFamily', ff.value));
  }

  _syncUI() {
    const s = this.settings;

    const setVal = (id, value) => {
      const el = document.getElementById(id);
      if (el) el.value = value;
    };
    const setText = (id, text) => {
      const el = document.getElementById(id);
      if (el) el.textContent = text;
    };

    setVal('setting-font-size', s.fontSize);
    setText('font-size-value', s.fontSize + 'px');

    setVal('setting-font-family', s.fontFamily);

    setVal('setting-warmth', s.warmth);
    setText('warmth-value', s.warmth + '%');

    setVal('setting-line-height', Math.round(s.lineHeight * 10));
    setText('line-height-value', s.lineHeight.toFixed(1));

    setVal('setting-paragraph-gap', Math.round(s.paragraphGap * 10));
    setText('paragraph-gap-value', s.paragraphGap.toFixed(1) + 'em');
  }
}

// Auto-mount when loaded as a standalone module (not when imported by reader.js)
// Both index.html and reader.html load this module directly; reader.js also imports it.
// We use a flag to avoid double-mounting.
const mgr = new SettingsManager();
if (document.getElementById('settings-panel')) {
  mgr.mount();
}

export default mgr;
