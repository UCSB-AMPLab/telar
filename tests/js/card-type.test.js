/**
 * Tests for Telar Story – Card Type Detection
 *
 * Verifies detectCardType returns the correct card type based on step data.
 * IIIF is the default for Phase 1 backward compatibility (COMPAT-02).
 *
 * @version v0.10.0-beta
 */

import { describe, it, expect } from 'vitest';
import { detectCardType, extractVideoId } from '../../assets/js/telar-story/card-type.js';

describe('detectCardType', () => {
  it("returns 'iiif' when no cardType field and objectId is present", () => {
    expect(detectCardType({ objectId: 'obj-1' })).toBe('iiif');
  });

  it("returns explicit cardType when provided (override wins)", () => {
    expect(detectCardType({ cardType: 'video', objectId: 'obj-1' })).toBe('video');
  });

  it("returns 'text-only' when objectId is empty string", () => {
    expect(detectCardType({ objectId: '' })).toBe('text-only');
  });

  it("returns 'text-only' when objectId is undefined", () => {
    expect(detectCardType({ objectId: undefined })).toBe('text-only');
  });
});

describe('video URL detection (VID-06)', () => {
  // YouTube variants
  it("returns 'youtube' for youtube.com/watch URL", () => {
    expect(detectCardType({ objectId: 'vid1', source_url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ' })).toBe('youtube');
  });

  it("returns 'youtube' for youtu.be short URL", () => {
    expect(detectCardType({ objectId: 'vid1', source_url: 'https://youtu.be/dQw4w9WgXcQ' })).toBe('youtube');
  });

  it("returns 'youtube' for youtube.com/embed URL", () => {
    expect(detectCardType({ objectId: 'vid1', source_url: 'https://www.youtube.com/embed/dQw4w9WgXcQ' })).toBe('youtube');
  });

  it("returns 'youtube' for youtube.com/shorts URL", () => {
    expect(detectCardType({ objectId: 'vid1', source_url: 'https://www.youtube.com/shorts/dQw4w9WgXcQ' })).toBe('youtube');
  });

  // Vimeo variants
  it("returns 'vimeo' for vimeo.com URL", () => {
    expect(detectCardType({ objectId: 'vid1', source_url: 'https://vimeo.com/123456789' })).toBe('vimeo');
  });

  it("returns 'vimeo' for vimeo.com/video URL", () => {
    expect(detectCardType({ objectId: 'vid1', source_url: 'https://vimeo.com/video/123456789' })).toBe('vimeo');
  });

  // Google Drive variants
  it("returns 'google-drive' for drive.google.com/file/d/ URL", () => {
    expect(detectCardType({ objectId: 'vid1', source_url: 'https://drive.google.com/file/d/abc123/view' })).toBe('google-drive');
  });

  it("returns 'google-drive' for drive.google.com/open?id= URL", () => {
    expect(detectCardType({ objectId: 'vid1', source_url: 'https://drive.google.com/open?id=abc123' })).toBe('google-drive');
  });

  // Non-video source_url falls back to 'iiif'
  it("returns 'iiif' for a non-video source_url", () => {
    expect(detectCardType({ objectId: 'img1', source_url: 'https://gallica.bnf.fr/manifest.json' })).toBe('iiif');
  });

  it("returns 'iiif' when no source_url present", () => {
    expect(detectCardType({ objectId: 'img1' })).toBe('iiif');
  });

  // Priority rules
  it("returns 'text-only' when objectId is empty even if source_url is a YouTube URL", () => {
    expect(detectCardType({ objectId: '', source_url: 'https://youtube.com/watch?v=abc' })).toBe('text-only');
  });

  it("returns explicit cardType even when source_url is a YouTube URL", () => {
    expect(detectCardType({ cardType: 'custom', objectId: 'x', source_url: 'https://youtube.com/watch?v=abc' })).toBe('custom');
  });
});

describe('audio file extension detection (AUD-07)', () => {
  it("returns 'audio' for file_path ending in .mp3", () => {
    expect(detectCardType({ objectId: 'audio-1', file_path: 'objects/interview.mp3' })).toBe('audio');
  });

  it("returns 'audio' for file_path ending in .ogg", () => {
    expect(detectCardType({ objectId: 'audio-1', file_path: 'objects/interview.ogg' })).toBe('audio');
  });

  it("returns 'audio' for file_path ending in .m4a", () => {
    expect(detectCardType({ objectId: 'audio-1', file_path: 'objects/interview.m4a' })).toBe('audio');
  });

  it("returns 'audio' for uppercase extension .MP3", () => {
    expect(detectCardType({ objectId: 'audio-1', file_path: 'objects/interview.MP3' })).toBe('audio');
  });

  it("returns 'iiif' when file_path is absent (no false positive)", () => {
    expect(detectCardType({ objectId: 'img-1' })).toBe('iiif');
  });

  it("returns 'iiif' when file_path ends in .jpg (non-audio extension)", () => {
    expect(detectCardType({ objectId: 'img-1', file_path: 'objects/photo.jpg' })).toBe('iiif');
  });

  it("explicit cardType override still wins over audio file_path detection", () => {
    expect(detectCardType({ cardType: 'iiif', objectId: 'audio-1', file_path: 'objects/interview.mp3' })).toBe('iiif');
  });

  it("text-only (empty objectId) still wins over audio file_path", () => {
    expect(detectCardType({ objectId: '', file_path: 'objects/interview.mp3' })).toBe('text-only');
  });
});

describe('extractVideoId', () => {
  it("extracts YouTube video ID from youtube.com/watch URL", () => {
    expect(extractVideoId('youtube', 'https://www.youtube.com/watch?v=dQw4w9WgXcQ')).toBe('dQw4w9WgXcQ');
  });

  it("extracts Vimeo video ID", () => {
    expect(extractVideoId('vimeo', 'https://vimeo.com/123456789')).toBe('123456789');
  });

  it("extracts Google Drive file ID from file/d/ URL", () => {
    expect(extractVideoId('google-drive', 'https://drive.google.com/file/d/abc123/view')).toBe('abc123');
  });
});
