/**
 * Copy text to the clipboard and show a checkmark on the button for two
 * seconds. The checkmark is decorative: the button's text or label says
 * what happened, so the SVG is hidden from assistive technology.
 *
 * Version: v1.7.0
 */

export const CHECK_ICON =
  '<svg class="icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg>';

/**
 * Write `text` to the clipboard, then replace the button's content with
 * `feedbackHtml` for two seconds. Returns the clipboard promise so a caller
 * can chain a catch.
 */
export function copyWithFeedback(text, buttonId, feedbackHtml, doc = document) {
  return navigator.clipboard.writeText(text).then(function() {
    const btn = doc.getElementById(buttonId);
    const originalHTML = btn.innerHTML;
    btn.innerHTML = feedbackHtml;
    setTimeout(function() {
      btn.innerHTML = originalHTML;
    }, 2000);
  });
}
