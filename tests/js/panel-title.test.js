/**
 * Tests for a layer panel's title.
 *
 * A panel with a title of its own shows it; one without shows the label of
 * the button that opened it. When that button was left blank, the story card
 * labels it with the site language's default (lang.buttons.learn_more for
 * layer 1, lang.buttons.go_deeper for layer 2), and the panel's heading takes
 * the same words rather than an English placeholder.
 *
 * @version v1.8.0
 */

import { describe, it, expect, beforeAll } from 'vitest';
import { openPanel } from '../../assets/js/telar-story/panels.js';

class FakeOffcanvas {
  static getInstance() { return null; }
  show() {}
}

const title = (t) => document.getElementById(`panel-${t}-title`).textContent;

beforeAll(() => {
  window.bootstrap = { Offcanvas: FakeOffcanvas };
  document.body.innerHTML = ['layer1', 'layer2'].map((t) => `
    <div class="offcanvas" id="panel-${t}">
      <h1 id="panel-${t}-title"></h1><div id="panel-${t}-content"></div>
    </div>`).join('');
  window.telarLang = { learnMore: 'Saber más', goDeeper: 'Profundizar' };
  window.storyData = {
    steps: [
      { step: '1', layer1_title: 'Técnicas de tejido', layer1_button: 'Ver más',
        layer1_text: '<p>uno</p>', layer2_title: 'Hilos', layer2_button: 'Otra capa',
        layer2_text: '<p>dos</p>' },
      { step: '2', layer1_title: '', layer1_button: 'Ver más', layer1_text: '<p>uno</p>',
        layer2_title: '', layer2_button: 'Otra capa', layer2_text: '<p>dos</p>' },
      { step: '3', layer1_title: '', layer1_button: '', layer1_text: '<p>uno</p>',
        layer2_title: '', layer2_button: '', layer2_text: '<p>dos</p>' },
    ],
  };
});

describe('a layer panel title', () => {
  it('is the panel\'s own title when it has one', () => {
    openPanel('layer1', '1');
    openPanel('layer2', '1');
    expect(title('layer1')).toBe('Técnicas de tejido');
    expect(title('layer2')).toBe('Hilos');
  });

  it('is the button label when the panel has no title', () => {
    openPanel('layer1', '2');
    openPanel('layer2', '2');
    expect(title('layer1')).toBe('Ver más');
    expect(title('layer2')).toBe('Otra capa');
  });

  it('is the site language\'s default button label when the button is blank too', () => {
    openPanel('layer1', '3');
    openPanel('layer2', '3');
    expect(title('layer1')).toBe('Saber más');
    expect(title('layer2')).toBe('Profundizar');
  });
});
