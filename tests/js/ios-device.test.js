/**
 * Tests for Telar Story – iOS Device Detection
 *
 * isIOSDevice decides whether a story gets button navigation because it is
 * running on an iPhone or iPad. Safari on iPadOS sends a Macintosh user agent,
 * so a Macintosh user agent with more than one touch point counts as an iPad;
 * a desktop Mac reports no touch points.
 *
 * @version v1.8.0
 */

import { describe, it, expect } from 'vitest';
import { isIOSDevice } from '../../assets/js/telar-story/ios-device.js';

const IPHONE_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 '
  + '(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1';
const IPAD_UA = 'Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 '
  + '(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1';
const MAC_UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 '
  + '(KHTML, like Gecko) Version/17.0 Safari/605.1.15';
const WINDOWS_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
  + '(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36';

describe('isIOSDevice', () => {
  it('is true for an iPhone', () => {
    expect(isIOSDevice(IPHONE_UA, 5)).toBe(true);
  });

  it('is true for an iPad that names itself', () => {
    expect(isIOSDevice(IPAD_UA, 5)).toBe(true);
  });

  it('is true for iPadOS Safari, which sends a Macintosh user agent, with touch points', () => {
    expect(isIOSDevice(MAC_UA, 5)).toBe(true);
  });

  it('is false for a desktop Mac, which reports no touch points', () => {
    expect(isIOSDevice(MAC_UA, 0)).toBe(false);
  });

  it('is false for a Windows touch laptop', () => {
    expect(isIOSDevice(WINDOWS_UA, 10)).toBe(false);
  });
});
