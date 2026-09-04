/**
 * Telar — which of the share panel's warnings stand, and how one is shown.
 *
 * `_includes/share-panel.html` renders two warnings per branch and the panel
 * reads all four ids, but only two are ever in the document at once: the story
 * branch's key warnings or the other branch's protected-story warnings. The
 * two pairs answer different questions, which is why there are two flags
 * rather than one — a story page can append the live decryption key, so its
 * pair speaks to exposing the key; no other page ever holds the key, so its
 * pair only flags that the chosen story is protected.
 *
 * The decision is plain values, so what raises a warning can be read and
 * checked without a page; the showing takes the element it is given.
 *
 * Version: v1.7.0
 */

/** Which of the two warning pairs the current state calls for. */
export function warningState(currentStoryProtected, storyKey, includeKey, currentStoryUrl) {
  return {
    key: Boolean(currentStoryProtected && includeKey && storyKey),
    protectedStory: Boolean(currentStoryProtected && currentStoryUrl),
  };
}

/** Show or hide one warning, if the branch on the page has it. */
export function setWarning(element, shown) {
  if (!element) return;
  if (shown) {
    element.classList.remove('d-none');
  } else {
    element.classList.add('d-none');
  }
}
