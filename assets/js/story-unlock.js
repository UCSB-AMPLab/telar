/**
 * Telar Story Unlock
 *
 * Handles client-side decryption of protected stories using the Web Crypto API.
 * When a story is encrypted, this module shows an unlock overlay and decrypts
 * the content when the user provides the correct key.
 *
 * Encryption uses AES-256-GCM with PBKDF2 key derivation (100,000 iterations),
 * matching the Python encryption in scripts/telar/encryption.py.
 *
 * @version v0.8.0-beta
 */

// PBKDF2 iterations — must match Python encryption
const PBKDF2_ITERATIONS = 100000;

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
 * Get cached decryption from sessionStorage.
 * @returns {object|null} Object with steps and key, or null
 */
function getCachedDecryption() {
  const storyId = getStoryId();
  const cached = sessionStorage.getItem(`telar_unlock_${storyId}`);
  if (cached) {
    try {
      const parsed = JSON.parse(cached);
      // Handle both old format (array) and new format (object with steps/key)
      if (Array.isArray(parsed)) {
        // Old cache format - just steps, no key
        return { steps: parsed, key: null };
      }
      return parsed;
    } catch (e) {
      return null;
    }
  }
  return null;
}

/**
 * Cache successful decryption in sessionStorage.
 * @param {object} decryptedData - The decrypted story data
 * @param {string} key - The decryption key (for share panel integration)
 */
function cacheDecryption(decryptedData, key) {
  const storyId = getStoryId();
  sessionStorage.setItem(`telar_unlock_${storyId}`, JSON.stringify({
    steps: decryptedData,
    key: key
  }));
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
 * Decrypt story data using AES-GCM.
 * @param {string} key - User-provided decryption key
 * @param {object} encryptedData - Object with salt, iv, ciphertext (base64)
 * @returns {Promise<object>} Decrypted story steps array
 * @throws {Error} If decryption fails
 */
async function decryptStory(key, encryptedData) {
  // Decode base64 values
  const salt = Uint8Array.from(atob(encryptedData.salt), c => c.charCodeAt(0));
  const iv = Uint8Array.from(atob(encryptedData.iv), c => c.charCodeAt(0));
  const ciphertext = Uint8Array.from(atob(encryptedData.ciphertext), c => c.charCodeAt(0));

  // Derive key
  const cryptoKey = await deriveKey(key, salt);

  // Decrypt
  const decryptedBuffer = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: iv },
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
 * Simple markdown to HTML conversion for step content.
 * Handles basic formatting: bold, italic, links, paragraphs.
 * @param {string} text - Markdown text
 * @returns {string} HTML string
 */
function simpleMarkdown(text) {
  if (!text) return '';
  return text
    // Bold
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/__(.+?)__/g, '<strong>$1</strong>')
    // Italic
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/_(.+?)_/g, '<em>$1</em>')
    // Links
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>')
    // Line breaks to paragraphs
    .split(/\n\n+/)
    .map(p => `<p>${p.trim()}</p>`)
    .join('\n');
}

/**
 * Render story steps dynamically after decryption.
 * @param {Array} steps - Decrypted steps array
 */
function renderDecryptedSteps(steps) {
  // Find the story-steps container (parent of intro step)
  const storySteps = document.querySelector('.story-steps');
  if (!storySteps) {
    console.error('Story steps container not found');
    return;
  }

  // Remove the placeholder container if it exists
  const placeholder = document.getElementById('encrypted-steps-container');
  if (placeholder) {
    placeholder.remove();
  }

  // Filter out metadata
  const actualSteps = steps.filter(step => !step._metadata);

  actualSteps.forEach((step, index) => {
    const isLast = index === actualSteps.length - 1;
    const stepIndex = index + 1; // +1 because intro is step 0
    const stepEl = document.createElement('div');
    stepEl.className = 'story-step';
    stepEl.setAttribute('data-step', step.step || '');
    stepEl.setAttribute('data-step-index', stepIndex);
    stepEl.setAttribute('data-object', step.object || '');
    stepEl.setAttribute('data-x', step.x || '');
    stepEl.setAttribute('data-y', step.y || '');
    stepEl.setAttribute('data-zoom', step.zoom || '');
    stepEl.setAttribute('data-region', step.region || '');
    stepEl.style.zIndex = step.step || stepIndex;

    // Build inner HTML
    let html = '<div class="step-content">';

    // Question
    html += `<h2 class="step-question">${step.question || ''}</h2>`;

    // Answer (with markdown conversion)
    html += `<div class="step-answer">${simpleMarkdown(step.answer || '')}</div>`;

    // Layer 1 panel trigger
    if (step.layer1_title || step.layer1_text) {
      const buttonText = step.layer1_button || 'Learn more';
      html += `<p class="mt-3">
        <button class="panel-trigger" data-panel="layer1" data-step="${step.step}">
          ${buttonText} →
        </button>
      </p>`;
    }

    html += '</div>';
    stepEl.innerHTML = html;

    storySteps.appendChild(stepEl);
  });

  console.log(`[Telar Unlock] Rendered ${actualSteps.length} decrypted steps`);
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
    showUnlockError('Please enter a key');
    return false;
  }

  try {
    const decryptedSteps = await decryptStory(key, window.storyData);

    // Success! Update storyData and cache
    const firstStep = decryptedSteps[0]?._metadata ? decryptedSteps[1] : decryptedSteps[0];
    window.storyData = {
      steps: decryptedSteps,
      firstObject: firstStep?.object || '',
    };

    // Expose the key for share panel integration
    window.telarStoryKey = key;

    cacheDecryption(decryptedSteps, key);

    // Render the decrypted steps into the DOM
    renderDecryptedSteps(decryptedSteps);

    hideUnlockOverlay();

    // Trigger story initialization
    window.dispatchEvent(new CustomEvent('telar:story-unlocked'));

    return true;
  } catch (e) {
    console.error('Decryption failed:', e);
    showUnlockError('Incorrect key. Please try again.');
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
        ? '<i class="bi bi-eye-slash"></i>'
        : '<i class="bi bi-eye"></i>';
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

  // Check for cached decryption
  const cached = getCachedDecryption();
  if (cached) {
    const steps = cached.steps;
    const firstStep = steps[0]?._metadata ? steps[1] : steps[0];
    window.storyData = {
      steps: steps,
      firstObject: firstStep?.object || '',
    };

    // Restore the key for share panel integration
    if (cached.key) {
      window.telarStoryKey = cached.key;
    }

    // Ensure overlay is hidden when loading from cache
    const overlay = document.getElementById('story-unlock-overlay');
    if (overlay) {
      overlay.classList.add('d-none');
      overlay.classList.remove('show');
    }

    // Render steps from cache
    renderDecryptedSteps(steps);
    return;
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

  // Prevent main story initialization until unlocked
  window.telarStoryBlocked = true;
}

// Run initialization when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeStoryUnlock);
} else {
  initializeStoryUnlock();
}

// Export for testing
window.TelarUnlock = {
  isStoryEncrypted,
  attemptUnlock,
  decryptStory,
};
