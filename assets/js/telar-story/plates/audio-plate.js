/**
 * Telar Story — Audio Plate
 *
 * A scene whose object is a self-hosted audio file.
 *
 * The extension comes from `window.audioObjects`, which `story.html` injects
 * from `_data/audio_objects.json`: the build knows what it wrote to disk, so
 * nothing here has to ask the server which file exists.
 *
 * @version v1.8.0
 */

import { MediaPlate, isTruthy, stepClip } from './media-plate.js';
import { getBasePath } from '../utils.js';
import {
  createAudioPlayer,
  activateAudioCard,
  deactivateAudioCard,
  updateAudioClip,
  hasAudioPlayer,
  applyAudioClipEndDim,
  layoutAudioPlate,
} from '../audio-card.js';

export class AudioPlate extends MediaPlate {

  static containerClass = 'audio-plate';
  static ariaFallback = 'Audio player';

  /** Bring the plate to the front and start its player, building it if needed. */
  center() {
    this.load();
    activateAudioCard(this.container, this.sceneIndex);
  }

  /** Re-clip the running player to this step's window. */
  goToStep(step) {
    const clip = stepClip(step);
    updateAudioClip(this.container, clip.start, clip.end || undefined, clip.loop);
  }

  /** Re-place the player for the scene's arrangement after a geometry pass. */
  resize() { layoutAudioPlate(this.container); }

  _hasPlayer() { return hasAudioPlayer(this.container); }

  _deactivatePlayer() { deactivateAudioCard(this.container); }

  _build() {
    const el = this.container;
    const audioObjects = window.audioObjects || {};
    const ext = audioObjects[this.objectId];
    if (!ext) {
      console.error('AudioPlate: no audio extension for', this.objectId);
      return;
    }

    const basePath = getBasePath();
    const audioUrl = `${basePath}/telar-content/objects/${this.objectId}.${ext}`;
    // Named only where the build has a peaks file; createAudioPlayer decodes
    // the audio itself without one.
    const peaksUrl = (window.audioPeaks || []).includes(this.objectId)
      ? `${basePath}/assets/audio/peaks/${this.objectId}.json`
      : null;

    const clipStart = parseFloat(el.dataset.clipStart) || 0;
    const clipEnd = parseFloat(el.dataset.clipEnd) || 0;
    const loop = isTruthy(el.dataset.loop);
    const isEmbed = document.body.classList.contains('embed-mode');

    el.style.zIndex = this.zIndex;

    createAudioPlayer(el, audioUrl, peaksUrl, {
      clipStart,
      clipEnd: clipEnd || undefined,
      loop,
      sceneIndex: this.sceneIndex,
      isEmbed,
      onEnded: () => {
        applyAudioClipEndDim(el);
      },
    });
  }
}
