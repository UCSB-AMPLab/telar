"""
Unit Tests for Post-Build Story Encryption

This module tests scripts/encrypt_protected_stories.py — envelope round-trip,
sentinel derivation, stub injection, the shape and content gates — and the
pipeline-side prerequisite check in telar/core.py that refuses to run when
the build workflow predates the post-build encryption step.

Version: v1.6.0
"""

import base64
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from encrypt_protected_stories import (
    FRAGMENT_END,
    FRAGMENT_START,
    FRAGMENT_URL_PREFIX,
    STUB_TOKEN,
    GateFailure,
    content_sentinel_sweep,
    derive_sentinels,
    extract_fragment_html,
    inject_envelope,
    process_site,
    shape_sweep,
)
from telar.encryption import derive_key, encrypt_story
from telar.core import _check_protected_prerequisites

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag


STORY_KEY = "unit-test-key"

STEPS = [
    {"_metadata": True, "has_latex": True},
    {
        "step": "1",
        "question": "What does the unit fixture ask about exactly",
        "answer": "A **marked** answer with a plain protected passage inside it.",
        "layer1_content": "<p>Layer prose that is definitely long enough.</p>",
    },
]


def decrypt_envelope(envelope, key=STORY_KEY, aad=None):
    salt = base64.b64decode(envelope["salt"])
    iv = base64.b64decode(envelope["iv"])
    ciphertext = base64.b64decode(envelope["ciphertext"])
    aesgcm = AESGCM(derive_key(key, salt))
    plaintext = aesgcm.decrypt(iv, ciphertext, aad.encode() if aad else None)
    return json.loads(plaintext)


class TestEnvelopeRoundTrip:
    def test_envelope_decrypts_to_payload(self):
        payload = {"steps": STEPS, "html": "<div>steps</div>"}
        envelope = encrypt_story(payload, STORY_KEY, aad="my-story")
        assert envelope["encrypted"] is True
        assert decrypt_envelope(envelope, aad="my-story") == payload

    def test_wrong_aad_fails_authentication(self):
        envelope = encrypt_story({"steps": []}, STORY_KEY, aad="story-a")
        with pytest.raises(InvalidTag):
            decrypt_envelope(envelope, aad="story-b")

    def test_no_aad_stays_backwards_compatible(self):
        envelope = encrypt_story(STEPS, STORY_KEY)
        assert decrypt_envelope(envelope) == STEPS

    def test_fresh_salt_and_iv_per_call(self):
        one = encrypt_story(STEPS, STORY_KEY)
        two = encrypt_story(STEPS, STORY_KEY)
        assert one["salt"] != two["salt"]
        assert one["iv"] != two["iv"]


class TestDeriveSentinels:
    def test_extracts_plain_segments(self):
        sentinels = derive_sentinels(STEPS)
        assert "What does the unit fixture ask about exactly" in sentinels
        # Markup-adjacent prose survives as separate plain segments.
        assert any("plain protected passage" in s for s in sentinels)

    def test_skips_metadata_and_short_segments(self):
        sentinels = derive_sentinels(
            [{"_metadata": True, "has_latex": True},
             {"question": "short", "answer": "tiny **x** bits"}]
        )
        assert sentinels == []

    def test_non_latin_scripts_yield_sentinels(self):
        # The gate must protect stories in any script, not just Latin —
        # a story whose prose derives zero sentinels is invisible to the
        # content sweep.
        cases = {
            "cyrillic": "Это защищённая история о старинных картах города",
            "greek": "Αυτή είναι μια προστατευμένη ιστορία για παλιούς χάρτες",
            "cjk": "这是一个关于古代地图和殖民地景观的受保护故事内容",
            "arabic": "هذه قصة محمية عن الخرائط القديمة والمناظر الطبيعية",
        }
        for name, prose in cases.items():
            sentinels = derive_sentinels([{"question": prose, "answer": ""}])
            assert sentinels, f"{name} prose produced no sentinels"
            assert any(s in prose for s in sentinels), name

    def test_dense_scripts_clear_a_lower_bar(self):
        # Ten Han characters are a distinctive phrase; ten Latin characters
        # are not. The dense-script minimum applies only when the segment is
        # mostly dense-script characters.
        short_cjk = "古代地图殖民地景观故事"          # 11 chars, all Han
        short_latin = "a tiny bit"                    # 10 chars, Latin
        assert derive_sentinels([{"question": short_cjk, "answer": ""}])
        assert derive_sentinels([{"question": short_latin, "answer": ""}]) == []

    def test_mostly_latin_keeps_the_full_bar(self):
        # A sprinkle of dense-script characters must not lower the bar for a
        # basically-Latin segment.
        mixed = "see 地图 maps"                        # 2 of 10 compact chars dense
        assert derive_sentinels([{"question": mixed, "answer": ""}]) == []

    def test_underscores_split_segments(self):
        # Markdown transforms underscores (emphasis), so they cannot sit
        # inside a sentinel even though regex \w matches them.
        sentinels = derive_sentinels(
            [{"question": "an _emphasised protected passage_ inside the "
                          "question text of this fixture", "answer": ""}]
        )
        assert all("_" not in s for s in sentinels)
        assert any("emphasised protected passage" in s for s in sentinels)


class TestFragmentExtraction:
    def test_extracts_between_markers(self, tmp_path):
        page = tmp_path / "index.html"
        page.write_text(
            f"<html><body>{FRAGMENT_START}<div class='step-data'>steps"
            f"</div>{FRAGMENT_END}</body></html>"
        )
        assert extract_fragment_html(page) == "<div class='step-data'>steps</div>"

    def test_missing_markers_fails(self, tmp_path):
        page = tmp_path / "index.html"
        page.write_text("<html><body>no markers</body></html>")
        with pytest.raises(GateFailure):
            extract_fragment_html(page)


class TestInjection:
    STUB_PAGE = (
        "<script>\nwindow.storyData = {\"encrypted\": true, \"salt\": \"\", "
        "\"iv\": \"\", \"ciphertext\": \"" + STUB_TOKEN + "\"};\n"
        "window.objectsData = {};\n</script>"
    )

    def test_replaces_stub_with_envelope(self, tmp_path):
        page = tmp_path / "index.html"
        page.write_text(self.STUB_PAGE)
        envelope = encrypt_story({"steps": []}, STORY_KEY, aad="s")
        inject_envelope(page, envelope)
        html = page.read_text()
        assert STUB_TOKEN not in html
        assert envelope["ciphertext"] in html
        # The following inline assignments survive the swap.
        assert "window.objectsData = {};" in html

    def test_page_without_stub_fails(self, tmp_path):
        page = tmp_path / "index.html"
        page.write_text("<script>window.storyData = {steps: []};</script>")
        with pytest.raises(GateFailure):
            inject_envelope(page, encrypt_story([], STORY_KEY))


class TestSweeps:
    def test_sentinel_hit_is_reported(self, tmp_path):
        (tmp_path / "page.html").write_text("...a plain protected passage leaked...")
        hits = content_sentinel_sweep(tmp_path, {"s": ["plain protected passage"]})
        assert len(hits) == 1

    def test_telar_content_passthrough_is_skipped(self, tmp_path):
        served = tmp_path / "telar-content" / "spreadsheets"
        served.mkdir(parents=True)
        (served / "s.csv").write_text("plain protected passage")
        assert content_sentinel_sweep(tmp_path, {"s": ["plain protected passage"]}) == []

    def test_shape_sweep_finds_leftovers(self, tmp_path):
        (tmp_path / "page.html").write_text(f"stub {STUB_TOKEN} left behind")
        fragment_dir = tmp_path / FRAGMENT_URL_PREFIX
        fragment_dir.mkdir()
        problems = shape_sweep(tmp_path)
        assert len(problems) == 2


def build_site_fixture(tmp_path, story_id="prot-story"):
    """A minimal built site + data dir with one protected story."""
    data_dir = tmp_path / "_data"
    data_dir.mkdir()
    (data_dir / "project.json").write_text(json.dumps(
        [{"stories": [{"number": "1", "title": "P", "story_id": story_id,
                       "protected": True}]}]
    ))
    (data_dir / f"{story_id}.json").write_text(json.dumps(STEPS))

    config = tmp_path / "_config.yml"
    config.write_text(f'story_key: "{STORY_KEY}"\n')

    site = tmp_path / "_site"
    story_dir = site / "stories" / story_id
    story_dir.mkdir(parents=True)
    (story_dir / "index.html").write_text(TestInjection.STUB_PAGE)

    fragment_dir = site / FRAGMENT_URL_PREFIX / story_id
    fragment_dir.mkdir(parents=True)
    (fragment_dir / "index.html").write_text(
        f"<html><body>{FRAGMENT_START}<div class='step-data'>rendered steps"
        f"</div>{FRAGMENT_END}</body></html>"
    )
    (site / "index.html").write_text("<html>homepage, no story content</html>")
    return site, data_dir, config


class TestProcessSite:
    def test_happy_path(self, tmp_path):
        site, data_dir, config = build_site_fixture(tmp_path)
        assert process_site(site, data_dir, config) == 1
        html = (site / "stories" / "prot-story" / "index.html").read_text()
        assert STUB_TOKEN not in html
        assert not (site / FRAGMENT_URL_PREFIX).exists()
        # Envelope on the page decrypts back to {steps, html} with the AAD.
        match = json.loads(
            html.split("window.storyData = ", 1)[1].split(";", 1)[0]
        )
        payload = decrypt_envelope(match, aad="prot-story")
        assert payload["steps"] == STEPS
        assert payload["html"] == "<div class='step-data'>rendered steps</div>"

    def test_no_protected_stories_is_a_noop(self, tmp_path):
        data_dir = tmp_path / "_data"
        data_dir.mkdir()
        (data_dir / "project.json").write_text(json.dumps([{"stories": []}]))
        config = tmp_path / "_config.yml"
        config.write_text("story_key: ''\n")
        assert process_site(tmp_path, data_dir, config) == 0

    def test_missing_key_fails(self, tmp_path):
        site, data_dir, config = build_site_fixture(tmp_path)
        config.write_text("story_key: ''\n")
        with pytest.raises(GateFailure, match="story_key"):
            process_site(site, data_dir, config)

    def test_missing_fragment_fails(self, tmp_path):
        site, data_dir, config = build_site_fixture(tmp_path)
        import shutil
        shutil.rmtree(site / FRAGMENT_URL_PREFIX)
        with pytest.raises(GateFailure, match="fragment"):
            process_site(site, data_dir, config)

    def test_encrypted_format_data_file_fails(self, tmp_path):
        # A dict-shaped data file means _data was produced by a pipeline
        # that still encrypts at generation — the migration-skew state the
        # gate must refuse.
        site, data_dir, config = build_site_fixture(tmp_path)
        (data_dir / "prot-story.json").write_text(
            json.dumps({"encrypted": True, "ciphertext": "..."})
        )
        with pytest.raises(GateFailure, match="plaintext steps list"):
            process_site(site, data_dir, config)

    def test_sentinel_leak_elsewhere_fails(self, tmp_path):
        site, data_dir, config = build_site_fixture(tmp_path)
        (site / "index.html").write_text(
            "<html>What does the unit fixture ask about exactly</html>"
        )
        with pytest.raises(GateFailure, match="plaintext"):
            process_site(site, data_dir, config)


WORKFLOW_WITH_STEP = "steps:\n  - run: python scripts/encrypt_protected_stories.py\n"
WORKFLOW_OLD = "steps:\n  - run: bundle exec jekyll build\n"


class TestPipelinePrerequisites:
    """_check_protected_prerequisites reads _config.yml from the CWD."""

    def _setup(self, tmp_path, monkeypatch, protected=True, key=STORY_KEY):
        monkeypatch.chdir(tmp_path)
        data_dir = tmp_path / "_data"
        data_dir.mkdir()
        stories = [{"number": "1", "title": "P", "story_id": "s",
                    "protected": protected}]
        (data_dir / "project.json").write_text(json.dumps([{"stories": stories}]))
        (tmp_path / "_config.yml").write_text(f'story_key: "{key}"\n')
        return data_dir

    def test_old_workflow_trips_interlock(self, tmp_path, monkeypatch):
        data_dir = self._setup(tmp_path, monkeypatch)
        workflow = tmp_path / "build.yml"
        workflow.write_text(WORKFLOW_OLD)
        with pytest.raises(SystemExit):
            _check_protected_prerequisites(data_dir, workflow_path=workflow)

    def test_missing_workflow_trips_interlock(self, tmp_path, monkeypatch):
        data_dir = self._setup(tmp_path, monkeypatch)
        with pytest.raises(SystemExit):
            _check_protected_prerequisites(
                data_dir, workflow_path=tmp_path / "absent.yml"
            )

    def test_upgraded_workflow_passes(self, tmp_path, monkeypatch):
        data_dir = self._setup(tmp_path, monkeypatch)
        workflow = tmp_path / "build.yml"
        workflow.write_text(WORKFLOW_WITH_STEP)
        _check_protected_prerequisites(data_dir, workflow_path=workflow)

    def test_no_protected_stories_passes_without_workflow(self, tmp_path, monkeypatch):
        data_dir = self._setup(tmp_path, monkeypatch, protected=False)
        _check_protected_prerequisites(
            data_dir, workflow_path=tmp_path / "absent.yml"
        )

    def test_missing_key_fails_before_workflow_check(self, tmp_path, monkeypatch):
        data_dir = self._setup(tmp_path, monkeypatch, key="")
        workflow = tmp_path / "build.yml"
        workflow.write_text(WORKFLOW_WITH_STEP)
        with pytest.raises(SystemExit):
            _check_protected_prerequisites(data_dir, workflow_path=workflow)
