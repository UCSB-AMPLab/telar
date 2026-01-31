/**
 * Tests for Telar Story – Shared Utilities
 *
 * Tests the three utility functions: getBasePath, fixImageUrls, and
 * calculateViewportPosition. These are the most purely testable functions
 * in the story module — getBasePath and fixImageUrls need jsdom for
 * window.location and document.createElement, while calculateViewportPosition
 * is pure maths with a mock viewport object.
 *
 * @version v0.7.0-beta
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { getBasePath, fixImageUrls, calculateViewportPosition } from '../../assets/js/telar-story/utils.js';

// ── getBasePath ──────────────────────────────────────────────────────────────

describe('getBasePath', () => {
  beforeEach(() => {
    delete window.location;
  });

  it('returns base path for subpath URL', () => {
    window.location = { pathname: '/telar/stories/story-1/' };
    expect(getBasePath()).toBe('/telar');
  });

  it('returns slash when path has exactly two segments', () => {
    window.location = { pathname: '/stories/story-1/' };
    expect(getBasePath()).toBe('/');
  });

  it('returns empty string for single segment', () => {
    window.location = { pathname: '/story-1/' };
    expect(getBasePath()).toBe('');
  });

  it('returns deeper base path for multi-segment prefix', () => {
    window.location = { pathname: '/site/telar/stories/story-1/' };
    expect(getBasePath()).toBe('/site/telar');
  });
});

// ── fixImageUrls ─────────────────────────────────────────────────────────────

describe('fixImageUrls', () => {
  it('prepends base path to site-relative image src', () => {
    const result = fixImageUrls('<img src="/assets/img/photo.jpg">', '/telar');
    const div = document.createElement('div');
    div.innerHTML = result;
    expect(div.querySelector('img').getAttribute('src')).toBe('/telar/assets/img/photo.jpg');
  });

  it('does not modify protocol-relative URLs', () => {
    const result = fixImageUrls('<img src="//cdn.example.com/img.jpg">', '/telar');
    const div = document.createElement('div');
    div.innerHTML = result;
    expect(div.querySelector('img').getAttribute('src')).toBe('//cdn.example.com/img.jpg');
  });

  it('does not modify absolute URLs', () => {
    const result = fixImageUrls('<img src="https://example.com/img.jpg">', '/telar');
    const div = document.createElement('div');
    div.innerHTML = result;
    expect(div.querySelector('img').getAttribute('src')).toBe('https://example.com/img.jpg');
  });

  it('handles multiple images with mixed URL types', () => {
    const html = '<img src="/local/a.jpg"><img src="https://ext.com/b.jpg"><img src="/local/c.jpg">';
    const result = fixImageUrls(html, '/base');
    const div = document.createElement('div');
    div.innerHTML = result;
    const imgs = div.querySelectorAll('img');
    expect(imgs[0].getAttribute('src')).toBe('/base/local/a.jpg');
    expect(imgs[1].getAttribute('src')).toBe('https://ext.com/b.jpg');
    expect(imgs[2].getAttribute('src')).toBe('/base/local/c.jpg');
  });

  it('handles empty base path', () => {
    const result = fixImageUrls('<img src="/assets/img/photo.jpg">', '');
    const div = document.createElement('div');
    div.innerHTML = result;
    expect(div.querySelector('img').getAttribute('src')).toBe('/assets/img/photo.jpg');
  });

  it('handles HTML with no images', () => {
    const html = '<p>No images here</p>';
    const result = fixImageUrls(html, '/telar');
    const div = document.createElement('div');
    div.innerHTML = result;
    expect(div.querySelector('p').textContent).toBe('No images here');
  });
});

// ── calculateViewportPosition ────────────────────────────────────────────────

function createMockViewport(homeZoom, bounds) {
  return {
    getHomeZoom: () => homeZoom,
    getHomeBounds: () => bounds,
  };
}

describe('calculateViewportPosition', () => {
  it('calculates position at origin with 1x zoom', () => {
    const viewport = createMockViewport(1.0, { x: 0, y: 0, width: 1, height: 1 });
    const result = calculateViewportPosition(viewport, 0, 0, 1);
    expect(result.point.x).toBe(0);
    expect(result.point.y).toBe(0);
    expect(result.actualZoom).toBe(1.0);
  });

  it('calculates position at centre', () => {
    const viewport = createMockViewport(1.0, { x: 0, y: 0, width: 1, height: 0.75 });
    const result = calculateViewportPosition(viewport, 0.5, 0.5, 1);
    expect(result.point.x).toBe(0.5);
    expect(result.point.y).toBe(0.375);
    expect(result.actualZoom).toBe(1.0);
  });

  it('applies zoom multiplier', () => {
    const viewport = createMockViewport(2.0, { x: 0, y: 0, width: 1, height: 1 });
    const result = calculateViewportPosition(viewport, 0.5, 0.5, 3);
    expect(result.point.x).toBe(0.5);
    expect(result.point.y).toBe(0.5);
    expect(result.actualZoom).toBe(6.0);
  });

  it('handles non-zero bounds origin', () => {
    const viewport = createMockViewport(1.5, { x: 0.1, y: 0.2, width: 0.8, height: 0.6 });
    const result = calculateViewportPosition(viewport, 0.5, 0.5, 2);
    expect(result.point.x).toBeCloseTo(0.5);
    expect(result.point.y).toBeCloseTo(0.5);
    expect(result.actualZoom).toBe(3.0);
  });
});
