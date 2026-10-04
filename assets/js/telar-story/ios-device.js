/**
 * Telar Story – iOS Device Detection
 *
 * Stories on an iPhone or iPad use button navigation, because Lenis momentum
 * scrolling is unreliable on iOS. The user agent alone cannot say which
 * devices those are: Safari on iPadOS requests desktop sites by default and
 * then sends a Macintosh user agent that does not mention the iPad. An iPad
 * reports several touch points and a desktop Mac reports none, so a Macintosh
 * user agent with more than one touch point is taken to be an iPad.
 *
 * @version v1.8.0
 */

/**
 * Whether the page is running on an iPhone, iPad or iPod.
 *
 * @param {string} [userAgent] - Defaults to navigator.userAgent.
 * @param {number} [maxTouchPoints] - Defaults to navigator.maxTouchPoints.
 * @returns {boolean}
 */
export function isIOSDevice(userAgent = navigator.userAgent, maxTouchPoints = navigator.maxTouchPoints) {
  if (/iPad|iPhone|iPod/.test(userAgent)) return true;
  return /Macintosh/.test(userAgent) && maxTouchPoints > 1;
}
