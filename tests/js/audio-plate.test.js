/**
 * The audio plate names a peaks file only where the build has one.
 *
 * `story.html` lists the audio objects that have a peaks file in
 * `window.audioPeaks`, read off Jekyll's static files. The plate builds the
 * peaks URL for those and passes none for the rest, and `createAudioPlayer`
 * decodes the audio itself when it is given none — so a site built without
 * `audiowaveform` asks the server for nothing it does not have.
 *
 * @version v1.8.0
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

const players = vi.hoisted(() => []);

vi.mock('../../assets/js/telar-story/audio-card.js', () => ({
  createAudioPlayer: (el, audioUrl, peaksUrl) => { players.push({ audioUrl, peaksUrl }); },
  activateAudioCard: () => {},
  deactivateAudioCard: () => {},
  updateAudioClip: () => {},
  hasAudioPlayer: () => false,
  applyAudioClipEndDim: () => {},
}));

import { AudioPlate } from '../../assets/js/telar-story/plates/audio-plate.js';

const build = async (objectId) => {
  const plate = new AudioPlate(document.createElement('div'), objectId, 1, 10, null);
  await plate.load();
  return players.at(-1);
};

beforeEach(() => {
  players.length = 0;
  window.history.replaceState(null, '', '/telar/stories/your-story/');
  window.audioObjects = { rec: 'mp3', bare: 'ogg' };
});

afterEach(() => {
  delete window.audioObjects;
  delete window.audioPeaks;
});

describe('AudioPlate peaks', () => {
  it('passes the peaks file for an object the build has one for', async () => {
    window.audioPeaks = ['rec'];
    const player = await build('rec');
    expect(player.audioUrl).toBe('/telar/telar-content/objects/rec.mp3');
    expect(player.peaksUrl).toBe('/telar/assets/audio/peaks/rec.json');
  });

  it('passes none for an object the build has no peaks file for', async () => {
    window.audioPeaks = ['rec'];
    const player = await build('bare');
    expect(player.audioUrl).toBe('/telar/telar-content/objects/bare.ogg');
    expect(player.peaksUrl).toBeNull();
  });

  it('passes none when the page lists no peaks at all', async () => {
    const player = await build('rec');
    expect(player.peaksUrl).toBeNull();
  });
});
