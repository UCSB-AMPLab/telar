/**
 * The object page's viewer pane has the authoring aspect.
 *
 * An author captures a step's zoom in that pane, and a story replays it
 * against a frame of AUTHORING_ASPECT; the two agree for every image only
 * when the pane has that aspect. The stylesheet cannot import the constant,
 * so this reads the rule and holds the two numbers together.
 *
 * @version v1.8.0
 */

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { AUTHORING_ASPECT } from '../../assets/js/telar-story/authoring-frame.js';

// jsdom gives import.meta.url an http scheme, so the path is resolved from the
// project root vitest runs in.
const scss = readFileSync(resolve(process.cwd(), '_sass/_viewer.scss'), 'utf8');

/** The declarations of the image pane's own rule, comments removed. */
function paneRule() {
  const bare = scss.replace(/\/\*[\s\S]*?\*\//g, '');
  const match = bare.match(/#object-viewer\.viewer-image\s*\{([^}]*)\}/);
  expect(match, 'the #object-viewer.viewer-image rule').not.toBeNull();
  return match[1];
}

describe('the object page viewer pane', () => {
  it('declares the authoring aspect', () => {
    const declared = paneRule().match(/aspect-ratio:\s*([\d.]+)(?:\s*\/\s*([\d.]+))?\s*;/);
    expect(declared, 'an aspect-ratio declaration').not.toBeNull();
    const ratio = Number(declared[1]) / Number(declared[2] ?? 1);
    expect(ratio).toBe(AUTHORING_ASPECT);
  });

  it('caps its width at the height cap times the same aspect', () => {
    const cap = paneRule().match(/max-width:\s*min\(\s*100%\s*,\s*calc\(\s*80vh\s*\*\s*([\d.]+)\s*\)\s*\)/);
    expect(cap, 'a max-width tied to 80vh').not.toBeNull();
    expect(Number(cap[1])).toBe(AUTHORING_ASPECT);
  });
});
