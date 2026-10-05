/**
 * Telar Story — Video Plate
 *
 * A scene whose object is a YouTube, Vimeo or Google Drive video.
 *
 * One player per scene: the steps of a scene share it, and a later step in the
 * scene re-clips the running player rather than rebuilding it.
 *
 * @version v1.8.0
 */

import { MediaPlate, isTruthy, stepClip } from './media-plate.js';
import { state } from '../state.js';
import { extractVideoId } from '../card-type.js';
import {
  createVideoPlayer,
  activateVideoCard,
  deactivateVideoCard,
  updateVideoClip,
  hasVideoPlayer,
  applyClipEndDim,
  showVideoPlayOverlay,
  layoutVideoPlate,
} from '../video-card.js';

export class VideoPlate extends MediaPlate {

  static containerClass = 'video-plate';
  static ariaFallback = 'Video player';

  /** Bring the plate to the front and start its player, building it if needed. */
  center() {
    this.load();
    // Always activate: _build creates .video-iframe synchronously — the
    // provider's API loads inside it — so the layout can be applied at once.
    activateVideoCard(this.container, this.sceneIndex);
  }

  /** Re-clip the running player to this step's window. */
  goToStep(step) {
    const clip = stepClip(step);
    updateVideoClip(this.container, clip.start, clip.end || undefined, clip.loop);
  }

  /** Re-place the player for the scene's arrangement after a geometry pass. */
  resize() { layoutVideoPlate(this.container); }

  _hasPlayer() { return hasVideoPlayer(this.container); }

  _deactivatePlayer() { deactivateVideoCard(this.container); }

  _build() {
    const el = this.container;
    const objectData = state.objectsIndex[this.objectId] || {};
    const sourceUrl = objectData.source_url || objectData.iiif_manifest || '';
    const cardType = el.dataset.cardType;
    const videoId = extractVideoId(cardType, sourceUrl);

    if (!videoId) {
      console.error('VideoPlate: no video ID for', this.objectId, sourceUrl);
      return;
    }

    const clipStart = parseFloat(el.dataset.clipStart) || 0;
    const clipEnd = parseFloat(el.dataset.clipEnd) || 0;
    const loop = isTruthy(el.dataset.loop);

    el.style.zIndex = this.zIndex;

    createVideoPlayer(el, cardType, videoId, {
      clipStart,
      clipEnd: clipEnd || undefined,
      loop,
      sceneIndex: this.sceneIndex,
      sourceUrl,
      onEnded: () => {
        applyClipEndDim(el);
      },
      onAutoplayBlocked: () => {
        showVideoPlayOverlay(el);
      },
    });
  }
}
