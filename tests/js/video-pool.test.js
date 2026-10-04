/**
 * Tests for the video player pool's eviction.
 *
 * At most three players exist at once, and building a fourth evicts the one
 * farthest from the scene being built. Google Drive embeds need no player
 * API, so four of them can be built in the test document and the real
 * eviction runs: the evicted wrapper is marked destroyed, and its plate is
 * left with no player in it, so re-entering the scene builds one rather than
 * a second beside the first.
 *
 * @version v1.8.0
 */

import { describe, it, expect, afterEach } from 'vitest';
import { createVideoPlayer, destroyVideoPlayer, hasVideoPlayer } from '../../assets/js/telar-story/video-card.js';

const built = [];

function drivePlate(sceneIndex) {
  const plate = document.createElement('div');
  plate.className = 'viewer-plate';
  document.body.appendChild(plate);
  const wrapper = createVideoPlayer(plate, 'google-drive', `file-${sceneIndex}`, { sceneIndex });
  built.push(wrapper);
  return { plate, wrapper };
}

afterEach(() => {
  for (const wrapper of built.splice(0)) destroyVideoPlayer(wrapper);
  document.body.innerHTML = '';
});

describe('the video player pool', () => {
  it('keeps three players, and a fourth evicts the farthest from its scene', () => {
    const scenes = [0, 1, 2, 3].map(drivePlate);
    const [farthest, ...kept] = scenes;

    expect(farthest.wrapper._destroyed).toBe(true);
    expect(farthest.plate.querySelector('.video-iframe')).toBeNull();
    expect(hasVideoPlayer(farthest.plate)).toBe(false);

    for (const { plate, wrapper } of kept) {
      expect(wrapper._destroyed).toBe(false);
      expect(plate.querySelectorAll('.video-iframe')).toHaveLength(1);
    }
  });

  it('measures distance from the scene being built, not from the first', () => {
    const scenes = [5, 6, 0].map(drivePlate);
    const last = drivePlate(1);
    // Built for scene 1: scene 6 is farthest (5 away), not scene 0 (1 away).
    expect(scenes[1].wrapper._destroyed).toBe(true);
    expect(scenes[0].wrapper._destroyed).toBe(false);
    expect(scenes[2].wrapper._destroyed).toBe(false);
    expect(last.wrapper._destroyed).toBe(false);
  });
});
