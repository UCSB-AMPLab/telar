/**
 * The clip panel shared by video and audio object pages: the collapse
 * toggle that hides its button while the panel is open, the theme class on
 * the panel, and the two copy buttons that write the clip's start and end
 * as CSV or tab-separated text.
 *
 * Version: v1.7.0
 */

import { copyWithFeedback, CHECK_ICON } from './copy-feedback.js';

export function initClipPanelToggle(doc = document) {
  var clipPanel = doc.getElementById('clipPanel');
  var clipButton = doc.getElementById('clipPickerButton');
  if (clipPanel && clipButton) {
    clipPanel.addEventListener('show.bs.collapse', function() { clipButton.style.display = 'none'; });
    clipPanel.addEventListener('hide.bs.collapse', function() { clipButton.style.display = 'block'; });
  }

  // Theme colouring for clip panel (same as coordinate panel)
  window.telarObjectTheme.applyPanelContrastClass(doc.querySelector('.clip-panel'));
}

export function initClipCopyButtons(copiedLang, doc = document) {
  function copyClipText(text, btnId) {
    copyWithFeedback(text, btnId, CHECK_ICON + ' ' + copiedLang, doc);
  }

  var copyClipCsv = doc.getElementById('copy-clip-csv');
  if (copyClipCsv) {
    copyClipCsv.addEventListener('click', function() {
      var start = doc.getElementById('clip-start-display').textContent;
      var end = doc.getElementById('clip-end-display').textContent;
      copyClipText(start + ',' + end, 'copy-clip-csv');
    });
  }

  var copyClipSheets = doc.getElementById('copy-clip-sheets');
  if (copyClipSheets) {
    copyClipSheets.addEventListener('click', function() {
      var start = doc.getElementById('clip-start-display').textContent;
      var end = doc.getElementById('clip-end-display').textContent;
      copyClipText(start + '\t' + end, 'copy-clip-sheets');
    });
  }
}
