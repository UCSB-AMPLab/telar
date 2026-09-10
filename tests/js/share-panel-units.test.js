/**
 * Unit tests for the share panel's warning decision.
 *
 * `warningState` is the whole of what raises either pair of warnings, and it
 * takes plain values, so every combination is reachable here without a panel.
 * The characterisation suite in `share-panel.test.js` covers the combinations
 * a rendered page can actually produce; this covers the rest of the table,
 * including the one a story page cannot reach.
 *
 * @version v1.7.0
 */

import { describe, it, expect } from 'vitest';

import { warningState, setWarning } from '../../assets/js/share-panel/warnings.js';

const URL_ = 'https://example.org/telar/stories/locked-fixture/';
const KEY = 's3cr3tkey';

describe('warningState', () => {
  const cases = [
    ['nothing set', [false, null, false, ''], { key: false, protectedStory: false }],
    ['an open story chosen', [false, null, false, URL_], { key: false, protectedStory: false }],
    ['a protected story chosen', [true, null, false, URL_], { key: false, protectedStory: true }],
    ['a protected story with a key, key off', [true, KEY, false, URL_], { key: false, protectedStory: true }],
    ['a protected story with a key, key on', [true, KEY, true, URL_], { key: true, protectedStory: true }],
    ['a protected story, key on but no key held', [true, null, true, URL_], { key: false, protectedStory: true }],
    ['a key on an unprotected story', [false, KEY, true, URL_], { key: false, protectedStory: false }],
    ['a protected story with a key but no URL', [true, KEY, true, ''], { key: true, protectedStory: false }],
  ];

  cases.forEach(([name, args, expected]) => {
    it(`raises ${expected.key ? 'the key pair' : 'no key pair'} and ${expected.protectedStory ? 'the protected pair' : 'no protected pair'} for ${name}`, () => {
      expect(warningState(...args)).toEqual(expected);
    });
  });
});

describe('setWarning', () => {
  const warning = () => {
    const element = document.createElement('p');
    element.className = 'share-warning d-none';
    return element;
  };

  it('reveals a warning that is to be shown', () => {
    const element = warning();
    setWarning(element, true);

    expect(element.className).toBe('share-warning');
  });

  it('leaves a hidden warning hidden', () => {
    const element = warning();
    setWarning(element, false);

    expect(element.className).toBe('share-warning d-none');
  });

  it('hides a warning that was showing', () => {
    const element = warning();
    setWarning(element, true);
    setWarning(element, false);

    expect(element.className).toBe('share-warning d-none');
  });

  it('does nothing when the branch on the page has no such warning', () => {
    expect(() => setWarning(null, true)).not.toThrow();
  });
});
