"""
Unit Tests for Post-Build Story Encryption

This module tests scripts/encrypt_protected_stories.py — envelope round-trip,
sentinel derivation, stub injection, the shape and content gates — and the
pipeline-side prerequisite check in telar/core.py that refuses to run when
the build workflow predates the post-build encryption step.

Version: v1.7.0
"""

import base64
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from encrypt_protected_stories import (
    _emit_actions_error,
    check_no_orphan_fragments,
    load_page_manifest,
    resolve_story_page,
    FRAGMENT_END,
    FRAGMENT_START,
    FRAGMENT_URL_PREFIX,
    STUB_TOKEN,
    GateFailure,
    content_sentinel_sweep,
    derive_sentinels,
    extract_fragment_html,
    inject_envelope,
    main,
    process_site,
    shape_sweep,
)
from telar.encryption import derive_key, encrypt_story
from telar.core import _check_protected_prerequisites
from telar.story_pages import build_manifest, write_manifest

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


def build_site_fixture(tmp_path, story_id="prot-story", page_slug=None,
                       site_name="_site"):
    """A minimal built site + data dir with one protected story."""
    data_dir = tmp_path / "_data"
    data_dir.mkdir()
    (data_dir / "project.json").write_text(json.dumps(
        [{"stories": [{"number": "1", "title": "P", "story_id": story_id,
                       "protected": True}]}]
    ))
    (data_dir / f"{story_id}.json").write_text(json.dumps(STEPS))
    write_manifest(data_dir, build_manifest([(story_id, f"_stories/{story_id}.md")]))

    config = tmp_path / "_config.yml"
    config.write_text(f'story_key: "{STORY_KEY}"\n')

    site = tmp_path / site_name
    story_dir = site / "stories" / (page_slug or story_id)
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


class TestPageManifest:
    """Resolution reads the manifest and nothing else."""

    def _manifest(self, *identifiers):
        return build_manifest([(i, f"_stories/{i}.md") for i in identifiers])

    def test_resolves_the_generated_url(self, tmp_path):
        page = tmp_path / "stories" / "blank-template" / "index.html"
        page.parent.mkdir(parents=True)
        page.write_text("x")
        manifest = self._manifest("blank_template")
        assert resolve_story_page(tmp_path, "blank_template", manifest) == page

    def test_a_page_at_the_raw_identifier_is_not_accepted(self, tmp_path):
        # The generator declared /stories/blank-template/. A page sitting at
        # the un-slugified path is some other document, whatever it claims
        # about itself, so resolution must not fall back onto it.
        page = tmp_path / "stories" / "blank_template" / "index.html"
        page.parent.mkdir(parents=True)
        page.write_text("x")
        manifest = self._manifest("blank_template")
        with pytest.raises(GateFailure, match="story page not found"):
            resolve_story_page(tmp_path, "blank_template", manifest)

    def test_identifier_absent_from_the_manifest_fails(self, tmp_path):
        with pytest.raises(GateFailure, match="no story page was generated"):
            resolve_story_page(tmp_path, "ghost", self._manifest("real"))

    def test_custom_permalink_is_reported_as_the_reason(self, tmp_path):
        manifest = build_manifest(
            [("prot", "_stories/prot.md")], "/relatos/:name/"
        )
        with pytest.raises(GateFailure, match="stories collection permalink"):
            resolve_story_page(tmp_path, "prot", manifest)

    def test_missing_manifest_names_the_generator(self, tmp_path):
        with pytest.raises(GateFailure, match="generate_collections.py"):
            load_page_manifest(tmp_path)

    def test_manifest_from_another_schema_is_refused(self, tmp_path):
        # Reading it as "no stories generated" would blame the wrong thing.
        manifest = build_manifest([("a", "_stories/a.md")])
        manifest['schema'] = 99
        write_manifest(tmp_path, manifest)
        with pytest.raises(GateFailure, match="different\\n?\\s*releases|schema"):
            load_page_manifest(tmp_path)

    def test_manifest_without_a_stories_map_is_refused(self, tmp_path):
        write_manifest(tmp_path, {'schema': 1, 'stories': None})
        with pytest.raises(GateFailure, match="story page manifest"):
            load_page_manifest(tmp_path)

    def test_manifest_that_is_not_an_object_is_refused(self, tmp_path):
        # Read loosely this becomes "no stories generated"; read carelessly
        # it raises AttributeError instead of failing the gate.
        write_manifest(tmp_path, ["not", "a", "manifest"])
        with pytest.raises(GateFailure, match="story page manifest"):
            load_page_manifest(tmp_path)

    def test_manifest_with_a_non_object_entry_is_refused(self, tmp_path):
        write_manifest(tmp_path, {'schema': 1, 'stories': {'a': "/stories/a/"}})
        with pytest.raises(GateFailure, match="story page manifest"):
            load_page_manifest(tmp_path)

    def test_a_non_string_url_is_refused(self, tmp_path):
        manifest = self._manifest("prot")
        manifest['stories']['prot']['url'] = ["/stories/prot/"]
        with pytest.raises(GateFailure, match="non-text URL"):
            resolve_story_page(tmp_path, "prot", manifest)

    def test_a_case_variant_directory_is_refused(self, tmp_path):
        # On a case-insensitive filesystem exists() answers for a directory
        # whose real name differs in case, and Jekyll reports no conflict for
        # that pair. Compare against the name actually on disk.
        site = tmp_path / "_site"
        (site / "stories" / "PROT").mkdir(parents=True)
        (site / "stories" / "PROT" / "index.html").write_text("<html>other</html>")
        manifest = self._manifest("prot")
        page = site / "stories" / "prot" / "index.html"
        if not page.exists():
            pytest.skip("case-sensitive filesystem: this collision cannot occur")
        with pytest.raises(GateFailure, match="named differently"):
            resolve_story_page(site, "prot", manifest)

    def test_a_url_escaping_the_site_directory_is_refused(self, tmp_path):
        manifest = self._manifest("prot")
        manifest['stories']['prot']['url'] = '/../../elsewhere/'
        with pytest.raises(GateFailure, match="resolves outside"):
            resolve_story_page(tmp_path / "_site", "prot", manifest)


class TestActionsAnnotation:
    """Gate failures must reach CI as a structured annotation, not exit code 1."""

    def test_emits_error_annotation_under_actions(self, capsys, monkeypatch):
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        _emit_actions_error(GateFailure("line one\nline two"))
        out = capsys.readouterr().out
        assert out.startswith("::error title=Protected stories gate::")
        # A workflow command is one line; newlines travel escaped.
        assert "%0A" in out
        assert "\n" not in out.rstrip("\n")

    def test_silent_outside_actions(self, capsys, monkeypatch):
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        _emit_actions_error(GateFailure("boom"))
        assert capsys.readouterr().out == ""

    def test_custom_title_is_used(self, capsys, monkeypatch):
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        _emit_actions_error("ValueError: bad json", title="Script error")
        assert "::error title=Script error::" in capsys.readouterr().out

    def test_escapes_percent(self, capsys, monkeypatch):
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        _emit_actions_error(GateFailure("100% plaintext"))
        assert "100%25 plaintext" in capsys.readouterr().out


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

    def test_orphan_fragment_fails_even_with_no_protected_stories(self, tmp_path):
        # A fragment renders the steps as plaintext for this script to
        # consume. One surviving where nothing claims protection would
        # deploy that plaintext, so the check runs even on a site where no
        # story claims protection.
        data_dir = tmp_path / "_data"
        data_dir.mkdir()
        (data_dir / "project.json").write_text(json.dumps([{"stories": []}]))
        config = tmp_path / "_config.yml"
        config.write_text("story_key: ''\n")
        stale = tmp_path / FRAGMENT_URL_PREFIX / "was-protected"
        stale.mkdir(parents=True)
        (stale / "index.html").write_text("<html>confidential draft</html>")
        with pytest.raises(GateFailure, match="was-protected"):
            process_site(tmp_path, data_dir, config)

    def test_no_fragments_means_no_orphan_failure(self, tmp_path):
        check_no_orphan_fragments(tmp_path)

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

    def test_underscore_identifier_resolves_to_the_generated_page(self, tmp_path):
        # `_stories/blank_template.md` is generated with the permalink
        # /stories/blank-template/, so that is where the encryptor looks.
        site, data_dir, config = build_site_fixture(
            tmp_path, story_id="blank_template", page_slug="blank-template"
        )
        assert process_site(site, data_dir, config) == 1
        html = (site / "stories" / "blank-template" / "index.html").read_text()
        assert STUB_TOKEN not in html
        assert not (site / FRAGMENT_URL_PREFIX).exists()

    def test_missing_story_page_still_fails(self, tmp_path):
        # The slug fallback must not soften a genuinely absent page.
        import shutil
        site, data_dir, config = build_site_fixture(tmp_path)
        shutil.rmtree(site / "stories" / "prot-story")
        with pytest.raises(GateFailure, match="story page not found"):
            process_site(site, data_dir, config)

    def test_sentinel_leak_elsewhere_fails(self, tmp_path):
        site, data_dir, config = build_site_fixture(tmp_path)
        (site / "index.html").write_text(
            "<html>What does the unit fixture ask about exactly</html>"
        )
        with pytest.raises(GateFailure, match="Reword whichever copy"):
            process_site(site, data_dir, config)

    def test_a_foreign_page_at_the_url_fails_closed(self, tmp_path):
        # Jekyll lets a user page declare a story's permalink: it warns
        # about the conflict, then lets that page win the destination. The
        # manifest still names the right path, so what stops the build is
        # the absence of the protected layout's stub on the page found
        # there — the second half of what this script trusts.
        site, data_dir, config = build_site_fixture(tmp_path)
        (site / "stories" / "prot-story" / "index.html").write_text(
            "<html><body>a page that is not the story</body></html>"
        )
        with pytest.raises(GateFailure, match="no stub envelope found"):
            process_site(site, data_dir, config)

    def test_missing_manifest_fails(self, tmp_path):
        # A build that skipped generate_collections.py has no manifest, so
        # the encryptor has no authority for where pages went.
        site, data_dir, config = build_site_fixture(tmp_path)
        (data_dir / "telar-build" / "story-pages.json").unlink()
        with pytest.raises(GateFailure, match="manifest not found"):
            process_site(site, data_dir, config)

    def test_missing_page_message_names_the_real_site_dir(self, tmp_path):
        # Under a non-default --site-dir the message must name the path that
        # was actually opened, not a hard-coded _site/ prefix.
        import shutil
        site, data_dir, config = build_site_fixture(
            tmp_path, story_id="blank_template", page_slug="blank-template",
            site_name="build-output",
        )
        shutil.rmtree(site / "stories" / "blank-template")
        with pytest.raises(GateFailure) as excinfo:
            process_site(site, data_dir, config)
        message = str(excinfo.value)
        assert "_site/stories" not in message
        assert str(site / "stories" / "blank-template" / "index.html") in message

    def test_fragment_page_is_not_slugified(self, tmp_path):
        # Fragment pages carry an explicit permalink built from the raw
        # identifier, so slugification must not reach them: an underscore
        # story's fragment stays at /telar-protected-fragments/blank_template/.
        site, data_dir, config = build_site_fixture(
            tmp_path, story_id="blank_template", page_slug="blank-template"
        )
        raw_fragment = site / FRAGMENT_URL_PREFIX / "blank_template"
        slug_fragment = site / FRAGMENT_URL_PREFIX / "blank-template"
        assert raw_fragment.exists() and not slug_fragment.exists()
        assert process_site(site, data_dir, config) == 1
        assert not (site / FRAGMENT_URL_PREFIX).exists()

    def test_fragment_lookup_does_not_fall_back_to_the_slug(self, tmp_path):
        # The converse: a fragment sitting at the slugified path is not the
        # one the layout emits, and accepting it would encrypt markup that
        # never belonged to this story.
        site, data_dir, config = build_site_fixture(
            tmp_path, story_id="blank_template", page_slug="blank-template"
        )
        (site / FRAGMENT_URL_PREFIX / "blank_template").rename(
            site / FRAGMENT_URL_PREFIX / "blank-template"
        )
        with pytest.raises(GateFailure, match="rendered fragment not found"):
            process_site(site, data_dir, config)


class TestMainAborts:
    """Every abort must reach CI as an annotation, not just exit code 1."""

    def _run(self, monkeypatch, site, data_dir, config):
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.setattr(sys, "argv", [
            "encrypt_protected_stories.py",
            "--site-dir", str(site),
            "--data-dir", str(data_dir),
            "--config", str(config),
        ])
        main()

    def test_gate_failure_is_annotated(self, tmp_path, capsys, monkeypatch):
        site, data_dir, config = build_site_fixture(tmp_path)
        config.write_text("story_key: ''\n")
        with pytest.raises(SystemExit):
            self._run(monkeypatch, site, data_dir, config)
        assert "::error title=Protected stories gate::" in capsys.readouterr().out

    def test_unexpected_error_is_annotated(self, tmp_path, capsys, monkeypatch):
        # A malformed data file raises JSONDecodeError, not GateFailure. The
        # run still aborts, so it still has to say why.
        site, data_dir, config = build_site_fixture(tmp_path)
        (data_dir / "prot-story.json").write_text("{ not json")
        with pytest.raises(json.JSONDecodeError):
            self._run(monkeypatch, site, data_dir, config)
        out = capsys.readouterr().out
        assert "::error title=Protected stories script error::" in out
        assert "JSONDecodeError" in out


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
