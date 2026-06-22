async function init() {
  const grid = document.getElementById('library-grid');
  if (!grid) return;

  try {
    const resp = await fetch('stories/index.json');
    if (!resp.ok) throw new Error('index not found');
    const stories = await resp.json();

    grid.innerHTML = '';

    if (stories.length === 0) {
      grid.innerHTML = '<p class="library-empty">No stories yet.</p>';
      return;
    }

    stories.forEach(story => grid.appendChild(renderCard(story)));
  } catch {
    grid.innerHTML = '<p class="library-empty">Could not load the story list.</p>';
  }
}

function renderCard(story) {
  const saved = getSavedPosition(story.id);
  const card = document.createElement('article');
  card.className = 'story-card';

  const coverContent = `
    <img src="${escHtml(story.coverImage)}"
         alt="Cover of ${escHtml(story.title)}"
         loading="lazy"
         onerror="this.style.display='none'">`;

  card.innerHTML = `
    <a href="reader.html?story=${encodeURIComponent(story.id)}"
       class="card-link"
       aria-label="Read ${escHtml(story.title)}">
      <div class="card-cover">${coverContent}</div>
      <div class="card-body">
        <h2 class="card-title">${escHtml(story.title)}</h2>
        <p class="card-author">by ${escHtml(story.author)}</p>
        <div class="card-meta">
          <span class="badge">${escHtml(story.ageRange)} yrs</span>
          <span class="badge">${escHtml(String(story.estimatedMinutes))} min</span>
          ${saved ? '<span class="badge badge-resume">Continue</span>' : ''}
        </div>
      </div>
    </a>`;

  return card;
}

function getSavedPosition(storyId) {
  try {
    const raw = localStorage.getItem('story-reader:position:' + storyId);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

init();
