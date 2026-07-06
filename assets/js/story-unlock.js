/**
 * Telar Story Unlock
 *
 * Handles client-side decryption of protected stories using the Web Crypto API.
 * When a story is encrypted, this module shows an unlock overlay, decrypts the
 * envelope when the user provides the correct key, and injects the decrypted
 * step markup into the page. The steps are rendered at build time through the
 * same include as open stories (scripts/encrypt_protected_stories.py encrypts
 * the rendered HTML together with the steps JSON in one envelope), so this
 * module does no rendering of its own: decrypt, inject, hand off.
 *
 * Encryption uses AES-256-GCM with PBKDF2 key derivation (210,000 iterations),
 * matching the Python encryption in scripts/telar/encryption.py. The story id
 * is the envelope's additional authenticated data, so one story's envelope
 * cannot be replayed onto another story's page.
 *
 * NOTE: This is a deterrent against casual access, not a confidentiality
 * guarantee. On a public site, the source CSV is publicly accessible in
 * the published output, and the salt/IV/ciphertext are all inline in the
 * page. Use a private repository for content that must not be read by
 * unauthorized people.
 *
 * @version v1.6.0
 */

// PBKDF2 iterations — must match Python encryption (OWASP minimum for
// PBKDF2-HMAC-SHA256). Stories are re-encrypted from plaintext each build,
// so this stays in lockstep with scripts/telar/encryption.py.
const PBKDF2_ITERATIONS = 210000;

/**
 * Check if storyData is encrypted.
 * @returns {boolean} True if storyData contains encrypted content
 */
function isStoryEncrypted() {
  return window.storyData?.encrypted === true;
}

/**
 * Get story ID from the current page URL.
 * @returns {string} Story identifier
 */
function getStoryId() {
  // Extract story ID from URL path (e.g., /stories/tu-historia/ -> tu-historia)
  const pathParts = window.location.pathname.split('/').filter(p => p);
  const storiesIndex = pathParts.indexOf('stories');
  if (storiesIndex >= 0 && pathParts[storiesIndex + 1]) {
    return pathParts[storiesIndex + 1];
  }
  return 'unknown';
}

/**
 * Derive a short, stable cache-binding token from the encrypted payload.
 *
 * Binding the sessionStorage entry to the salt+IV (which are regenerated on
 * every build-time re-encryption) means a stale cache is ignored after a
 * rebuild, and one story's cache can never be applied to a different story
 * whose URL happens to resolve to the same id. Returns null when there is no
 * payload to bind to.
 * @returns {string|null}
 */
let _payloadBinding = null;
function getPayloadKey() {
  // Memoise on first computation: window.storyData carries salt/iv only until a
  // successful unlock replaces it with the decrypted steps, so reading it lazily
  // after that point would yield null. The binding is computed once at init.
  if (_payloadBinding) return _payloadBinding;
  const d = window.storyData;
  // A stub that reached the browser un-encrypted carries salt: "" — falsy, so
  // the cache path is skipped entirely and a bad build fails safe here.
  if (!d || !d.salt) return null;
  const material = String(d.salt) + String(d.iv || '');
  try {
    _payloadBinding = btoa(material).slice(0, 16);
  } catch (e) {
    // btoa throws on non-Latin1 input; the salt/iv are base64 so this is a
    // belt-and-braces fallback only.
    _payloadBinding = material.slice(0, 16);
  }
  return _payloadBinding;
}

/**
 * Get a cached unlock from sessionStorage.
 *
 * Only ever returns the stored decryption key (+ its payload binding) — never
 * plaintext steps (those are re-derived on use). Refuses to read when the story
 * id is unknown (prevents cross-story disclosure) or when the cached payload
 * binding no longer matches the page's ciphertext. Legacy plaintext caches
 * (array, or `{ steps, key }`) are treated as a miss.
 * @returns {{ key: string, payloadKey: string }|null}
 */
function getCachedDecryption() {
  const storyId = getStoryId();
  if (storyId === 'unknown') return null;
  const cached = sessionStorage.getItem(`telar_unlock_${storyId}`);
  if (!cached) return null;
  try {
    const parsed = JSON.parse(cached);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null;
    if (!parsed.key || !parsed.payloadKey) return null;       // legacy / incomplete entry
    if (parsed.payloadKey !== getPayloadKey()) return null;   // ciphertext changed since caching
    return { key: parsed.key, payloadKey: parsed.payloadKey };
  } catch (e) {
    return null;
  }
}

/**
 * Cache a successful unlock in sessionStorage.
 *
 * Stores only the decryption key and the payload binding — not the decrypted
 * plaintext — so the cache exposes nothing beyond what the user already typed.
 * Refuses to write under an unknown story id.
 * @param {string} key - The decryption key (also used for share-panel integration)
 */
function cacheDecryption(key, payloadKey) {
  const storyId = getStoryId();
  if (storyId === 'unknown') return;
  // The caller passes the binding captured before window.storyData is replaced
  // with the decrypted steps (which no longer carry salt/iv); fall back to a
  // live read for any other caller.
  const binding = payloadKey || getPayloadKey();
  if (!binding) return;
  sessionStorage.setItem(`telar_unlock_${storyId}`, JSON.stringify({ key, payloadKey: binding }));
}

/**
 * Derive encryption key from password and salt using PBKDF2.
 * @param {string} password - User-provided key
 * @param {Uint8Array} salt - Salt from encrypted data
 * @returns {Promise<CryptoKey>} Derived key for AES-GCM
 */
async function deriveKey(password, salt) {
  const encoder = new TextEncoder();
  const passwordKey = await crypto.subtle.importKey(
    'raw',
    encoder.encode(password),
    'PBKDF2',
    false,
    ['deriveKey']
  );

  return crypto.subtle.deriveKey(
    {
      name: 'PBKDF2',
      salt: salt,
      iterations: PBKDF2_ITERATIONS,
      hash: 'SHA-256',
    },
    passwordKey,
    { name: 'AES-GCM', length: 256 },
    false,
    ['decrypt']
  );
}

/**
 * The story identifier that the build bound into the envelope as additional
 * authenticated data. The template emits window.telarStoryId (the data_file
 * name) on every protected page; there is deliberately NO fallback to the
 * URL segment — the permalink slug equals the data-file stem only by
 * convention (not at all for `story-{number}` naming), so a URL-derived AAD
 * can silently decrypt-fail as a "wrong key" on a correct key. A missing
 * telarStoryId is a template bug; the console.warn names it so nobody
 * debugs the key instead. (The session-cache functions still use the URL
 * segment — cache identity doesn't need to match the AAD.)
 * @returns {string} Story identifier for AAD ('' if the template is broken)
 */
function getStoryAadId() {
  if (!window.telarStoryId) {
    console.warn('story-unlock: window.telarStoryId missing — the story ' +
      'template must emit it on protected pages; decryption will fail.');
    return '';
  }
  return window.telarStoryId;
}

/**
 * Decrypt a story envelope using AES-GCM.
 * @param {string} key - User-provided decryption key
 * @param {object} encryptedData - Object with salt, iv, ciphertext (base64)
 * @returns {Promise<object>} Decrypted payload: { steps, html }
 * @throws {Error} If decryption fails (wrong key, or an envelope bound to a
 *   different story id)
 */
async function decryptStory(key, encryptedData) {
  // Decode base64 values
  const salt = Uint8Array.from(atob(encryptedData.salt), c => c.charCodeAt(0));
  const iv = Uint8Array.from(atob(encryptedData.iv), c => c.charCodeAt(0));
  const ciphertext = Uint8Array.from(atob(encryptedData.ciphertext), c => c.charCodeAt(0));

  // Derive key
  const cryptoKey = await deriveKey(key, salt);

  // Decrypt; additionalData must byte-match the Python encrypt step's aad
  const decryptedBuffer = await crypto.subtle.decrypt(
    {
      name: 'AES-GCM',
      iv: iv,
      additionalData: new TextEncoder().encode(getStoryAadId()),
    },
    cryptoKey,
    ciphertext
  );

  // Decode JSON
  const decoder = new TextDecoder();
  const jsonString = decoder.decode(decryptedBuffer);
  return JSON.parse(jsonString);
}

/**
 * Get key from URL parameter if present.
 * @returns {string|null} Key from ?key= parameter or null
 */
function getKeyFromUrl() {
  const params = new URLSearchParams(window.location.search);
  return params.get('key');
}

/**
 * Show the unlock overlay.
 * Ensures overlay is a direct child of body for proper z-index stacking.
 */
function showUnlockOverlay() {
  const overlay = document.getElementById('story-unlock-overlay');
  if (overlay) {
    // Ensure overlay is at body level (workaround for HTML parsing issues)
    if (overlay.parentElement !== document.body) {
      document.body.appendChild(overlay);
    }
    overlay.classList.remove('d-none');
    overlay.classList.add('show');
    // Focus the key input
    const input = document.getElementById('unlock-key-input');
    if (input) {
      input.focus();
    }
  }
}

/**
 * Hide the unlock overlay with success animation.
 */
function hideUnlockOverlay() {
  const overlay = document.getElementById('story-unlock-overlay');
  if (overlay) {
    overlay.classList.add('success');
    setTimeout(() => {
      overlay.classList.remove('show');
      setTimeout(() => {
        overlay.classList.add('d-none');
      }, 300);
    }, 500);
  }
}

/**
 * Render LaTeX inside an element once the shared renderer exists.
 *
 * KaTeX loads through story.html's standard path (keyed on the page's
 * has_latex frontmatter); the CDN scripts race the unlock, so retry until
 * window.telarRenderLatex appears. When the story has no LaTeX the renderer
 * never appears and the retries lapse harmlessly.
 * @param {Element} element - Container whose math should render
 * @param {number} [attempt] - Internal retry counter
 */
function renderLatexWhenReady(element, attempt = 0) {
  if (window.telarRenderLatex) {
    window.telarRenderLatex(element);
    return;
  }
  if (attempt < 20) {
    setTimeout(() => renderLatexWhenReady(element, attempt + 1), 250);
  }
}

/**
 * Apply a decrypted envelope to the page.
 *
 * Single owner of the post-decryption sequence, shared by the fresh-unlock
 * and cached-key paths: inject the build-rendered step markup into the
 * hidden step pool, publish window.storyData in the same shape open stories
 * get, then dispatch telar:story-unlocked so main.js initialises the story
 * system on the injected DOM (card pool clones the steps exactly as it does
 * for open stories).
 * @param {object} payload - Decrypted envelope: { steps, html }
 * @param {string} key - The key that decrypted it (share-panel integration)
 * @throws {Error} If the payload does not carry the envelope shape
 */
function applyDecryptedPayload(payload, key) {
  if (!payload || !Array.isArray(payload.steps) || typeof payload.html !== 'string') {
    throw new Error('Decrypted payload is not a { steps, html } envelope');
  }

  const container = document.getElementById('encrypted-steps-container');
  if (!container) {
    throw new Error('encrypted-steps-container not found in the step pool');
  }
  container.innerHTML = payload.html;

  const firstStep = payload.steps[0]?._metadata ? payload.steps[1] : payload.steps[0];
  window.storyData = {
    steps: payload.steps,
    firstObject: firstStep?.object || '',
  };

  // Expose the key for share panel integration
  window.telarStoryKey = key;

  // Render math into the pool BEFORE the event: main.js clones cards from
  // the pool synchronously in its unlock handler, and clones inherit the
  // pool's state. If KaTeX is still loading, the retries render the pool
  // for every later clone — the same CDN race open stories run.
  renderLatexWhenReady(container);

  window.dispatchEvent(new CustomEvent('telar:story-unlocked'));
}

/**
 * Show error state on the unlock form.
 * @param {string} message - Error message to display
 */
function showUnlockError(message) {
  const form = document.getElementById('unlock-form');
  const input = document.getElementById('unlock-key-input');
  const errorEl = document.getElementById('unlock-error');

  if (form) {
    form.classList.add('shake');
    setTimeout(() => form.classList.remove('shake'), 500);
  }

  if (input) {
    input.value = '';
    input.focus();
  }

  if (errorEl) {
    errorEl.textContent = message;
    errorEl.classList.remove('d-none');
  }
}

/**
 * Attempt to unlock the story with the provided key.
 * @param {string} key - User-provided key
 * @returns {Promise<boolean>} True if unlock succeeded
 */
async function attemptUnlock(key) {
  if (!key) {
    showUnlockError(window.telarLang?.unlock?.errorEmpty || 'Please enter a key');
    return false;
  }

  try {
    // Capture the payload binding before window.storyData is replaced below
    // (the decrypted form carries no salt/iv to bind to).
    const payloadKey = getPayloadKey();

    const payload = await decryptStory(key, window.storyData);

    // Cache only the key (+ payload binding), not the decrypted plaintext.
    cacheDecryption(key, payloadKey);

    applyDecryptedPayload(payload, key);

    hideUnlockOverlay();

    return true;
  } catch (e) {
    console.error('Decryption failed:', e);
    showUnlockError(window.telarLang?.unlock?.errorIncorrect || 'Incorrect key. Please try again.');
    return false;
  }
}

/**
 * Initialize unlock form event handlers.
 */
function initializeUnlockForm() {
  const form = document.getElementById('unlock-form');
  const input = document.getElementById('unlock-key-input');
  const toggleBtn = document.getElementById('toggle-key-visibility');

  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const key = input?.value || '';
      await attemptUnlock(key);
    });
  }

  if (toggleBtn && input) {
    toggleBtn.addEventListener('click', () => {
      const isPassword = input.type === 'password';
      input.type = isPassword ? 'text' : 'password';
      toggleBtn.innerHTML = isPassword
        ? '<svg class="icon icon-eye-off" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 10.747 10.747 0 0 1-1.444 2.49"/><path d="M14.084 14.158a3 3 0 0 1-4.242-4.242"/><path d="M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143"/><path d="m2 2 20 20"/></svg>'
        : '<svg class="icon icon-eye" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/></svg>';
    });
  }
}

/**
 * Main initialization for story unlock.
 * Called before the main story script runs.
 */
async function initializeStoryUnlock() {
  if (!isStoryEncrypted()) {
    // Story is not encrypted, nothing to do
    return;
  }

  // Check for a cached unlock. The cache holds only the key, so re-derive the
  // plaintext here rather than reading it from sessionStorage.
  const cached = getCachedDecryption();
  if (cached && cached.key) {
    try {
      const payload = await decryptStory(cached.key, window.storyData);

      // Ensure overlay is hidden when loading from cache (no animation)
      const overlay = document.getElementById('story-unlock-overlay');
      if (overlay) {
        overlay.classList.add('d-none');
        overlay.classList.remove('show');
      }

      // Same apply path as a fresh unlock — including the unlock event,
      // which main.js is always still waiting for at this point (this async
      // resolution cannot run before main.js's DOMContentLoaded handler has
      // registered the listener in the same task).
      applyDecryptedPayload(payload, cached.key);
      return;
    } catch (e) {
      // The cached key no longer decrypts (e.g. the story was re-encrypted).
      // Drop the stale entry and fall through to the unlock prompt.
      console.warn('[Telar Unlock] Cached key failed to decrypt; prompting for key.');
      const storyId = getStoryId();
      if (storyId !== 'unknown') sessionStorage.removeItem(`telar_unlock_${storyId}`);
    }
  }

  // Check for key in URL
  const urlKey = getKeyFromUrl();
  if (urlKey) {
    const success = await attemptUnlock(urlKey);
    if (success) {
      return;
    }
    // If URL key failed, fall through to show overlay
  }

  // Show unlock overlay and wait
  showUnlockOverlay();
  initializeUnlockForm();
}

// Run initialization when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeStoryUnlock);
} else {
  initializeStoryUnlock();
}

// Consumed by tests/js/story-unlock.test.js (loaded as a side-effect script
// in jsdom; a plain script has no module exports to import).
window.TelarUnlock = {
  isStoryEncrypted,
  attemptUnlock,
  decryptStory,
  applyDecryptedPayload,
};
