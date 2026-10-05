/**
 * Tests for the kind label in the glossary panel.
 *
 * The line above an entry's title names its kind. The entry's page carries
 * the label on its `.glossary-content`, and telar.js reads it from the page
 * it fetched, so a link from a story and a link from the glossary index show
 * the same label. While the entry loads the label is hidden, so it never
 * names the kind of the entry shown before; a page without a label gets the
 * default kind's, which panels.html writes on the element.
 *
 * @version v1.8.0
 */

import { describe, it, expect, beforeAll, beforeEach, vi } from 'vitest';

class FakeOffcanvas {
  static getInstance() { return null; }
  show() {}
  hide() {}
}

const page = (attrs) => `<html><body><h1>Entry</h1>
  <div class="glossary-content" ${attrs}><p>Definition.</p></div></body></html>`;

let respond;
const fetchSpy = vi.fn(() => new Promise((resolve) => {
  respond = (html, ok = true) => resolve({ ok, text: () => Promise.resolve(html) });
}));

const kindLabel = () => document.querySelector('.glossary-term-prefix');
const afterTasks = () => new Promise((resolve) => setTimeout(resolve, 0));

async function openEntry(linkClass, pageHtml, ok = true) {
  const host = document.getElementById('host');
  host.innerHTML = `<a href="#" class="${linkClass}" data-term-id="x" data-term-url="/telar/glossary/x/">x</a>`;
  host.querySelector('a').click();
  const hiddenWhileLoading = kindLabel().style.visibility === 'hidden';
  respond(pageHtml, ok);
  await afterTasks();
  await afterTasks();
  return hiddenWhileLoading;
}

beforeAll(async () => {
  window.bootstrap = { Offcanvas: FakeOffcanvas };
  globalThis.fetch = fetchSpy;
  document.body.innerHTML = `
    <div id="host"></div>
    <div class="offcanvas" id="panel-glossary">
      <div class="glossary-term-prefix" data-default-label="Key term">Key term:</div>
      <h1 id="panel-glossary-title"></h1><div id="panel-glossary-content"></div>
    </div>`;
  await import('../../assets/js/telar.js');
  document.dispatchEvent(new Event('DOMContentLoaded'));
});

beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

describe('the glossary panel names the kind of the entry it shows', () => {
  it('shows the label the entry page carries, from a story link', async () => {
    await openEntry('glossary-inline-link',
      page('data-glossary-kind="source" data-glossary-kind-label="Primary source"'));
    expect(kindLabel().textContent).toBe('Primary source:');
    expect(kindLabel().style.visibility).toBe('');
  });

  it('shows the label the entry page carries, from the glossary index', async () => {
    await openEntry('glossary-term-link',
      page('data-glossary-kind="source" data-glossary-kind-label="Fuente primaria"'));
    expect(kindLabel().textContent).toBe('Fuente primaria:');
  });

  it('hides the label while an entry loads', async () => {
    await openEntry('glossary-inline-link',
      page('data-glossary-kind="source" data-glossary-kind-label="Primary source"'));
    const hidden = await openEntry('glossary-inline-link',
      page('data-glossary-kind="term" data-glossary-kind-label="Key term"'));
    expect(hidden).toBe(true);
    expect(kindLabel().textContent).toBe('Key term:');
  });

  it('falls back to the default kind for a page without a label', async () => {
    await openEntry('glossary-inline-link',
      page('data-glossary-kind="source" data-glossary-kind-label="Primary source"'));
    await openEntry('glossary-inline-link', page(''));
    expect(kindLabel().textContent).toBe('Key term:');
    expect(kindLabel().style.visibility).toBe('');
  });

  it('shows the default label again when the entry fails to load', async () => {
    await openEntry('glossary-inline-link',
      page('data-glossary-kind="source" data-glossary-kind-label="Primary source"'));
    await openEntry('glossary-inline-link', '', false);
    expect(kindLabel().textContent).toBe('Key term:');
    expect(kindLabel().style.visibility).toBe('');
  });
});
