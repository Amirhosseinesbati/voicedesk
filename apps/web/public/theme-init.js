/* global document, localStorage, window */
/* Runs before the application and stylesheet. External script: no inline CSP exception. */
(function () {
  var preference = 'dark';
  try {
    var stored = localStorage.getItem('voicedesk_appearance');
    if (stored === null) stored = localStorage.getItem('voicedesk_theme');
    if (stored === 'light' || stored === 'dark' || stored === 'system') preference = stored;
  } catch { /* Restricted storage: keep the safe, deterministic default. */ }
  var appearance = preference;
  if (preference === 'system') {
    try { appearance = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'; }
    catch { appearance = 'dark'; }
  }
  document.documentElement.dataset.themePreference = preference;
  document.documentElement.dataset.appearance = appearance;
  var meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', appearance === 'dark' ? '#0b101a' : '#f4f6fa');
}());
