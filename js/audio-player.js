// Supported formats in preference order for tryFormats fallback.
// Opus (.opus) and OGG Vorbis (.ogg) are both carried in the Ogg container.
// All modern browsers (Chrome 33+, Firefox 15+, Edge 14+) support Opus.
// Safari supports Opus from v11+ (macOS High Sierra / iOS 11).
const FORMAT_FALLBACKS = {
  'opus': ['opus', 'ogg', 'mp3'],
  'ogg':  ['ogg',  'opus', 'mp3'],
  'mp3':  ['mp3',  'opus', 'ogg'],
};

const MIME = {
  opus: 'audio/ogg; codecs=opus',
  ogg:  'audio/ogg; codecs=vorbis',
  mp3:  'audio/mpeg',
};

function canPlay(ext) {
  const probe = document.createElement('audio');
  return probe.canPlayType(MIME[ext] || '') !== '';
}

// Build the best src to try given a raw audio path.
// If the browser can't play the file's native format, swap the extension to
// the first supported alternative (useful when serving both opus and mp3).
function resolveSrc(rawSrc) {
  const ext = rawSrc.split('.').pop().toLowerCase();
  const base = rawSrc.slice(0, rawSrc.lastIndexOf('.'));
  const fallbacks = FORMAT_FALLBACKS[ext] || [ext];
  for (const fmt of fallbacks) {
    if (canPlay(fmt)) {
      return fmt === ext ? rawSrc : `${base}.${fmt}`;
    }
  }
  return rawSrc; // let the browser decide and error naturally
}

function dispatch(name, detail) {
  document.dispatchEvent(new CustomEvent('audioplayer:' + name, { detail }));
}

export class AudioPlayer {
  constructor() {
    this._audio = new Audio();
    this._queue = [];   // [{ id, audioSrc, text }]
    this._index = -1;

    this._audio.addEventListener('ended', () => this._advance());
    this._audio.addEventListener('timeupdate', () => {
      const pct = this._audio.duration
        ? (this._audio.currentTime / this._audio.duration) * 100
        : 0;
      dispatch('progress', { percent: pct });
    });
    this._audio.addEventListener('play', () =>
      dispatch('playerstate', { playing: true }));
    this._audio.addEventListener('pause', () =>
      dispatch('playerstate', { playing: false }));
    this._audio.addEventListener('error', () => {
      dispatch('playerstate', { playing: false, audioMissing: true });
    });
  }

  loadQueue(nodes) {
    this._queue = nodes;
  }

  playFrom(nodeId) {
    const idx = this._queue.findIndex(n => n.id === nodeId);
    if (idx === -1) return;
    this._index = idx;
    this._playCurrentNode();
  }

  togglePlayPause() {
    if (this._audio.paused) {
      this._audio.play().catch(() => {});
    } else {
      this._audio.pause();
    }
  }

  prev() {
    if (this._index > 0) {
      this._index--;
      this._playCurrentNode();
    }
  }

  next() {
    this._advance();
  }

  setSpeed(rate) {
    this._audio.playbackRate = rate;
  }

  get currentNodeId() {
    return this._queue[this._index]?.id ?? null;
  }

  get isPlaying() {
    return !this._audio.paused;
  }

  _playCurrentNode() {
    const node = this._queue[this._index];
    if (!node) return;
    dispatch('nodestart', { nodeId: node.id, nodeText: node.text });
    this._audio.pause();
    this._audio.src = resolveSrc(node.audioSrc);
    this._audio.load();
    this._audio.play().catch(err => {
      // AbortError fires when load() interrupts an in-progress play — safe to ignore
      if (err.name !== 'AbortError') {
        dispatch('playerstate', { playing: false, audioMissing: true });
      }
    });
  }

  _advance() {
    if (this._index < this._queue.length - 1) {
      this._index++;
      this._playCurrentNode();
    } else {
      dispatch('storycomplete', {});
      dispatch('progress', { percent: 100 });
    }
  }
}
