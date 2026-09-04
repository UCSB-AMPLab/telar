/**
 * Shared fixture for the share panel tests.
 *
 * Holds what the share panel's test files need in common: the two panel
 * markups, the stories JSON block, the clipboard and alert stubs, the script
 * harness, and the DOM query helpers the assertions read back. Not itself a
 * test file, so vitest does not collect it (see `include` in
 * `vitest.config.js`).
 *
 * The markup is `_includes/share-panel.html` with the Liquid stripped and the
 * English language pack's strings in place, one builder per branch: the story
 * branch (`page.layout == "story"`) and the branch every other page renders.
 * Both builders end with `_includes/share-site-tab.html`, and both embed
 * sections end with `_includes/share-embed-controls.html`, exactly as the
 * include composes them.
 *
 * The stories in `storiesBlock` are this repository's own, as
 * `_jekyll-files/_stories/` holds them: their titles, their permalinks, and
 * the one that carries `protected: true`.
 *
 * @version v1.7.0
 */

import { vi } from 'vitest';

import { createSharePanel } from '../../assets/js/share-panel/main.js';

/** The origin the test file is served at; see its @vitest-environment-options. */
export const ORIGIN = 'https://example.org';
export const BASEURL = '/telar';

/** Stories copied verbatim from _jekyll-files/_stories/. */
export const ALLEGORICAL = {
  title: 'The Allegorical Woman',
  url: `${ORIGIN}${BASEURL}/stories/allegorical-woman/`,
  protected: false,
};
export const COLONIAL = {
  title: 'Colonial Landscapes',
  url: `${ORIGIN}${BASEURL}/stories/colonial-landscapes/`,
  protected: false,
};
export const LOCKED = {
  title: 'Locked Fixture Story',
  url: `${ORIGIN}${BASEURL}/stories/locked-fixture/`,
  protected: true,
};
export const STORIES = [ALLEGORICAL, COLONIAL, LOCKED];

/** The copy icon every copy button carries, as the include writes it. */
const COPY_ICON = '<svg class="icon" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>';

/**
 * The checkmark the copy feedback swaps in. The literal in share-panel.js
 * self-closes its two shapes; this is that literal as jsdom serialises it back
 * out of the document, which is what an assertion on outerHTML sees.
 */
export const CHECK_ICON = '<svg class="icon" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"></circle><path d="m9 12 2 2 4-4"></path></svg>';

function copyButton(id) {
  return `<button class="share-copy-btn" type="button" id="${id}" aria-label="COPY">
        ${COPY_ICON}
        <span class="btn-text">COPY</span>
      </button>`;
}

/** _includes/share-embed-controls.html with the Liquid resolved. */
function embedControls() {
  return `<div class="share-embed-controls">
    <div class="share-embed-preset">
      <label class="share-embed-label">Preset sizes for different platforms</label>
      <select class="share-embed-select" id="embed-preset-select">
        <option value="canvas" selected>Canvas LMS</option>
        <option value="moodle">Moodle/Blackboard</option>
        <option value="wordpress">WordPress</option>
        <option value="squarespace">Squarespace</option>
        <option value="wix">Wix</option>
        <option value="mobile">Mobile</option>
        <option value="fixed">Fixed</option>
        <option value="custom">Custom</option>
      </select>
    </div>
    <div class="share-embed-dimension">
      <label class="share-embed-label">Width</label>
      <input type="text" class="share-embed-input" id="embed-width-input" value="100%">
    </div>
    <div class="share-embed-dimension">
      <label class="share-embed-label">Height</label>
      <input type="text" class="share-embed-input" id="embed-height-input" value="800">
    </div>
    <div class="share-embed-copy">
      ${copyButton('embed-copy-code-btn')}
    </div>
  </div>`;
}

/** _includes/share-site-tab.html with the Liquid resolved. */
function siteTab() {
  return `<div class="tab-pane fade" id="content-site" role="tabpanel" aria-labelledby="tab-site">
    <div class="share-section">
      <label class="share-section-label">Share Link</label>
      <p class="share-section-help">Copy a link to the site homepage, where visitors can browse all stories.</p>
      <div class="share-input-row">
        <input type="text" class="share-input" id="share-site-url-input" readonly value="" aria-label="Share Link">
        ${copyButton('share-copy-site-btn')}
      </div>
    </div>
  </div>`;
}

/** The story branch of _includes/share-panel.html, Liquid resolved. */
export function storyPanelMarkup() {
  return `<div class="modal fade" id="panel-share" tabindex="-1" aria-labelledby="panel-share-title" aria-hidden="true">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content">
      <div class="modal-header share-panel-header">
        <div class="share-header-row">
          <h5 class="share-panel-title" id="panel-share-title">Share</h5>
          <div class="share-pill-tabs" role="tablist">
            <button class="share-pill-tab active" id="tab-story" data-bs-toggle="tab" data-bs-target="#content-story" type="button" role="tab" aria-controls="content-story" aria-selected="true">this story</button>
            <button class="share-pill-tab" id="tab-view" data-bs-toggle="tab" data-bs-target="#content-view" type="button" role="tab" aria-controls="content-view" aria-selected="false">this view</button>
            <button class="share-pill-tab" id="tab-site" data-bs-toggle="tab" data-bs-target="#content-site" type="button" role="tab" aria-controls="content-site" aria-selected="false">this whole site</button>
          </div>
        </div>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
      </div>

      <div class="modal-body">
        <div class="tab-content">
          <div class="tab-pane fade show active" id="content-story" role="tabpanel" aria-labelledby="tab-story">
            <div class="share-section d-none" id="story-privacy-section">
              <label class="share-section-label">Story Privacy</label>
              <div class="share-privacy-row">
                <span class="share-privacy-question">Do you want to share your story with or without the access key?</span>
                <div class="share-key-toggle" role="group" aria-label="Include key option">
                  <button type="button" class="share-key-btn active" data-value="without" id="share-key-without">Without key</button>
                  <button type="button" class="share-key-btn" data-value="with" id="share-key-with">With key</button>
                </div>
              </div>
            </div>

            <div class="share-section">
              <label class="share-section-label">Share Link</label>
              <p class="share-section-help">Copy a direct link to this story to share by email, social media, or messaging apps.</p>
              <div class="share-input-row">
                <input type="text" class="share-input" id="share-url-input" readonly value="" aria-label="Share Link">
                ${copyButton('share-copy-link-btn')}
              </div>
              <p class="share-warning d-none" id="share-key-warning">This link includes the access key, so anyone who has it can open the story. Don't share it publicly.</p>
            </div>

            <div class="share-section">
              <label class="share-section-label">Embed Code</label>
              <p class="share-section-help">Embed this story in another website or LMS.</p>
              <textarea class="share-textarea" id="embed-code-textarea" rows="3" readonly aria-label="Embed Code"></textarea>
              <p class="share-warning d-none" id="embed-key-warning">This embed code includes the access key, so anyone who copies it can open the story. Only embed it on sites you trust.</p>
              ${embedControls()}
            </div>
          </div>

          <div class="tab-pane fade" id="content-view" role="tabpanel" aria-labelledby="tab-view">
            <div class="share-section">
              <label class="share-section-label">Share Link</label>
              <p class="share-section-help">Copy a link to this exact point in the story — the step and panel you're currently viewing.</p>
              <div class="share-input-row">
                <input type="text" class="share-input" id="share-view-url-input" readonly value="" aria-label="Share Link">
                ${copyButton('share-copy-view-btn')}
              </div>
            </div>
          </div>

          ${siteTab()}
        </div>
      </div>
    </div>
  </div>
</div>`;
}

/** The branch every non-story page renders, Liquid resolved. */
export function otherPanelMarkup() {
  return `<div class="modal fade" id="panel-share" tabindex="-1" aria-labelledby="panel-share-title" aria-hidden="true">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content">
      <div class="modal-header share-panel-header">
        <div class="share-header-row">
          <h5 class="share-panel-title" id="panel-share-title">Share</h5>
          <div class="share-pill-tabs" role="tablist">
            <button class="share-pill-tab active" id="tab-story" data-bs-toggle="tab" data-bs-target="#content-story" type="button" role="tab" aria-controls="content-story" aria-selected="true">a single story</button>
            <button class="share-pill-tab" id="tab-site" data-bs-toggle="tab" data-bs-target="#content-site" type="button" role="tab" aria-controls="content-site" aria-selected="false">this whole site</button>
          </div>
        </div>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
      </div>

      <div class="modal-body">
        <div class="tab-content">
          <div class="tab-pane fade show active" id="content-story" role="tabpanel" aria-labelledby="tab-story">
            <div class="share-section">
              <label class="share-section-label">Select Story</label>
              <select class="share-story-select" id="share-story-select">
                <option value="">Choose a story...</option>
              </select>
            </div>

            <div class="share-section">
              <label class="share-section-label">Share Link</label>
              <p class="share-section-help">Copy a direct link to this story to share by email, social media, or messaging apps.</p>
              <div class="share-input-row">
                <input type="text" class="share-input" id="share-url-input" readonly value="" placeholder="Select a story above" aria-label="Share Link">
                ${copyButton('share-copy-link-btn')}
              </div>
              <p class="share-warning d-none" id="share-protected-warning">This story is protected. Recipients will need the key to view it.</p>
            </div>

            <div class="share-section">
              <label class="share-section-label">Embed Code</label>
              <p class="share-section-help">Embed this story in another website or LMS.</p>
              <textarea class="share-textarea" id="embed-code-textarea" rows="3" readonly placeholder="Select a story above" aria-label="Embed Code"></textarea>
              <p class="share-warning d-none" id="embed-protected-warning">This story is protected. The embed will show a lock screen until viewers enter the key.</p>
              ${embedControls()}
            </div>
          </div>

          ${siteTab()}
        </div>
      </div>
    </div>
  </div>
</div>`;
}

/** The JSON block _layouts/index.html writes, one entry per story. */
export function storiesBlock(json) {
  return `<script id="telar-stories-data" type="application/json">${json}</script>`;
}

/** The stories block with this repository's stories in it. */
export function storiesBlockFor(stories = STORIES) {
  return storiesBlock(JSON.stringify(stories.map(
    (story) => ({ title: story.title, url: story.url, protected: story.protected }))));
}

/**
 * Put a page in place: its path, its body class, its title, and its markup.
 * The share panel reads all four, and only the markup through an id.
 */
export function renderPage({ path, bodyClass = '', title = 'Telar', markup = '' }) {
  window.history.replaceState({}, '', path);
  document.body.className = bodyClass;
  document.title = title;
  document.body.innerHTML = markup;
}

/** The og:title jekyll-seo-tag emits, which the embed title prefers. */
export function setOgTitle(content) {
  const meta = document.createElement('meta');
  meta.setAttribute('property', 'og:title');
  meta.setAttribute('content', content);
  document.head.appendChild(meta);
}

/** The overlay _layouts/story.html renders for an encrypted story. */
export function addUnlockOverlay() {
  const overlay = document.createElement('div');
  overlay.id = 'story-unlock-overlay';
  document.body.appendChild(overlay);
}

/**
 * A clipboard recording every write. `writeText` decides what the promise
 * does, which is how the rejection path is reached; the default resolves.
 */
export function stubClipboard(writeText = () => Promise.resolve()) {
  const writes = [];
  const clipboard = {
    writeText: vi.fn((text) => {
      writes.push(text);
      return writeText(text);
    }),
  };
  Object.defineProperty(navigator, 'clipboard', {
    value: clipboard, configurable: true, writable: true,
  });
  return writes;
}

/** No clipboard at all, which is what an insecure context gives the page. */
export function removeClipboard() {
  delete navigator.clipboard;
}

/** The alert the copy path falls back to, recording its messages. */
export function stubAlert() {
  const messages = [];
  vi.stubGlobal('alert', vi.fn((message) => { messages.push(message); }));
  return messages;
}

/** Build a panel over the page as the bundle's tail does. */
export async function runScript() {
  createSharePanel({
    doc: document,
    win: window,
    navigatorRef: navigator,
    alertFn: window.alert,
  }).init();
}

/** Open the panel the way Bootstrap does. */
export function openPanel() {
  el('panel-share').dispatchEvent(new Event('show.bs.modal'));
}

export const el = (id) => document.getElementById(id);
export const value = (id) => el(id).value;
export const hasClass = (id, className) => el(id).classList.contains(className);
export const icon = (id) => el(id).querySelector('.icon');

/** Every option of the story selector, with the flag the code stamps on it. */
export const selectOptions = () => [...el('share-story-select').options].map((option) => ({
  value: option.value,
  text: option.textContent,
  protected: option.dataset.protected,
}));

/** Choose a story in the selector the way a reader does. */
export function chooseStory(url) {
  const select = el('share-story-select');
  select.value = url;
  select.dispatchEvent(new Event('change', { bubbles: true }));
}

/** Choose an embed preset the way a reader does. */
export function choosePreset(preset) {
  const select = el('embed-preset-select');
  select.value = preset;
  select.dispatchEvent(new Event('change', { bubbles: true }));
}

/** Type a dimension the way a reader does. */
export function typeDimension(id, text) {
  const input = el(id);
  input.value = text;
  input.dispatchEvent(new Event('input', { bubbles: true }));
}

/** Registered as `beforeEach` by each test file so both share one setup. */
export function silenceConsole() {
  return {
    log: vi.spyOn(console, 'log').mockImplementation(() => {}),
    warn: vi.spyOn(console, 'warn').mockImplementation(() => {}),
    error: vi.spyOn(console, 'error').mockImplementation(() => {}),
  };
}

/** Registered as `afterEach` by each test file so both share one teardown. */
export function resetTimersMocksAndDom() {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  removeClipboard();
  delete window.storyData;
  delete window.telarStoryKey;
  document.body.innerHTML = '';
  document.body.className = '';
  document.head.querySelectorAll('meta[property="og:title"]').forEach((meta) => meta.remove());
}
