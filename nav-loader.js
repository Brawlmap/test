window.addEventListener('DOMContentLoaded', () => {
  const placeholder = document.getElementById('nav-root');
  if (!placeholder) return;
  fetch('templates/nav.html')
    .then(response => {
      if (!response.ok) throw new Error('Nav template not found');
      return response.text();
    })
    .then(html => {
      placeholder.innerHTML = html;
      initNav();
    })
    .catch(err => console.error('Nav load failed:', err));
});

function initNav() {
  const root = document.getElementById('nav-root');
  if (!root) return;

  const moreWrap = root.querySelector('#moreWrap');
  const moreBtn = root.querySelector('.nav-more-btn');
  const profileBtn = root.querySelector('#profileBtn');
  const currentPath = window.location.pathname.split('/').pop() || 'index.html';
  const hash = window.location.hash || '';

  const isIndex = currentPath === '' || currentPath === 'index.html';

  const pageTabs = root.querySelectorAll('.nav-tab[data-page]');
  pageTabs.forEach(tab => {
    const page = tab.dataset.page;
    const isHome = isIndex && page === 'home' && hash !== '#countdown-section';
    const isLeaderboard = page === 'leaderboard' && currentPath === 'leaderboard.html';
    const isCountdown = page === 'countdown' && isIndex && hash === '#countdown-section';

    if (isHome || isLeaderboard || isCountdown) {
      tab.classList.add('active');
    }

    if (isIndex && page === 'home') {
      tab.addEventListener('click', event => {
        event.preventDefault();
        if (typeof showPage === 'function') showPage('home', tab);
        else window.location.href = tab.href;
      });
    }
  });

  if (currentPath === 'profile.html' && profileBtn) {
    profileBtn.classList.add('active');
  }

  if (profileBtn) {
    profileBtn.addEventListener('click', () => {
      window.location.href = 'profile.html';
    });
  }

  if (moreBtn && moreWrap) {
    moreBtn.addEventListener('click', () => moreWrap.classList.toggle('open'));
    document.addEventListener('click', e => {
      if (!moreWrap.contains(e.target)) moreWrap.classList.remove('open');
    });
  }
}
