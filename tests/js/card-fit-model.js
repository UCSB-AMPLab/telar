/**
 * A side card whose geometry follows its answer size, for the fit suites.
 *
 * jsdom lays nothing out, so the card's heights are modelled: the content is
 * a fixed part (question, padding, panel button) plus `perPx` px of answer for
 * each px of answer font size. The size is the fitted one where the card
 * carries `data-card-fit` and a fitted size, and the answer's
 * `--telar-answer-base-size` otherwise, in rem of the root font size.
 *
 * @version v1.8.0
 */

/** The root font size in px, as the page states it. */
export function rootPx() {
  return parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
}

/**
 * @param {Object} [opts]
 * @param {string} [opts.base] - The answer's tier size, e.g. '1rem'
 * @param {number} [opts.fixed] - Content height that does not scale, px
 * @param {number} [opts.perPx] - Answer height per px of font size
 * @param {number} [opts.width] - The card's offsetWidth
 */
export function modelCard({ base = '1rem', fixed = 100, perPx = 20, width = 400 } = {}) {
  const card = document.createElement('div');
  card.className = 'text-card';
  card.dataset.stepIndex = '0';
  card.dataset.runPosition = '0';
  const content = document.createElement('div');
  content.className = 'step-content';
  const question = document.createElement('h2');
  question.className = 'step-question';
  question.textContent = 'Question';
  const answer = document.createElement('div');
  answer.className = 'step-answer';
  answer.style.setProperty('--telar-answer-base-size', base);
  content.append(question, answer);
  card.append(content);
  document.body.append(card);

  const baseSize = () => {
    const raw = answer.style.getPropertyValue('--telar-answer-base-size');
    return raw.endsWith('rem') ? parseFloat(raw) * rootPx() : parseFloat(raw);
  };
  const size = () => {
    const fitted = card.style.getPropertyValue('--telar-answer-fit-size');
    return card.dataset.cardFit !== undefined && fitted ? parseFloat(fitted) : baseSize();
  };
  const contentH = () => fixed + perPx * size();
  const ceiling = () => parseFloat(card.style.maxHeight) || Infinity;

  Object.defineProperty(card, 'offsetWidth', { configurable: true, get: () => width });
  Object.defineProperty(card, 'scrollHeight', { configurable: true, get: () => Math.round(contentH()) });
  Object.defineProperty(card, 'clientHeight', {
    configurable: true, get: () => Math.round(Math.min(contentH(), ceiling())),
  });
  Object.defineProperty(card, 'offsetHeight', { configurable: true, get: () => card.clientHeight });
  Object.defineProperty(answer, 'offsetHeight', { configurable: true, get: () => perPx * size() });

  return { card, content, question, answer, size };
}
