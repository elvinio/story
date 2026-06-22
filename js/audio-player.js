function dispatch(name, detail) {
  document.dispatchEvent(new CustomEvent('audioplayer:' + name, { detail }));
}

export class AudioPlayer {
  constructor() {
    this._audio = new Audio();
    this._queue = [];   // [{ id, audioSrc, text }]
    this._index = -1;
    this._loading = false;

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
      // Audio file missing or unplayable — emit error so UI can reflect it
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
    this._audio.src = node.audioSrc;
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
