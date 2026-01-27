/**
 * Tests for Telar Story – Panel System (content check functions)
 *
 * Tests stepHasLayer1Content and stepHasLayer2Content, which determine
 * whether a story step has panel content available. These are pure
 * predicate functions with no DOM or Bootstrap dependencies.
 *
 * @version v0.7.0-beta
 */

import { describe, it, expect } from 'vitest';
import { stepHasLayer1Content, stepHasLayer2Content } from '../../assets/js/telar-story/panels.js';

// ── stepHasLayer1Content ─────────────────────────────────────────────────────

describe('stepHasLayer1Content', () => {
  it('returns true when layer1_title is present', () => {
    expect(stepHasLayer1Content({ layer1_title: 'Title' })).toBe(true);
  });

  it('returns true when layer1_text is present', () => {
    expect(stepHasLayer1Content({ layer1_text: '<p>Content</p>' })).toBe(true);
  });

  it('returns false for null step', () => {
    expect(stepHasLayer1Content(null)).toBe(false);
  });

  it('returns false for empty and whitespace strings', () => {
    expect(stepHasLayer1Content({ layer1_title: '', layer1_text: '   ' })).toBe(false);
  });

  it('returns falsy for step with no layer1 fields', () => {
    expect(stepHasLayer1Content({ object: 'obj-1', x: 0.5 })).toBeFalsy();
  });
});

// ── stepHasLayer2Content ─────────────────────────────────────────────────────

describe('stepHasLayer2Content', () => {
  it('returns true when layer2_title is present', () => {
    expect(stepHasLayer2Content({ layer2_title: 'Title' })).toBe(true);
  });

  it('returns true when layer2_text is present', () => {
    expect(stepHasLayer2Content({ layer2_text: '<p>Content</p>' })).toBe(true);
  });

  it('returns false for null step', () => {
    expect(stepHasLayer2Content(null)).toBe(false);
  });

  it('returns false for empty and whitespace strings', () => {
    expect(stepHasLayer2Content({ layer2_title: '', layer2_text: '   ' })).toBe(false);
  });

  it('returns falsy for step with only layer1 content', () => {
    expect(stepHasLayer2Content({ layer1_title: 'Title', layer1_text: 'Text' })).toBeFalsy();
  });
});
