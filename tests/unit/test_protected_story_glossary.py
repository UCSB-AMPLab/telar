"""
Integration Test: Glossary Markup Stripping for Protected Stories

Protected (password-encrypted) stories are rendered at runtime by a path that
HTML-escapes the step answer and offers no glossary panel, so the inline
`<a class="glossary-inline-link">` that `process_story` injects into the answer
would surface as escaped tag-text. Before encryption, `_encrypt_protected_stories`
reduces that markup back to plain text (see `strip_glossary_links`).

This test drives the real `_encrypt_protected_stories` against a temporary
`_data` directory, then decrypts the result to prove that:
  - the step `answer` has its glossary link reduced to the plain term title, and
  - layer panel content (`layer1_text`) is left untouched, because it IS rendered
    as trusted HTML at panel-open time and the glossary panel works there.

Version: v1.5.1
"""

import sys
import os
import json
import base64

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.core import _encrypt_protected_stories
from telar.encryption import derive_key
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _decrypt(blob, key):
    """Reverse encrypt_story: derive key from salt, AES-GCM decrypt, parse JSON."""
    salt = base64.b64decode(blob['salt'])
    iv = base64.b64decode(blob['iv'])
    ciphertext = base64.b64decode(blob['ciphertext'])
    plaintext = AESGCM(derive_key(key, salt)).decrypt(iv, ciphertext, None)
    return json.loads(plaintext.decode('utf-8'))


def test_protected_story_answer_glossary_is_stripped_layers_kept(tmp_path, monkeypatch):
    data_dir = tmp_path / '_data'
    data_dir.mkdir()

    # _config.yml is read from the current working directory
    (tmp_path / '_config.yml').write_text('story_key: "secret-key"\n', encoding='utf-8')

    # project.json marks our story protected
    (data_dir / 'project.json').write_text(json.dumps([
        {'stories': [{'story_id': 'locked', 'number': 1, 'protected': True}]}
    ]), encoding='utf-8')

    # The story JSON as process_story would have produced it: the answer carries a
    # resolved glossary link; a layer carries one too (must be preserved).
    answer_html = 'Made with <a href="#" class="glossary-inline-link" data-term-id="telar">Telar</a>.'
    layer_html = 'See <a href="#" class="glossary-inline-link" data-term-id="iiif">IIIF</a> details.'
    (data_dir / 'locked.json').write_text(json.dumps([
        {'step': '1', 'question': 'A plain question', 'answer': answer_html,
         'layer1_text': layer_html},
    ]), encoding='utf-8')

    monkeypatch.chdir(tmp_path)
    _encrypt_protected_stories(data_dir)

    # File on disk must now be encrypted (not plaintext)
    blob = json.loads((data_dir / 'locked.json').read_text(encoding='utf-8'))
    assert blob.get('encrypted') is True
    assert 'glossary-inline-link' not in json.dumps(blob)  # nothing leaks in plaintext

    steps = _decrypt(blob, 'secret-key')
    answer = steps[0]['answer']
    # Answer glossary link reduced to plain title — no tag-soup at runtime
    assert answer == 'Made with Telar.'
    assert 'glossary-inline-link' not in answer
    # Layer content untouched (it renders as trusted HTML; the panel works there)
    assert 'glossary-inline-link' in steps[0]['layer1_text']
    assert steps[0]['question'] == 'A plain question'
