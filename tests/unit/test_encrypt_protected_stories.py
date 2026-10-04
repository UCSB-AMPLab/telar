"""
Unit Tests for Post-Build Story Encryption

This module tests scripts/encrypt_protected_stories.py — envelope round-trip,
sentinel derivation, stub injection, the shape and content gates, the
glossary overlap acknowledgement that suppresses one story's hit on one
term's page — and the pipeline-side prerequisite check in telar/core.py
that refuses to run when the build workflow predates the post-build
encryption step.

Version: v1.8.0
"""

import base64
import json
import os
import sys

import pytest

from html import escape

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from encrypt_protected_stories import (
    _emit_actions_error,
    ACKNOWLEDGEMENT_COLUMN,
    read_glossary_acknowledgements,
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
from telar.core import (_check_protected_prerequisites,
                        PROTECTED_PREREQUISITE_EXIT)
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
    """The fixture mirrors what story.html emits for a protected page.

    Both assignments, in the order the layout writes them: the page's claim
    about which story it is, then the stub it expects to have replaced.
    """

    @staticmethod
    def stub_page(identifier="s"):
        return (
            "<script>\n"
            'window.telarStoryId = "%s";\n' % identifier
            + "window.storyData = {\"encrypted\": true, \"salt\": \"\", "
            "\"iv\": \"\", \"ciphertext\": \"" + STUB_TOKEN + "\"};\n"
            "window.objectsData = {};\n</script>"
        )

    def test_replaces_stub_with_envelope(self, tmp_path):
        page = tmp_path / "index.html"
        page.write_text(self.stub_page())
        envelope = encrypt_story({"steps": []}, STORY_KEY, aad="s")
        inject_envelope(page, envelope, "s")
        html = page.read_text()
        assert STUB_TOKEN not in html
        assert envelope["ciphertext"] in html
        # The following inline assignments survive the swap.
        assert "window.objectsData = {};" in html

    def test_page_without_stub_fails(self, tmp_path):
        page = tmp_path / "index.html"
        page.write_text('<script>window.telarStoryId = "s";\n'
                        "window.storyData = {steps: []};</script>")
        with pytest.raises(GateFailure):
            inject_envelope(page, encrypt_story([], STORY_KEY), "s")

    def test_a_page_claiming_another_story_is_refused(self, tmp_path):
        """The manifest says where a story renders; the page says who it is.

        Swapping two identifiers inside an otherwise valid manifest puts
        each envelope on the other's page. Both stubs are consumed and no
        destination conflict occurs, so nothing downstream notices — and
        the site ships two protected stories that cannot be opened, because
        the identifier the browser passes as the envelope's additional
        authenticated data is the one on the page, not the one encrypted.
        """
        page = tmp_path / "index.html"
        page.write_text(self.stub_page("the-other-story"))

        with pytest.raises(GateFailure) as failure:
            inject_envelope(page, encrypt_story({"steps": []}, STORY_KEY,
                                                aad="s"), "s")

        assert "the-other-story" in str(failure.value)

    def test_the_refused_page_is_left_alone(self, tmp_path):
        """A gate that has already written is not a gate."""
        page = tmp_path / "index.html"
        page.write_text(self.stub_page("the-other-story"))
        before = page.read_text()

        with pytest.raises(GateFailure):
            inject_envelope(page, encrypt_story({"steps": []}, STORY_KEY,
                                                aad="s"), "s")

        assert page.read_text() == before

    def test_a_page_that_names_no_story_is_refused(self, tmp_path):
        page = tmp_path / "index.html"
        page.write_text(self.stub_page().replace(
            'window.telarStoryId = "s";\n', ''))

        with pytest.raises(GateFailure) as failure:
            inject_envelope(page, encrypt_story({"steps": []}, STORY_KEY,
                                                aad="s"), "s")

        assert "telarStoryId" in str(failure.value)

    def test_an_identifier_needing_escapes_still_matches(self, tmp_path):
        """`jsonify` writes a JSON string, so the claim is parsed as one."""
        page = tmp_path / "index.html"
        page.write_text(self.stub_page("acentu\\u00e1da"))
        envelope = encrypt_story({"steps": []}, STORY_KEY, aad="acentuáda")

        inject_envelope(page, envelope, "acentuáda")

        assert STUB_TOKEN not in page.read_text()


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
    (story_dir / "index.html").write_text(TestInjection.stub_page(story_id))

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
        # the page found there, which neither names this story nor carries
        # the protected layout's stub. Either refusal is enough; the first
        # is the one that fires.
        site, data_dir, config = build_site_fixture(tmp_path)
        (site / "stories" / "prot-story" / "index.html").write_text(
            "<html><body>a page that is not the story</body></html>"
        )
        with pytest.raises(GateFailure, match="does not declare which story"):
            process_site(site, data_dir, config)

    def test_a_swapped_manifest_fails_closed(self, tmp_path):
        """Two identifiers exchanged inside an otherwise valid manifest.

        Each envelope goes to the other's page: both stubs are consumed,
        no destination conflict occurs, and every downstream sweep passes,
        because nothing leaked — the site simply ships two protected
        stories that no password can open.
        """
        site, data_dir, config = build_site_fixture(tmp_path)
        other = site / "stories" / "other-story"
        other.mkdir(parents=True)
        (other / "index.html").write_text(TestInjection.stub_page("other-story"))
        # Edited after the fact, because build_manifest derives the URL
        # from the identifier and so cannot express the swap — which is
        # the threat exactly: a manifest that did not come from a build.
        manifest = build_manifest([("prot-story", "_stories/prot-story.md")])
        manifest['stories']['prot-story']['url'] = '/stories/other-story/'
        write_manifest(data_dir, manifest)

        # Matched on the gate's own wording: a bare identifier also
        # appears in the failures a disabled gate would produce later.
        with pytest.raises(GateFailure, match="but that page is"):
            process_site(site, data_dir, config)

    def test_two_swapped_stories_fail_closed(self, tmp_path):
        """The shape the deferral was about, with nothing else to catch it.

        With one story misdirected the shape sweep still fires, because the
        story left alone keeps its stub. With two exchanged, both stubs are
        consumed, both fragments are deleted, no destination conflict
        occurs and every sweep passes — and the site ships two protected
        stories that no password opens, because the identifier the browser
        passes as the envelope's additional authenticated data is the one
        written on the page.
        """
        data_dir = tmp_path / "_data"
        data_dir.mkdir()
        identifiers = ["story-one", "story-two"]
        (data_dir / "project.json").write_text(json.dumps(
            [{"stories": [{"number": str(n), "title": "P", "story_id": i,
                           "protected": True}
                          for n, i in enumerate(identifiers, 1)]}]
        ))
        for identifier in identifiers:
            (data_dir / f"{identifier}.json").write_text(json.dumps(STEPS))

        manifest = build_manifest(
            [(i, f"_stories/{i}.md") for i in identifiers])
        manifest['stories']['story-one']['url'] = '/stories/story-two/'
        manifest['stories']['story-two']['url'] = '/stories/story-one/'
        write_manifest(data_dir, manifest)

        config = tmp_path / "_config.yml"
        config.write_text(f'story_key: "{STORY_KEY}"\n')

        site = tmp_path / "_site"
        for identifier in identifiers:
            story_dir = site / "stories" / identifier
            story_dir.mkdir(parents=True)
            (story_dir / "index.html").write_text(
                TestInjection.stub_page(identifier))
            fragment_dir = site / FRAGMENT_URL_PREFIX / identifier
            fragment_dir.mkdir(parents=True)
            (fragment_dir / "index.html").write_text(
                f"<html><body>{FRAGMENT_START}<div class='step-data'>steps"
                f"</div>{FRAGMENT_END}</body></html>"
            )
        (site / "index.html").write_text("<html>homepage</html>")

        with pytest.raises(GateFailure, match="but that page is"):
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
    """_check_protected_prerequisites reads _config.yml from the CWD.

    The exit code is asserted, not just the exit. It is the signal the
    upgrade reads to tell "this site has a workflow left to edit" from
    "the conversion failed", so a refusal that exits 1 would put a site
    back to being stranded at its old version.
    """

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
        with pytest.raises(SystemExit) as exit_info:
            _check_protected_prerequisites(data_dir, workflow_path=workflow)

        assert exit_info.value.code == PROTECTED_PREREQUISITE_EXIT

    def test_missing_workflow_trips_interlock(self, tmp_path, monkeypatch):
        data_dir = self._setup(tmp_path, monkeypatch)
        with pytest.raises(SystemExit) as exit_info:
            _check_protected_prerequisites(
                data_dir, workflow_path=tmp_path / "absent.yml"
            )

        assert exit_info.value.code == PROTECTED_PREREQUISITE_EXIT

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
        with pytest.raises(SystemExit) as exit_info:
            _check_protected_prerequisites(data_dir, workflow_path=workflow)

        assert exit_info.value.code == PROTECTED_PREREQUISITE_EXIT



# A passage of the fixture story's own prose, long enough to be a sentinel.
QUOTED_PASSAGE = "What does the unit fixture ask about exactly"

SECOND_STEPS = [
    {"step": "1",
     "question": "Which passage does the second story keep to itself",
     "answer": "A second plain protected passage, from the other story."},
]
SECOND_PASSAGE = "Which passage does the second story keep to itself"


def meta_tag(name, value):
    """One tag as the layout writes it: the value as JSON, then escaped."""
    return (f'<meta name="{name}" '
            f'content="{escape(json.dumps(value), quote=True)}">')


def glossary_markup(term_id, definition, acknowledges=(), term_meta=None,
                    meta=None, head=True):
    """A rendered glossary term page, as the glossary layout writes one.

    `term_meta` and `meta` replace a tag's content verbatim, for the shapes
    a layout should not be able to emit and the sweep must refuse anyway;
    `head=False` puts the tags in the body, where they say nothing.
    """
    tags = []
    if term_meta is not None:
        tags.append(f'<meta name="telar-term-id" content="{term_meta}">')
    else:
        tags.append(meta_tag("telar-term-id", term_id))
    if meta is not None:
        tags.append(f'<meta name="telar-quoted-in-stories" content="{meta}">')
    elif acknowledges:
        tags.append(meta_tag("telar-quoted-in-stories", list(acknowledges)))
    markup = "".join(tags)
    if head:
        return ("<html><head>" + markup + "</head><body><p>" + definition
                + "</p></body></html>")
    return ("<html><head></head><body>" + markup + "<p>" + definition
            + "</p></body></html>")


def add_glossary_page(site, term_id, definition, acknowledges=(), url=None,
                      markup=None, **shape):
    """Write the page a glossary term rendered to, tags and all.

    The page is the whole input: the sweep reads the acknowledgement out of
    _site and never asks a record where the term was going to render.
    """
    page = site / (url or f"glossary/{term_id}") / "index.html"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(markup if markup is not None else glossary_markup(
        term_id, definition, acknowledges, **shape))
    return page


def build_two_story_fixture(tmp_path):
    """The one-story fixture with a second protected story beside it."""
    site, data_dir, config = build_site_fixture(tmp_path)
    (data_dir / "project.json").write_text(json.dumps(
        [{"stories": [
            {"number": "1", "title": "P", "story_id": "prot-story",
             "protected": True},
            {"number": "2", "title": "Q", "story_id": "other-story",
             "protected": True},
        ]}]
    ))
    (data_dir / "other-story.json").write_text(json.dumps(SECOND_STEPS))
    write_manifest(data_dir, build_manifest(
        [("prot-story", "_stories/prot-story.md"),
         ("other-story", "_stories/other-story.md")]
    ))
    story_dir = site / "stories" / "other-story"
    story_dir.mkdir(parents=True)
    (story_dir / "index.html").write_text(TestInjection.stub_page("other-story"))
    fragment_dir = site / FRAGMENT_URL_PREFIX / "other-story"
    fragment_dir.mkdir(parents=True)
    (fragment_dir / "index.html").write_text(
        f"<html><body>{FRAGMENT_START}<div>second story</div>"
        f"{FRAGMENT_END}</body></html>"
    )
    return site, data_dir, config


def open_stories_fixture(tmp_path):
    """A site with stories, none of them protected."""
    data_dir = tmp_path / "_data"
    data_dir.mkdir()
    (data_dir / "project.json").write_text(json.dumps(
        [{"stories": [{"number": "1", "title": "O", "story_id": "open-story"}]}]
    ))
    config = tmp_path / "_config.yml"
    config.write_text("story_key: ''\n")
    site = tmp_path / "_site"
    site.mkdir()
    (site / "index.html").write_text("<html>homepage</html>")
    return site, data_dir, config


class TestOverlapAcknowledgement:
    """A glossary term names the protected stories it quotes on purpose.

    The page states it, at the path it rendered to. The acknowledgement is
    one record wide and one story wide: it belongs to the page the author
    wrote the quotation on, and to the story they named there.
    """

    def test_an_acknowledged_overlap_passes(self, tmp_path):
        site, data_dir, config = build_site_fixture(tmp_path)
        add_glossary_page(site, "unit-fixture",
                          f"A term that quotes: {QUOTED_PASSAGE}.",
                          acknowledges=["prot-story"])

        assert process_site(site, data_dir, config) == 1

    def test_the_suppression_is_reported_with_the_record_and_column(
            self, tmp_path, capsys):
        site, data_dir, config = build_site_fixture(tmp_path)
        page = add_glossary_page(site, "unit-fixture",
                                 f"A term that quotes: {QUOTED_PASSAGE}.",
                                 acknowledges=["prot-story"])
        process_site(site, data_dir, config)

        out = capsys.readouterr().out
        assert str(page) in out
        assert "prot-story" in out
        assert "glossary.csv:unit-fixture.quoted_in_stories" in out

    def test_a_story_the_page_does_not_name_still_fails(self, tmp_path):
        # The acknowledgement covers one story, not the page: a passage
        # from a second protected story on the same term's page is a leak
        # nobody declared.
        site, data_dir, config = build_two_story_fixture(tmp_path)
        add_glossary_page(
            site, "unit-fixture",
            f"A term that quotes: {QUOTED_PASSAGE}. And also: "
            f"{SECOND_PASSAGE}.",
            acknowledges=["prot-story"]
        )

        with pytest.raises(GateFailure, match="other-story"):
            process_site(site, data_dir, config)

    def test_the_same_passage_on_another_page_still_fails(self, tmp_path):
        # The acknowledgement is one record wide. A paste of the same
        # quotation onto a page that acknowledges nothing is the case the
        # gate exists for.
        site, data_dir, config = build_site_fixture(tmp_path)
        add_glossary_page(site, "unit-fixture",
                          f"A term that quotes: {QUOTED_PASSAGE}.",
                          acknowledges=["prot-story"])
        (site / "index.html").write_text(f"<html>{QUOTED_PASSAGE}</html>")

        with pytest.raises(GateFailure, match="Protected plaintext"):
            process_site(site, data_dir, config)

    def test_a_symlink_to_an_acknowledged_page_grants_nothing(self, tmp_path):
        # The reproduced defect: resolving both paths to the file they
        # share made the homepage's own hit look like the glossary page's.
        # Paths are compared as the sweep names them, and a link to a page
        # is not the page the acknowledgement was written on.
        site, data_dir, config = build_site_fixture(tmp_path)
        page = add_glossary_page(site, "unit-fixture",
                                 f"A term that quotes: {QUOTED_PASSAGE}.",
                                 acknowledges=["prot-story"])
        (site / "index.html").unlink()
        (site / "index.html").symlink_to(page)

        with pytest.raises(GateFailure, match="index.html"):
            process_site(site, data_dir, config)

    def test_an_empty_slug_does_not_acknowledge_the_glossary_index(
            self, tmp_path):
        # A term id of pure punctuation slugifies to nothing, and a sweep
        # that built /glossary/<slug>/index.html from it named the glossary
        # index instead. Nothing is built from the id any more.
        site, data_dir, config = build_site_fixture(tmp_path)
        add_glossary_page(site, "!!!", "A term that quotes nothing.",
                          acknowledges=["prot-story"], url="glossary/punct")
        index = site / "glossary" / "index.html"
        index.parent.mkdir(parents=True, exist_ok=True)
        index.write_text(f"<html>{QUOTED_PASSAGE}</html>")

        with pytest.raises(GateFailure, match="Protected plaintext"):
            process_site(site, data_dir, config)

    def test_two_ids_with_one_slug_keep_their_own_pages(self, tmp_path):
        # `a-b` and `a_b` slugify alike. One file has one path, so the two
        # pages cannot share a record whatever their ids look like.
        site, data_dir, config = build_site_fixture(tmp_path)
        add_glossary_page(site, "a-b", f"Quoting: {QUOTED_PASSAGE}.",
                          acknowledges=["prot-story"], url="glossary/a-b")
        add_glossary_page(site, "a_b", f"Quoting: {QUOTED_PASSAGE}.",
                          url="glossary/a-b-1")

        with pytest.raises(GateFailure, match="a-b-1"):
            process_site(site, data_dir, config)

    def test_a_page_carries_its_tags_wherever_it_rendered(self, tmp_path):
        # A document-level permalink puts a term somewhere no permalink
        # template predicts. The page says what it is at the address it is.
        site, data_dir, config = build_site_fixture(tmp_path)
        add_glossary_page(site, "unit-fixture",
                          f"A term that quotes: {QUOTED_PASSAGE}.",
                          acknowledges=["prot-story"], url="elsewhere")

        assert process_site(site, data_dir, config) == 1

    def test_an_unacknowledged_glossary_hit_names_the_way_out(self, tmp_path):
        site, data_dir, config = build_site_fixture(tmp_path)
        add_glossary_page(site, "unit-fixture",
                          f"A term that quotes: {QUOTED_PASSAGE}.")

        with pytest.raises(GateFailure) as failure:
            process_site(site, data_dir, config)

        message = str(failure.value)
        assert "prot-story" in message
        assert "unit-fixture" in message
        assert ACKNOWLEDGEMENT_COLUMN in message

    def test_a_leak_off_the_glossary_offers_only_the_two_exits(self, tmp_path):
        # A page with no acknowledgement column of its own must not be
        # pointed at one.
        site, data_dir, config = build_site_fixture(tmp_path)
        (site / "index.html").write_text(f"<html>{QUOTED_PASSAGE}</html>")

        with pytest.raises(GateFailure) as failure:
            process_site(site, data_dir, config)

        assert ACKNOWLEDGEMENT_COLUMN not in str(failure.value)

    def test_an_unknown_story_warns_with_the_term_and_the_id(
            self, tmp_path, capsys):
        site, data_dir, config = build_site_fixture(tmp_path)
        add_glossary_page(site, "unit-fixture",
                          "A term that quotes nothing protected.",
                          acknowledges=["ghost-story"])
        process_site(site, data_dir, config)

        out = capsys.readouterr().out
        assert "WARNING" in out
        assert "unit-fixture" in out
        assert "ghost-story" in out

    def test_an_unknown_story_warns_where_nothing_is_protected(
            self, tmp_path, capsys):
        # The warning is about a typo, which is a typo whether or not this
        # site protects a story today.
        site, data_dir, config = open_stories_fixture(tmp_path)
        add_glossary_page(site, "unit-fixture", "A term.",
                          acknowledges=["ghost-story"])

        assert process_site(site, data_dir, config) == 0
        out = capsys.readouterr().out
        assert "unit-fixture" in out
        assert "ghost-story" in out

    def test_an_unprotected_story_is_silent(self, tmp_path, capsys):
        # An author who unprotects a story is not told the acknowledgement
        # is stale: there is nothing left to acknowledge.
        site, data_dir, config = build_site_fixture(tmp_path)
        (data_dir / "project.json").write_text(json.dumps(
            [{"stories": [
                {"number": "1", "title": "P", "story_id": "prot-story",
                 "protected": True},
                {"number": "2", "title": "O", "story_id": "open-story"},
            ]}]
        ))
        add_glossary_page(site, "unit-fixture",
                          "A term that quotes nothing protected.",
                          acknowledges=["open-story"])
        process_site(site, data_dir, config)

        assert "WARNING" not in capsys.readouterr().out

    @pytest.mark.parametrize("content", [
        # The mapping the first build let through: joined with pipes it
        # read as three ids, one of them the story.
        escape('{"x"=>"x|prot-story|x"}', quote=True),
        escape(json.dumps({"x": "prot-story"}), quote=True),
        escape(json.dumps("prot-story"), quote=True),
        escape(json.dumps([["prot-story"]]), quote=True),
        escape(json.dumps(["prot-story", 3]), quote=True),
        escape(json.dumps(["prot-story", ""]), quote=True),
        escape(json.dumps(["prot-story\nother"]), quote=True),
        "",
        "prot-story",
    ])
    def test_an_unreadable_acknowledgement_grants_nothing(
            self, tmp_path, capsys, content):
        # The value decides whether a page may publish a protected story's
        # prose, so the reading of one this cannot decode is "nothing".
        site, data_dir, config = build_site_fixture(tmp_path)
        add_glossary_page(site, "unit-fixture",
                          f"A term that quotes: {QUOTED_PASSAGE}.",
                          meta=content)

        with pytest.raises(GateFailure, match="Protected plaintext"):
            process_site(site, data_dir, config)
        assert "not a list of story ids" in capsys.readouterr().out

    @pytest.mark.parametrize("content", [
        "",
        escape(json.dumps(""), quote=True),
        escape(json.dumps("a\nb"), quote=True),
        escape(json.dumps(["unit-fixture"]), quote=True),
        "unit-fixture",
    ])
    def test_a_term_id_that_is_not_plain_text_states_no_record(
            self, tmp_path, capsys, content):
        # A page that cannot say which term it is cannot be pointed at a
        # row in the spreadsheet, and a newline would break the line the
        # gate prints about it.
        site, data_dir, config = build_site_fixture(tmp_path)
        add_glossary_page(site, "unit-fixture",
                          f"A term that quotes: {QUOTED_PASSAGE}.",
                          acknowledges=["prot-story"], term_meta=content)

        with pytest.raises(GateFailure, match="Protected plaintext"):
            process_site(site, data_dir, config)
        assert "not plain text" in capsys.readouterr().out

    def test_a_commented_out_tag_grants_nothing(self, tmp_path):
        site, data_dir, config = build_site_fixture(tmp_path)
        tags = glossary_markup("unit-fixture", "", acknowledges=["prot-story"])
        head = tags.split("<head>")[1].split("</head>")[0]
        add_glossary_page(
            site, "unit-fixture", "",
            markup=f"<html><head><!-- {head} --></head><body><p>"
                   f"{QUOTED_PASSAGE}</p></body></html>"
        )

        with pytest.raises(GateFailure, match="Protected plaintext"):
            process_site(site, data_dir, config)

    def test_a_tag_inside_a_script_grants_nothing(self, tmp_path):
        site, data_dir, config = build_site_fixture(tmp_path)
        tags = glossary_markup("unit-fixture", "", acknowledges=["prot-story"])
        head = tags.split("<head>")[1].split("</head>")[0]
        add_glossary_page(
            site, "unit-fixture", "",
            markup="<html><head><script>var t = '" + head
                   + "';</script></head><body><p>" + QUOTED_PASSAGE
                   + "</p></body></html>"
        )

        with pytest.raises(GateFailure, match="Protected plaintext"):
            process_site(site, data_dir, config)

    def test_a_tag_in_the_body_grants_nothing(self, tmp_path):
        # The layout writes to the head. A body tag is not conforming
        # markup, and honouring one would attribute the decision to a
        # spreadsheet row that need not exist.
        site, data_dir, config = build_site_fixture(tmp_path)
        add_glossary_page(site, "unit-fixture",
                          f"A term that quotes: {QUOTED_PASSAGE}.",
                          acknowledges=["prot-story"], head=False)

        with pytest.raises(GateFailure, match="Protected plaintext"):
            process_site(site, data_dir, config)

    @pytest.mark.parametrize("head", [
        '<meta content={content} name="telar-quoted-in-stories">'
        '<meta content={term} name="telar-term-id">',
        '<meta  name = "telar-term-id"  content = {term} >'
        '<meta  name = "telar-quoted-in-stories"  content = {content} >',
        "<META NAME='telar-term-id' CONTENT={term}>"
        "<META NAME='telar-quoted-in-stories' CONTENT={content}>",
    ])
    def test_the_tags_are_read_however_they_are_written(self, tmp_path, head):
        # An emitter chooses attribute order, spacing, quoting and case;
        # none of that is the acknowledgement.
        site, data_dir, config = build_site_fixture(tmp_path)
        markup = head.format(
            term='"' + escape(json.dumps("unit-fixture"), quote=True) + '"',
            content='"' + escape(json.dumps(["prot-story"]), quote=True) + '"',
        )
        add_glossary_page(
            site, "unit-fixture", "",
            markup=f"<html><head>{markup}</head><body><p>{QUOTED_PASSAGE}"
                   "</p></body></html>"
        )

        assert process_site(site, data_dir, config) == 1

    @pytest.mark.parametrize("story", ["x|prot-story|x", "prot-story'other"])
    def test_a_separator_inside_an_id_does_not_divide_it(
            self, tmp_path, capsys, story):
        # Joining with pipes made the shape of the value invisible, and a
        # pattern read a value as ending at an apostrophe: both took half
        # an id for a story this site protects. JSON says where an id ends.
        site, data_dir, config = build_site_fixture(tmp_path)
        add_glossary_page(site, "unit-fixture",
                          f"A term that quotes: {QUOTED_PASSAGE}.",
                          acknowledges=[story])

        with pytest.raises(GateFailure, match="Protected plaintext"):
            process_site(site, data_dir, config)
        assert repr(story) in capsys.readouterr().out

    @pytest.mark.parametrize("head", [
        # No `</head>`: a head ends at the first thing that cannot be in
        # one, which is how a browser reads it too.
        "<head><body>{tags}",
        "<head><p>{tags}",
        "<head><title>t</title><div>{tags}",
        # Conditional content is not something a page states.
        "<head><noscript>{tags}</noscript></head><body>",
        "<head><noscript><noscript>{tags}</noscript></noscript></head>",
        # Inert until a script clones it, so not something the page states.
        "<head><template>{tags}</template></head><body>",
        # A head that opens after content began is not this document's head.
        "<html><body><head>{tags}</head>",
        # And neither is a second one after the first has closed.
        "<head></head><body></body><head>{tags}</head>",
    ])
    def test_tags_outside_an_open_head_grant_nothing(self, tmp_path, head):
        site, data_dir, config = build_site_fixture(tmp_path)
        tags = (meta_tag("telar-term-id", "unit-fixture")
                + meta_tag("telar-quoted-in-stories", ["prot-story"]))
        add_glossary_page(
            site, "unit-fixture", "",
            markup="<html>" + head.format(tags=tags)
                   + f"<p>{QUOTED_PASSAGE}</p></body></html>"
        )

        with pytest.raises(GateFailure, match="Protected plaintext"):
            process_site(site, data_dir, config)

    @pytest.mark.parametrize("head", [
        "<html><head><title>t</title>{tags}</head><body>",
        # A doctype and the html element precede every real head.
        "<!doctype html><html><head>{tags}</head><body>",
        # A template's contents are not in the head, so they do not end it.
        "<html><head><template><div></div></template>{tags}</head><body>",
    ])
    def test_a_real_head_still_states_its_tags(self, tmp_path, head):
        """The guards above must not cost the shape the layout writes."""
        site, data_dir, config = build_site_fixture(tmp_path)
        tags = (meta_tag("telar-term-id", "unit-fixture")
                + meta_tag("telar-quoted-in-stories", ["prot-story"]))
        add_glossary_page(
            site, "unit-fixture", "",
            markup=head.format(tags=tags)
                   + f"<p>{QUOTED_PASSAGE}</p></body></html>"
        )

        assert process_site(site, data_dir, config) == 1

    def test_a_tag_with_no_content_states_nothing(self, tmp_path, capsys):
        # The parser reports a missing attribute as None, which is a shape
        # like any other rather than a reason to stop the build.
        site, data_dir, config = build_site_fixture(tmp_path)
        add_glossary_page(
            site, "unit-fixture", "",
            markup='<html><head>'
                   + meta_tag("telar-term-id", "unit-fixture")
                   + '<meta name="telar-quoted-in-stories">'
                   + f"</head><body><p>{QUOTED_PASSAGE}</p></body></html>"
        )

        with pytest.raises(GateFailure, match="Protected plaintext"):
            process_site(site, data_dir, config)
        assert "not a list of story ids" in capsys.readouterr().out

    @pytest.mark.parametrize("control", ["\x00", "\x1f", "\x7f", "\x85",
                                         "\x9b", "\u2028", "\u2029"])
    def test_a_control_character_in_an_id_states_nothing(
            self, tmp_path, capsys, control):
        # C1 and the Unicode separators end a line wherever the build
        # output is read, and none of them is a character typed into a
        # cell.
        site, data_dir, config = build_site_fixture(tmp_path)
        add_glossary_page(site, "unit-fixture",
                          f"A term that quotes: {QUOTED_PASSAGE}.",
                          acknowledges=[f"prot{control}story"])

        with pytest.raises(GateFailure, match="Protected plaintext"):
            process_site(site, data_dir, config)
        assert "not a list of story ids" in capsys.readouterr().out

    @pytest.mark.parametrize("control", ["\x00", "\x1f", "\x7f", "\x85",
                                         "\x9b", "\u2028", "\u2029"])
    def test_a_control_character_in_a_term_id_states_nothing(
            self, tmp_path, capsys, control):
        site, data_dir, config = build_site_fixture(tmp_path)
        add_glossary_page(
            site, "unit-fixture", "",
            markup="<html><head>"
                   + meta_tag("telar-term-id", f"unit{control}fixture")
                   + meta_tag("telar-quoted-in-stories", ["prot-story"])
                   + f"</head><body><p>{QUOTED_PASSAGE}</p></body></html>"
        )

        with pytest.raises(GateFailure, match="Protected plaintext"):
            process_site(site, data_dir, config)
        assert "not plain text" in capsys.readouterr().out

    def test_a_page_with_no_tags_is_not_a_record(self, tmp_path):
        site, data_dir, config = build_site_fixture(tmp_path)

        assert read_glossary_acknowledgements(site) == {}

    def test_a_term_acknowledging_nothing_is_still_located(self, tmp_path):
        site, data_dir, config = build_site_fixture(tmp_path)
        page = add_glossary_page(site, "unit-fixture",
                                 "A term that quotes nothing protected.")

        assert read_glossary_acknowledgements(site) == {
            str(page): ("unit-fixture", set())
        }

    def test_escaped_ids_are_read_back_as_written(self, tmp_path):
        # The layout escapes the JSON into an attribute; the parser hands
        # it back unescaped, so an ampersand in an id survives the trip.
        site, data_dir, config = build_site_fixture(tmp_path)
        page = add_glossary_page(site, "café", "A term.",
                                 acknowledges=["a&b", 'quote"d'],
                                 url="glossary/cafe")

        assert read_glossary_acknowledgements(site) == {
            str(page): ("café", {"a&b", 'quote"d'})
        }
