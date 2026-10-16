"""Unit Tests for an Upgrade That Finishes When Tile Generation Runs Long

Tile generation is the soft step of data regeneration: the build generates
tiles again, so a tile failure is reported and the upgrade completes. A
site with many large local images can need longer than the step's time
limit, and running out of time must be treated the same way: a tile
failure, never a failed upgrade that leaves the site at its old version.

Driven through real subprocesses, with the limit shortened, because the
behavior under test is what happens when a child process is stopped.

Version: v1.8.2
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

import telar_upgrade as upgrade
import telar_upgrade_regen as regen
from migrations.messages import get_message


def _site(tmp_path, lang='en', tile_seconds=30):
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    (scripts / 'csv_to_json.py').write_text('import sys\nsys.exit(0)\n', encoding='utf-8')
    (scripts / 'generate_collections.py').write_text('import sys\nsys.exit(0)\n', encoding='utf-8')
    (scripts / 'generate_iiif.py').write_text(
        'import time\ntime.sleep(%d)\n' % tile_seconds, encoding='utf-8')
    (tmp_path / '_config.yml').write_text(f'telar_language: "{lang}"\n', encoding='utf-8')
    return str(tmp_path)


class TestTileTimeout:

    def test_running_out_of_time_on_tiles_is_a_tile_failure(self, tmp_path, monkeypatch):
        monkeypatch.setattr(regen, 'IIIF_TIMEOUT_SECONDS', 1)

        csv_ok, iiif_ok, blocked = upgrade._regenerate_data_files(_site(tmp_path))

        assert (csv_ok, iiif_ok, blocked) == (True, False, False)

    def test_it_says_so_in_the_sites_language(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(regen, 'IIIF_TIMEOUT_SECONDS', 1)

        upgrade._regenerate_data_files(_site(tmp_path, lang='es'))

        assert get_message('es', 'regeneration_iiif_timeout', 1) in capsys.readouterr().out

    def test_tiles_that_finish_in_time_are_not_a_failure(self, tmp_path, monkeypatch):
        monkeypatch.setattr(regen, 'IIIF_TIMEOUT_SECONDS', 30)

        assert upgrade._regenerate_data_files(_site(tmp_path, tile_seconds=0)) == (True, True, False)
