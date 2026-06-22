const PREFIX = 'story-reader:position:';

export class ScrollTracker {
  constructor(storyId, storyVersion) {
    this._key = PREFIX + storyId;
    this._version = storyVersion;
    this._observer = null;
    this._timer = null;
  }

  observe(container) {
    this._observer = new IntersectionObserver(entries => {
      const visible = entries
        .filter(e => e.isIntersecting && e.intersectionRatio >= 0.3)
        .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);

      if (visible.length === 0) return;
      const el = visible[0].target;
      this._schedule(el.dataset.nodeId, el.dataset.chapterId);
    }, { threshold: 0.3 });

    container.querySelectorAll('.story-node').forEach(el =>
      this._observer.observe(el));
  }

  disconnect() {
    this._observer?.disconnect();
    clearTimeout(this._timer);
  }

  getSavedPosition() {
    try {
      const raw = localStorage.getItem(this._key);
      if (!raw) return null;
      const pos = JSON.parse(raw);
      if (pos.storyVersion !== this._version) return null;
      return pos;
    } catch {
      return null;
    }
  }

  _schedule(nodeId, chapterId) {
    clearTimeout(this._timer);
    this._timer = setTimeout(() => {
      try {
        localStorage.setItem(this._key, JSON.stringify({
          nodeId,
          chapterId,
          savedAt: new Date().toISOString(),
          storyVersion: this._version,
        }));
      } catch {}
    }, 500);
  }
}
