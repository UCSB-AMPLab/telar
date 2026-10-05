/**
 * Test helpers shared across the JS suites.
 *
 * The DOM lookup, the scripted fetch and the flush that the page-level suites
 * all use, in one place so they cannot drift apart. The page fixtures
 * re-export what their suites import from them.
 *
 * @version v1.8.0
 */

import { vi } from 'vitest';

export const el = (id) => document.getElementById(id);

/**
 * A fetch stub answering from a URL -> body map; anything else rejects.
 *
 * A body that is an Error rejects with it. A body of `{ notOk: true, body }`
 * answers 404 with `body` as its JSON. Returns the list of URLs asked for.
 */
export function stubFetch(responses) {
  const calls = [];
  vi.stubGlobal('fetch', vi.fn((url) => {
    calls.push(url);
    if (!(url in responses)) return Promise.reject(new Error(`unscripted fetch: ${url}`));
    const body = responses[url];
    if (body instanceof Error) return Promise.reject(body);
    if (body && body.notOk) {
      return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve(body.body) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
  }));
  return calls;
}

/** Let promise chains and a timer turn run out, three times over. */
export async function flush() {
  for (let round = 0; round < 3; round++) {
    for (let i = 0; i < 20; i++) await Promise.resolve();
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}
