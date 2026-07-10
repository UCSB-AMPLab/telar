/**
 * Tests for assets/js/story-unlock.js
 *
 * The decrypt fixture (tests/fixtures/unlock-envelope.json) is a
 * cross-language vector produced by scripts/telar/encryption.py, so the
 * round-trip test proves the JS decrypt path matches the Python encrypt
 * path — PBKDF2 parameters, AES-GCM layout, and the story-id AAD binding.
 *
 * story-unlock.js is a standalone script (not part of the esbuild bundle);
 * it is loaded once as a side-effect import and exercised through its
 * window.TelarUnlock surface.
 *
 * @version v1.6.0
 */

import { describe, it, expect, beforeAll, beforeEach } from 'vitest';
import { webcrypto } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(
  fs.readFileSync(path.join(here, '../fixtures/unlock-envelope.json'), 'utf8')
);

beforeAll(async () => {
  // jsdom has no SubtleCrypto; the script calls window.crypto.subtle.
  if (!window.crypto?.subtle) {
    Object.defineProperty(window, 'crypto', { value: webcrypto, configurable: true });
  }
  window.telarStoryId = fixture.aad;
  window.storyData = fixture.envelope;
  document.body.innerHTML =
    '<div class="step-data"><div id="encrypted-steps-container"></div></div>';
  await import('../../assets/js/story-unlock.js');
});

beforeEach(() => {
  window.telarStoryId = fixture.aad;
  document.body.innerHTML =
    '<div class="step-data"><div id="encrypted-steps-container"></div></div>';
});

describe('decryptStory (cross-language vector)', () => {
  it('decrypts a Python-produced envelope to the {steps, html} payload', async () => {
    const payload = await window.TelarUnlock.decryptStory(fixture.key, fixture.envelope);
    expect(payload).toEqual(fixture.payload);
  });

  it('rejects when the page story id does not match the envelope AAD', async () => {
    window.telarStoryId = 'a-different-story';
    await expect(
      window.TelarUnlock.decryptStory(fixture.key, fixture.envelope)
    ).rejects.toThrow();
  });

  it('rejects a wrong key', async () => {
    await expect(
      window.TelarUnlock.decryptStory('not-the-key', fixture.envelope)
    ).rejects.toThrow();
  });
});

describe('applyDecryptedPayload', () => {
  it('injects the rendered steps, publishes storyData, and dispatches the unlock event', () => {
    let unlocked = false;
    window.addEventListener('telar:story-unlocked', () => { unlocked = true; }, { once: true });

    window.TelarUnlock.applyDecryptedPayload(fixture.payload, fixture.key);

    const container = document.getElementById('encrypted-steps-container');
    expect(container.querySelector('.story-step[data-step="1"]')).not.toBeNull();
    expect(container.querySelector('.step-question').textContent).toBe('Fixture question one');
    expect(window.storyData.steps).toEqual(fixture.payload.steps);
    expect(window.storyData.firstObject).toBe('fixture-obj');
    expect(window.telarStoryKey).toBe(fixture.key);
    expect(unlocked).toBe(true);
  });

  it('refuses a payload that is not a {steps, html} envelope', () => {
    expect(() =>
      window.TelarUnlock.applyDecryptedPayload(fixture.payload.steps, fixture.key)
    ).toThrow();
  });
});
