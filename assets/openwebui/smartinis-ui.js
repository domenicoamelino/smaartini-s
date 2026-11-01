/* SMARTINI's presentation adapter for Open WebUI 0.12.3. No chat or account access. */
(() => {
  'use strict';
  const KEY = 'smartinis.skin.v1';
  const PREVIOUS = 'smartinis.previous-theme.v1';
  const ROOT = document.documentElement;
  const SKINS = ['midnight', 'forest', 'original'];
  const LOGO = '/smartinis-ui/smartinis-logo.png';
  const GREETING = 'Ready to work, what’s on your mind?';
  const read = (key) => { try { return localStorage.getItem(key); } catch { return null; } };
  const write = (key, value) => { try { localStorage.setItem(key, value); } catch { /* Session still works. */ } };
  let skin = read(KEY) || 'midnight';
  if (!SKINS.includes(skin)) skin = 'midnight';
  let picker;
  const heroes = new Map();
  function applySkin(value) {
    skin = value;
    ROOT.dataset.smartinisSkin = value;
    if (value !== 'original') {
      if (read(PREVIOUS) === null) write(PREVIOUS, read('theme') || 'system');
      write('theme', 'dark');
      ROOT.classList.remove('light', 'her', 'oled-dark');
      ROOT.classList.add('dark');
    }
    if (picker) picker.value = value;
  }
  function logo(className) {
    const img = document.createElement('img');
    img.src = LOGO;
    img.alt = 'SMARTINI’s';
    img.className = className;
    img.width = 2172;
    img.height = 724;
    return img;
  }
  function mountPicker() {
    const sidebar = document.querySelector('#sidebar');
    const top = sidebar?.querySelector('.sidebar');
    if (!top || sidebar.querySelector('[data-smartinis-picker]')) return;
    const label = document.createElement('label');
    label.dataset.smartinisPicker = '';
    label.className = 'smartinis-skin-picker';
    const text = document.createElement('span');
    text.textContent = 'Appearance';
    picker = document.createElement('select');
    picker.setAttribute('aria-label', 'SMARTINI’s appearance');
    for (const [value, title] of [['midnight', 'Midnight'], ['forest', 'Forest'], ['original', 'Open WebUI theme']]) {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = title;
      picker.append(option);
    }
    picker.value = skin;
    picker.addEventListener('change', () => {
      const value = picker.value;
      write(KEY, value);
      if (value === 'original') {
        write('theme', read(PREVIOUS) || 'system');
        try { localStorage.removeItem(PREVIOUS); } catch { /* Optional persistence. */ }
        // Let Open WebUI restore its own complete theme, including inline OLED colors.
        location.reload();
      } else applySkin(value);
    });
    label.append(text, picker);
    top.after(label);
  }
  function brandSidebar() {
    const name = document.querySelector('#sidebar-webui-name');
    const top = name?.closest('.sidebar');
    const link = name?.closest('a[href="/"]');
    const icon = top?.querySelector('img.sidebar-new-chat-icon');
    // Require both independently known anchors; unknown layouts stay unchanged.
    if (!name || !top || !link || !icon || top.dataset.smartinisBrand) return;
    const image = logo('smartinis-sidebar-logo');
    top.dataset.smartinisBrand = 'pending';
    image.addEventListener('load', () => {
      top.dataset.smartinisBrand = 'ready';
      name.hidden = true;
      icon.closest('a')?.setAttribute('data-smartinis-old-mark', '');
      link.setAttribute('aria-label', 'SMARTINI’s — new chat');
    }, { once: true });
    image.addEventListener('error', () => { image.remove(); /* Original remains visible. */ }, { once: true });
    link.append(image);
  }
  function brandHero() {
    // Placeholder.svelte's welcome-only header. Never search/replace model text in chat.
    const welcome = document.querySelector('div.m-auto.w-full.max-w-\\[58rem\\]');
    const header = welcome?.querySelector('div.flex.flex-row.justify-center.gap-2\\.5');
    if (!header || header.dataset.smartinisHero ||
        !header.querySelector('img[src*="/models/model/profile/image"]') ||
        !header.querySelector('div.line-clamp-1')) return;
    header.dataset.smartinisHero = 'pending';
    const hero = document.createElement('div');
    hero.className = 'smartinis-hero';
    const image = logo('smartinis-hero-logo');
    const heading = document.createElement('h1');
    heading.textContent = GREETING;
    hero.append(image, heading);
    image.addEventListener('load', () => {
      header.hidden = true;
      header.dataset.smartinisHero = 'ready';
      header.after(hero);
      heroes.set(header, hero);
    }, { once: true });
    image.addEventListener('error', () => {
      // A missing asset must not produce a blank welcome screen.
      header.dataset.smartinisHero = 'asset-unavailable';
    }, { once: true });
  }
  function update() {
    for (const [header, hero] of heroes) {
      if (!header.isConnected) { hero.remove(); heroes.delete(header); }
    }
    mountPicker(); brandSidebar(); brandHero();
  }
  async function start() {
    try {
      const response = await fetch('/api/version', { credentials: 'omit', cache: 'no-store' });
      if (!response.ok || (await response.json()).version !== '0.12.3') {
        console.info('SMARTINI’s UI: unsupported WebUI version; original interface retained.');
        return;
      }
    } catch {
      console.info('SMARTINI’s UI: version unavailable; original interface retained.');
      return;
    }
    applySkin(skin);
    update();
    let scheduled = false;
    new MutationObserver(() => {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(() => { scheduled = false; update(); });
    }).observe(document.body, { childList: true, subtree: true });
    window.addEventListener('storage', (event) => {
      if (event.key === KEY) location.reload();
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();
