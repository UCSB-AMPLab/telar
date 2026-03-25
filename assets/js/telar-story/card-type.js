/**
 * Telar Story – Card Type Detection
 *
 * Determines the card type for a given story step. Supported types:
 * 'iiif' (default when an objectId is present), 'text-only' (when no
 * objectId is present), 'youtube', 'vimeo', 'google-drive' (detected
 * from the object's source_url field), and 'audio' (detected from the
 * object's file_path field for self-hosted MP3/OGG/M4A files). An
 * explicit cardType field on the step data always wins over auto-detection.
 *
 * This module exists to isolate the type-detection logic so future card
 * types (widgets, etc.) can be added here without touching the
 * card-pool or navigation modules.
 *
 * @version v1.0.0-beta
 */

// ── Video URL patterns ────────────────────────────────────────────────────────

const YOUTUBE_RE = /(?:youtube\.com\/(?:watch\?.*v=|embed\/|shorts\/)|youtu\.be\/)([A-Za-z0-9_-]{11})/;
const VIMEO_RE   = /vimeo\.com\/(?:video\/)?(\d+)/;
const GDRIVE_RE  = /drive\.google\.com\/(?:file\/d\/|open\?id=)([A-Za-z0-9_-]+)/;

// ── Audio file extension pattern ─────────────────────────────────────────────

const AUDIO_FILE_RE = /\.(mp3|ogg|m4a)$/i;

// ── Card type detection ───────────────────────────────────────────────────────

/**
 * Detect the card type for a step.
 *
 * Detection order:
 *   1. Explicit `cardType` field — always wins if non-empty
 *   2. No `objectId` (absent or empty) → 'text-only'
 *   3. Check source_url against YouTube URL pattern → 'youtube'
 *   4. Check source_url against Vimeo URL pattern → 'vimeo'
 *   5. Check source_url against Google Drive URL pattern → 'google-drive'
 *   5.5. Check file_path against audio file extensions → 'audio'
 *   6. Default → 'iiif'
 *
 * @param {Object} stepData - Step data object from window.storyData.steps
 * @param {string} [stepData.cardType] - Optional explicit type override
 * @param {string} [stepData.objectId] - Object ID driving the viewer
 * @param {string} [stepData.source_url] - Source URL from the object data
 * @param {string} [stepData.file_path] - Resolved file path from the object data (audio detection)
 * @returns {'iiif'|'text-only'|'youtube'|'vimeo'|'google-drive'|'audio'|string} Detected card type
 */
export function detectCardType(stepData) {
  if (stepData.cardType && stepData.cardType !== '') return stepData.cardType;
  if (!stepData.objectId || stepData.objectId === '') return 'text-only';

  const sourceUrl = stepData.source_url || '';
  if (YOUTUBE_RE.test(sourceUrl)) return 'youtube';
  if (VIMEO_RE.test(sourceUrl)) return 'vimeo';
  if (GDRIVE_RE.test(sourceUrl)) return 'google-drive';

  if (AUDIO_FILE_RE.test(stepData.file_path || '')) return 'audio';

  return 'iiif';
}

/**
 * Extract the provider-specific video ID from a source URL.
 *
 * @param {'youtube'|'vimeo'|'google-drive'} cardType - The video card type
 * @param {string} sourceUrl - The source URL to extract the ID from
 * @returns {string|null} The provider-specific ID, or null if not found
 */
export function extractVideoId(cardType, sourceUrl) {
  const regexMap = { youtube: YOUTUBE_RE, vimeo: VIMEO_RE, 'google-drive': GDRIVE_RE };
  const match = (sourceUrl || '').match(regexMap[cardType]);
  return match ? match[1] : null;
}
