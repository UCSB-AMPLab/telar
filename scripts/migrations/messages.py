"""
Bilingual Messages for the Telar Upgrade System

This module deals with every user-facing string the upgrade workflow
prints or writes, in both English and Spanish, so that `upgrade.py` and
the individual migrations never hardcode language-specific text. A site's
language comes from `telar_language` in `_config.yml`; the upgrade code
reads it once and then asks this module for each string by key.

`MESSAGES` is a two-level dictionary — `'en'` and `'es'`, each mapping a
stable key to its translated string. Keys are grouped by where they
surface: the upgrade console output, the fail-closed / resume flow, the
sections and category headings of the generated `UPGRADE_SUMMARY.md`, and
the common phrases migrations reuse. Some strings carry `{}` placeholders
filled in at call time (a version number, a file path, a count).

`get_message(lang, key, *args)` is the main entry point. It normalises an
unknown language code to English, looks the key up in the requested
language, falls back to the English string (and finally the raw key) when
a translation is missing, and applies `str.format()` only when arguments
are supplied — returning the unformatted string rather than raising if the
placeholders and arguments do not line up.

`get_file_count_suffix(lang, count)` is a small helper for the one place
grammatical number matters in the summary: it returns the singular or
plural of "file" in the active language so category headings read
naturally ("1 file" / "2 files", "1 archivo" / "2 archivos").

Version: v1.8.0
"""

MESSAGES = {
    'en': {
        # upgrade.py console messages
        'upgrade_title': 'Telar Upgrade Script',
        'detecting_version': 'Detecting current version...',
        'current_version': 'Current version: {}',
        'target_version': 'Target version:  {}',
        'already_updated': '✓ Already at latest version!',
        'no_migrations': 'No migrations found from {} to {}',
        'unsupported_note': "This might indicate an unsupported version or that you're already up to date.",
        'migrations_to_apply': 'Migrations to apply: {}',
        'applying_migrations': 'Applying migrations...',
        'updating_config': 'Updating _config.yml with new version...',
        'config_updated': '✓ Updated _config.yml to version {}',
        'config_update_warning': '⚠️  Warning: Could not update _config.yml version',
        'regenerating_data': 'Regenerating data files and IIIF tiles...',
        'data_regenerated': '✓ Regenerated data files and IIIF tiles',
        'data_regenerate_warning': '⚠️  Warning: Could not regenerate data files (scripts may not exist)',
        'upgrade_complete': '✓ Upgrade complete!',
        'created_summary': 'Created: UPGRADE_SUMMARY.md',
        'review_summary': 'Please review UPGRADE_SUMMARY.md for any manual steps.',
        'uncommitted_warning': '⚠️  Warning: You have uncommitted changes.',
        'uncommitted_recommend': "It's recommended to commit or stash your changes before upgrading.",
        'continue_anyway': 'Continue anyway? (y/N): ',
        'upgrade_cancelled': 'Upgrade cancelled.',
        'dry_run_mode': '[DRY RUN MODE - No changes will be made]',
        'dry_run_complete': '[DRY RUN COMPLETE]',
        'dry_run_instruction': 'Run without --dry-run to apply these changes.',
        'dry_run_would_apply': '[DRY RUN] Would apply this migration',

        # Console output on the version-detection, migration-failure and
        # data-regeneration paths. These print; they are not change
        # descriptions, so none of them reaches coerce_change and the note
        # above about the English phrase that classifies does not apply.
        'config_not_found': '❌ Error: _config.yml not found. Are you in a '
                            'Telar repository?',
        'version_unrecognised': '⚠️  Warning: Unrecognized version "{}" in '
                                '_config.yml.',
        'version_not_text': '⚠️  Warning: Unrecognized version {} in '
                            '_config.yml (the value is not text — quote it).',
        'version_grammar': 'Expected MAJOR.MINOR.PATCH, with an optional '
                           '"-beta" suffix, for example version: "1.6.2" or '
                           'version: "0.9.4-beta". A leading "v" is accepted '
                           'but belongs to git tags, not to this field.',
        'version_missing': 'Warning: No version found in _config.yml, '
                           'assuming 0.2.0-beta',
        'config_read_error': '❌ Error reading _config.yml: {}',
        'migration_error': '✗ Error: {}',
        'migration_stopped': '✗ Stopping: this migration did not complete.',
        'regeneration_script_error': '⚠️  Warning: {} returned error: {}',
        'regeneration_timeout': '⚠️  Warning: Data regeneration timed out',
        'regeneration_failed': '⚠️  Warning: Data regeneration failed: {}',
        'index_no_frontmatter': '[WARN] index.md has no leading frontmatter '
                                'delimiter — skipping upgrade-notice insertion',
        'index_frontmatter_unclosed': '[WARN] index.md frontmatter is not '
                                      'closed — skipping upgrade-notice '
                                      'insertion',
        'fetch_failed_console': '⚠️  Warning: Could not fetch {} from '
                                'GitHub: {}',
        'fetch_error_console': '⚠️  Warning: Error fetching {}: {}',

        # Fail-closed / resume console messages (v1.5.0 redesign)
        'prev_upgrade_incomplete': 'ℹ️  A previous upgrade to {} did not complete.',
        'prev_upgrade_rerun': '   Re-running it now. The site was left at its previous version, so this re-applies the same files from scratch.',
        'no_tty_continue': '(No interactive terminal — continuing.)',
        'upgrade_failed_steps': '✗ Upgrade did not complete: {} required step(s) failed.',
        'upgrade_completed_with_flags': '⚠️  {} file(s) could not be installed; they '
                                        'are listed in UPGRADE_SUMMARY.md. The site '
                                        'still reached {}. This is a fault in Telar '
                                        'rather than in your site — please report it.',
        'upgrade_not_applied': '  The site was NOT upgraded and its version was left unchanged.',
        'upgrade_reached_version': '  The upgrade stopped, but your site did advance: '
                                   'it is now at {}. Run the upgrade again and it will '
                                   'continue from there up to {}.',
        'transient_retry': '  This is usually a transient network problem.',
        'see_summary_failures': '  See UPGRADE_SUMMARY.md for the list of failures.',
        'upgrade_failed_data': '✗ Upgrade did not complete: data regeneration failed.',
        'see_summary_details': '  See UPGRADE_SUMMARY.md for details.',
        'data_files_regenerated': '✓ Regenerated data files',
        'chain_stops': '⚠️  Migration chain stops at {}: no registered migration continues from there toward {}.',
        'chain_stops_note': '    This usually means the current version is unsupported or a migration is missing from the chain — review manually before proceeding.',

        # Phase labels (for migration console output)
        'phase': 'Phase {}',

        # UPGRADE_SUMMARY.md structure
        'summary_title': 'Upgrade Summary',
        'summary_from': 'From',
        'summary_to': 'To',
        'summary_date': 'Date',
        'summary_automated_changes': 'Automated changes',
        'summary_manual_steps': 'Manual steps',
        'summary_failed_count': 'Failed / needs attention',
        'automated_changes_applied': 'Automated Changes Applied',
        'failed_needs_attention': 'Failed / Needs Manual Attention',
        'failed_section_body': 'The following changes did not complete automatically. The site was **not** upgraded to the new version. Resolve these (usually a transient network problem) and run the upgrade again.',
        # A separate section, because the body above is false of these: the
        # upgrade did complete, and running it again changes nothing.
        'summary_flagged_count': 'Files not installed',
        'flagged_needs_attention': 'Files Not Installed',
        'flagged_section_body': 'These files are not part of the new Telar release, so they could not be installed. The upgrade **did** complete and your site is at that version — running it again will not change this. Please report them so the release can be fixed.',
        'completed_with_warnings': 'Completed With Warnings',
        'warnings_section_body': 'These steps are non-fatal and did not block the upgrade, but you should check them:',
        'manual_steps_required': 'Manual Steps Required',
        'complete_after_merge': 'Please complete these steps:',
        'no_manual_steps': 'No Manual Steps Required',
        'all_automated': 'All changes have been automated!',
        'resources': 'Resources',
        'guide': 'guide',
        'full_documentation': 'Full Documentation',
        'changelog': 'CHANGELOG',
        'report_issues': 'Report Issues',

        # Category labels (for organizing changes in UPGRADE_SUMMARY.md)
        'category_configuration': 'Configuration',
        'category_layouts': 'Layouts',
        'category_includes': 'Includes',
        'category_styles': 'Styles',
        'category_scripts': 'Scripts',
        'category_documentation': 'Documentation',
        'category_other': 'Other',

        # File count suffix (for category headings)
        'file': 'file',
        'files': 'files',

        # Common messages used across migrations
        'created_directory': 'Created directory: {}',
        'moved_file': 'Moved {} → {}',
        'removed_file': 'Removed file: {}',
        'removed_directory': 'Removed directory: {}',
        'updated_file': 'Updated {}',
        'fetched_file': 'Updated {}: {}',
        'file_exists': '{} already exists',
        'empty_directory_removed': 'Removed empty directory: {}',
        'could_not_remove': '⚠️  Warning: Could not remove {}: {}',

        # Safety messages (for preserved user content)
        'kept_modified_files': '⚠️  Kept {} user-modified demo files',
        'kept_images_safety': 'ℹ️  Kept {} old demo images for safety',
        'manual_delete_note': '(You can manually delete these if not using them)',

        # Records written into the upgrade summary on a failure, and the
        # console messages of the dependency-ensure step. Both are localised
        # so a site reads its failures in its own language.
        #
        # record_fetch_failed carries the phrase coerce_change treats as a
        # hard failure, but the record it fills is built with severity
        # 'hard' already -- the phrase is not what classifies it here,
        # which is why this one is safe to translate. A migration that
        # returns a bare string is a different matter: there the English
        # phrase IS the classification, so it stays English.
        'record_deps_missing': 'Data regeneration dependencies are missing ({}). '
                               'Data regeneration cannot run without them, so the '
                               'site was not upgraded. Install the packages listed '
                               'in requirements.txt and re-run the upgrade.',
        'record_regeneration_failed': 'Data regeneration (csv_to_json / '
                                      'generate_collections) failed. Run the data '
                                      'scripts by hand and try the upgrade again.',
        'record_migration_aborted': 'The {} \u2192 {} migration stopped: {}',
        'config_note_section_vs_value': '{} is a section on this site and a '
                                        'single value in the release \u2014 left '
                                        'as the release has it',
        'config_note_unwritable_value': '{} could not be written back as YAML '
                                       '\u2014 left as the release has it',
        'config_note_release_owns_list': "{} is a list the release owns; this "
                                        "site's own is not carried across",
        'config_note_unwritable_list_item': '{} holds something that could not '
                                           'be written back as YAML \u2014 left '
                                           'as the release has it',
        'config_note_kept_list_entries': "Kept this site's own {} entries: {}",
        'config_note_unwritable_not_carried': '{} could not be written back as '
                                             'YAML and was not carried across',
        'config_note_carried_into': 'Carried {} across into {}',
        'manual_step_record_version': 'Record the version in `_config.yml`. This site has no `telar:` section for the upgrade to write it in, and the upgrade rewrites that section rather than creating it, because it cannot tell what else your site keeps there. Add `telar:` at the top of the file, and under it, indented, `version: "{}"` and `release_date: "{}"`. Everything else is already done; without these lines the next upgrade will not know which release this site is on, and will run the whole thing again over content that is already current.',
        'config_note_carried_top_level': 'Carried {} across \u2014 the release '
                                        'does not have it',
        'stamp_date_unknown': 'Telar {} has no release date recorded yet, so '
                               'the upgrade is stamping today. This happens only '
                               'before a release is tagged.',
        'record_protected_unencryptable': (
            'This site has stories marked protected, and '
            '.github/workflows/build.yml does not run '
            'scripts/encrypt_protected_stories.py, so the build will refuse '
            'to publish rather than put protected text in the clear. The '
            'upgrade itself is finished and the data files are current; this '
            'is what is left. Open the current build.yml in the Telar '
            'repository on GitHub, choose "Copy raw contents", paste it over '
            'your copy, and commit. GitHub does not let an upgrade write '
            'workflow files, which is why this one is yours \u2014 the Telar '
            'Compositor commits them itself, so a site upgraded through it '
            'does not need this step. If none of those stories is meant to be '
            'private, removing the protected mark is the other way out.'),
        'record_fetch_failed': 'Could not fetch {} from GitHub (Telar version {}). '
                               'Update it by hand.',
        # The counterpart for a fetch no re-run can fix. It deliberately
        # avoids the 'Could not fetch' phrase: that phrase classifies a bare
        # string as a hard failure, and this failure is the soft one.
        'record_fetch_absent': '{} is not part of Telar {}, so it could not be '
                               'installed. The upgrade continued without it \u2014 '
                               'please report it.',
        'record_write_rolled_back': 'A framework file could not be written, so the '
                                    'changes were rolled back: {}',

        # Change descriptions. These name what happened to the user's own
        # content -- a directory relocated, a column renamed, an image left
        # where it was -- so they are the half of the summary a site owner
        # reads to find out what the upgrade did to their material.
        'change_concurrency_by_hand': 'Build workflow concurrency group: add the `concurrency` block '
                                   'to .github/workflows/build.yml by hand (or recopy the file). '
                                   'The in-Actions upgrade cannot modify workflow files; the Telar '
                                   'Compositor applies it automatically. See the manual step '
                                   'below.',
        'change_gitattributes_added': 'Added {} — marks the generated story bundle as '
                                   'linguist-generated',
        'change_gitattributes_skipped': 'Skipped {} (already exists) — see the manual step to merge the '
                                   'new linguist-generated markers',
        'change_gitattributes_absent': '{} did not download from GitHub. Non-fatal — add it manually '
                                   'if you want the generated-bundle markers.',
        'change_chain_wiring_internal': 'Upgrade-chain wiring fix (internal): the v1.5.4 -> v1.6.0 '
                                   'migration is now registered in scripts/upgrade.py, so upgrades '
                                   'starting below v1.6.0 no longer stop early at 1.5.4. No files '
                                   'in this site changed.',
        'change_removed_dependabot': 'Removed {} — dependency-bump pull requests are now managed by '
                                   'the Telar release process, not per-site',
        'change_could_not_remove_dependabot': 'Could not remove {}: {}. Non-fatal — delete it by hand when '
                                   'convenient. It no longer does anything: dependency-bump pull '
                                   'requests are managed by the Telar release process, not '
                                   "per-site, and GitHub's security alerts are unaffected either "
                                   'way.',
        'change_could_not_remove_superseded': 'Could not remove {}: {}. Non-fatal — delete it by hand when '
                                   'convenient. Nothing loads it any more: the layouts and scripts '
                                   'installed by this upgrade use the files that replaced it.',
        'change_could_not_fetch_config': 'Could not fetch _config.yml',
        'change_transformation_aborted': '{} aborted: {}',
        'and_n_more': 'and {} more',
        'change_gitignore_paths': 'Updated .gitignore path references (components/ → telar-content/)',
        'change_gitignore_section': 'Updated .gitignore — {}',
        'change_removed_not_telar': 'Removed {} — no longer part of Telar',
        'change_could_not_remove': 'Could not remove {}: {}',
        'change_kept_uncheckable': 'Kept {} — could not check whether it had been edited',
        'change_kept_edited': 'Kept {} — edited on this site',
        'change_removed_demo_term': 'Removed {} — withdrawn demo glossary term',
        'change_both_dirs_present': 'Both {}/ and {}/ are present. Neither was changed — please merge '
                               'them by hand.',
        'change_moved_dir': 'Moved {}/ → {}/',
        'change_kept_components': 'Kept components/ — it still holds {}',
        'change_removed_empty_components': 'Removed the empty components/ directory',
        'change_both_files_present': 'Both {} and {} are present. Neither was changed — please merge '
                               'them by hand.',
        'change_could_not_move': 'Could not move {}',
        'change_moved_file': 'Moved {} → {}',
        'change_removed_empty_pages': 'Removed the empty pages/ directory',
        'change_moved_images': 'Moved {} image(s) up out of objects/ and additional/',
        'change_kept_different_image': 'Kept {}/{}/{} — {}/{} is a different image, and the spreadsheet '
                               'names this one',
        'change_kept_both_taken': 'Kept {}/{}/{} — both {} and {} are taken in {}/',
        'change_could_not_move_image': 'Could not move {}/{}/{}: {}',
        'change_moved_renamed': 'Moved {}/{}/{} → {}/{}, renamed because {} was taken',
        'change_removed_empty_subdir': 'Removed the empty {}/{}/ directory',
        'change_rewrote_image_paths': 'Updated {} image path(s) to the flattened directory',
        'change_renamed_column': 'Renamed the {} column to {} in {}',
        'change_added_columns': 'New columns in {}: {}',
        'change_kept_no_stories': 'Kept {} — it is in the old key-value format but names no stories',
        'change_rewrote_stories_table': 'Rewrote {} as a table of {} story/stories',
        'change_kept_config_unreadable': 'Kept _config.yml as it is — it could not be read as YAML, so '
                               'nothing could be moved across safely',
        'change_rewrote_config': "Rewrote _config.yml from the release's copy, keeping this "
                                 "site's own settings",
        'change_nothing_to_remove': 'No {} to remove (already absent)',
        'change_removed_superseded': 'Removed {} — superseded by the files installed with this upgrade',
        'change_removed_stale_bundle': 'Removed stale bundle file {}',
        'change_no_stale_bundles': 'No stale bundle files to remove',
        'change_removed_dead_file': 'Removed dead file {}',
        'change_no_dead_files': 'No dead files to remove',
        'deps_installing': '  Installing the missing dependencies, from {} ...',
        'deps_no_manifest': '  \u26a0\ufe0f  Warning: cannot install the missing '
                            'dependencies ({}) because there is no requirements.txt '
                            'beside the upgrade script or in the site.',
        'deps_pip_failed': '  \u26a0\ufe0f  Warning: pip install from {} failed:\n{}',
        'deps_pip_timeout': '  \u26a0\ufe0f  Warning: pip install from {} ran out of time',

        'retired_migrations': 'Removed scripts/migrations/ — this site runs the '
                              'upgrade launcher, which downloads a verified copy '
                              'of the migrations each time it runs.',
        'retire_migrations_warning': 'Could not remove scripts/migrations/: {}. '
                                     'The upgrade completed; the directory is '
                                     'unused and can be deleted by hand.',

        # v1.8.0 migration records
        'v180_removed_stale_manifest': 'Removed migration.json, the manifest of the 1.5.4 '
                                       'upgrade, which Jekyll published as a page of your site',
        'v180_page_line_updated': 'Updated {}: its default content now comes from `{}`',
        'v180_page_line_current': '{} already has the 1.8.0 line',
        'v180_page_line_own_text': '{} has its own text in place of the default line, so it '
                                   'was left as it is. To keep the default content, the '
                                   'line is now `{}`',
        'v180_page_absent': 'No {} in this site, so there was nothing to update',
        'v180_column_dropped': 'Removed the empty column `{}` from `{}`; `{}` holds your values.',
        'v180_column_dropped_all_empty': 'Removed the empty column `{}` from `{}`; it and '
                                         '`{}` mean the same thing, both were empty, and '
                                         '`{}` was kept.',
        'v180_columns_hold_values': '`{}` has columns that mean the same thing and each '
                                    'holds values: {}. Telar cannot choose between them, so '
                                    'the next build will stop. Keep one, move the values you '
                                    'need into it, and delete the others.',
        'v180_column_in_sheet': 'Your site reads its content from a Google Sheet, and the '
                                'next build reads the sheet again. Delete the column `{}` '
                                'from the tab behind `{}` in the sheet itself, or the build '
                                'will stop on the same two columns.',
        'v180_column_not_removed': 'Could not remove the empty column `{}` from `{}` without '
                                   'changing the rest of the file, so the file was left as it '
                                   'is. Delete that column by hand: until it is gone the next '
                                   'build stops.',
        'v180_column_marked_note': 'Renamed the empty column `{}` in `{}` to `{}`, so the build '
            'ignores it. Removing the column would have changed which '
            'rows the build reads from that sheet.',
        'v180_column_marked_in_sheet': 'Your site reads its content from a Google Sheet, and the'
            ' next build reads the sheet again. In the sheet itself, '
            'rename the column `{}` in the tab behind `{}` to `{}`, '
            'or the build will stop on the same two columns.',
        'v180_column_kept_for_header_row': 'Could not remove the empty column `{}` from `{}`: '
            'without it, the build would no longer recognize the '
            'second row of column names, the one in the other '
            'language, and would publish it as content. Delete '
            'that column and that row by hand; until the column '
            'is gone, the next build stops.',
        'v180_reserved_column': '`{}` has a column named `{}`, a name Telar keeps for its own '
                                'use. Rename that column, or the next build will stop.',
        'v180_sheet_unreadable': 'Could not read `{}` to check its columns: {}',
        'v180_sheets_unchecked': 'Could not check the spreadsheets for two columns that mean '
                                 'the same thing, because the build\'s column rules could not '
                                 'be loaded ({}). If there are any, the next build stops and '
                                 'names them.',
        'v180_sheets_clean': 'No spreadsheet has two columns that mean the same thing',
        'v180_exclude_added': 'Added {} to `exclude:` in _config.yml, so Jekyll does not '
                              'publish them as pages of your site',
        'v180_exclude_present': '_config.yml already excludes {}',
        'v180_exclude_texts_failed': '_config.yml has no `exclude:` list this upgrade can add '
                                     '`telar-content/texts/` to: `exclude:` holds a single value '
                                     'or a mapping, or the file could not be read. Make '
                                     '`exclude:` a list with `- telar-content/texts/` in it '
                                     'by hand and run the upgrade again. '
                                     'Without it, Jekyll publishes an unprocessed copy of every '
                                     'page, story and glossary source, and a page that sets its '
                                     'own address stops the build.',
        'v180_exclude_others_failed': '_config.yml has no `exclude:` list this upgrade can add '
                                      '{} to. Add them under `exclude:` by hand: they are '
                                      'Telar\'s own tests, and without the entries Jekyll '
                                      'publishes them with your site.',
        'v180_page_keys_removed': 'Removed {} from {}: the build sets a page\'s layout and '
                                  'address itself',
        'v180_page_key_kept': '{} sets `{}: {}`, which the build ignores. The page is '
                              'published at {}.',
        'v180_page_source_refused': 'Left {} as it is: removing {} would have changed how the '
                                    'rest of its front matter reads. The build ignores both '
                                    'keys, so the page is published correctly either way.',
        'v180_file_unreadable': 'Could not update {}: {}',
        'v180_pages_clean': 'No page source sets a layout or address of its own',
        'v180_related_terms_listed': 'Wrote `related_terms` in {} as a list, so the page '
                                     'links each related term',
        'v180_related_terms_refused': 'Left `related_terms` in {} as it is, because it is '
                                      'written in a form this upgrade does not rewrite. Write '
                                      'it as a list, such as `related_terms: ["term-one", '
                                      '"term-two"]`, or the page will not link those terms.',
        'v180_glossary_clean': 'No glossary entry needed its `related_terms` rewritten',
        'v180_answer_over_limit': 'Story `{}`, step {}: the answer has {} words, and the build '
                                  'cuts it to {}. Shorten it to keep its ending.',
        'v180_answer_content_removed': 'Story `{}`, step {}: the build removes {} from the '
                                       'answer, which shows text only. Move it to a panel to '
                                       'keep it.',
        'v180_answer_kind_media': 'images and media',
        'v180_answer_kind_widgets': 'widgets',
        'v180_answer_kind_footnotes': 'footnotes',
        'v180_answer_kind_markup': 'the marks of lists, headings and quotes, and any tables, '
                                   'code blocks and horizontal rules',
        'v180_answers_from_local_copies': 'The answers were counted in the local copies of '
                                          'your spreadsheets. Your site reads a Google Sheet, '
                                          'and the next build reads it again, so make any '
                                          'change in the sheet itself.',
        'v180_answers_unchecked': 'Could not count the story answers, because the build\'s '
                                  'answer rules could not be loaded ({}). The next build names '
                                  'every answer it cuts.',
        'v180_answers_clean': 'No story answer is cut or loses content in the build',
        'v180_engine_removed': 'Removed {}: the upgrade runs from the verified tooling '
                               '`scripts/upgrade.py` downloads',
        'v180_engine_kept': 'Left {} in place: it is not a copy Telar released, so it may be '
                            'your own. The upgrade does not use it; delete it if nothing of '
                            'yours does.',
        'v180_engine_not_removed': 'Could not remove {}: {}. The upgrade completed; the file '
                                   'is unused and can be deleted by hand.',
    },

    'es': {
        # upgrade.py console messages
        'upgrade_title': 'Script de actualización de Telar',
        'detecting_version': 'Detectando versión actual…',
        'current_version': 'Versión actual: {}',
        'target_version': 'Versión de destino: {}',
        'already_updated': '✓ ¡Ya estás en la última versión!',
        'no_migrations': 'No se encontraron migraciones de {} a {}',
        'unsupported_note': 'Esto podría indicar una versión no compatible o que ya estás actualizado.',
        'migrations_to_apply': 'Migraciones a aplicar: {}',
        'applying_migrations': 'Aplicando migraciones…',
        'updating_config': 'Actualizando _config.yml con nueva versión…',
        'config_updated': '✓ _config.yml actualizado a versión {}',
        'config_update_warning': '⚠️  Advertencia: No se pudo actualizar la versión en _config.yml',
        'regenerating_data': 'Regenerando archivos de datos y teselas (*tiles*) IIIF…',
        'data_regenerated': '✓ Archivos de datos y teselas (*tiles*) IIIF regenerados',
        'data_regenerate_warning': '⚠️  Advertencia: No se pudieron regenerar archivos de datos (los scripts podrían no existir)',
        'upgrade_complete': '✓ Actualización completa.',
        'created_summary': 'Creado: UPGRADE_SUMMARY.md',
        'review_summary': 'Por favor revisa UPGRADE_SUMMARY.md para ver los pasos manuales.',
        'uncommitted_warning': '⚠️  Advertencia: Tienes cambios sin confirmar.',
        'uncommitted_recommend': 'Se recomienda confirmar o guardar los cambios antes de actualizar.',
        'continue_anyway': '¿Continuar de todos modos? (s/N): ',
        'upgrade_cancelled': 'Actualización cancelada.',
        'dry_run_mode': '[MODO DE PRUEBA — No se realizarán cambios]',
        'dry_run_complete': '[PRUEBA COMPLETA]',
        'dry_run_instruction': 'Ejecuta sin --dry-run para aplicar estos cambios.',
        'dry_run_would_apply': '[PRUEBA] Se aplicaría esta migración',

        # Ver la nota en la seccion en ingles: estas se imprimen, no son
        # descripciones de cambios, asi que no pasan por coerce_change.
        'config_not_found': '❌ Error: No se encontró _config.yml. ¿Estás en '
                            'un repositorio de Telar?',
        'version_unrecognised': '⚠️  Advertencia: No se reconoce la versión '
                                '"{}" en _config.yml.',
        'version_not_text': '⚠️  Advertencia: No se reconoce la versión {} en '
                            '_config.yml (el valor no es texto: ponlo entre '
                            'comillas).',
        'version_grammar': 'La versión se escribe MAYOR.MENOR.PARCHE, con '
                           '"-beta" opcional; por ejemplo version: "1.6.2" o '
                           'version: "0.9.4-beta". La "v" inicial se acepta, '
                           'pero pertenece a las etiquetas de git y no a este '
                           'campo.',
        'version_missing': 'Advertencia: No se encontró ninguna versión en '
                           '_config.yml; se parte de 0.2.0-beta',
        'config_read_error': '❌ Error al leer _config.yml: {}',
        'migration_error': '✗ Error: {}',
        'migration_stopped': '✗ La actualización se interrumpió: esta '
                             'migración no se completó.',
        'regeneration_script_error': '⚠️  Advertencia: {} devolvió un '
                                     'error: {}',
        'regeneration_timeout': '⚠️  Advertencia: Se agotó el tiempo al '
                                'regenerar los datos',
        'regeneration_failed': '⚠️  Advertencia: Falló la regeneración de '
                               'datos: {}',
        'index_no_frontmatter': '[ADVERTENCIA] index.md no empieza con el '
                                'delimitador del frontmatter; no se inserta '
                                'el aviso de actualización',
        'index_frontmatter_unclosed': '[ADVERTENCIA] El frontmatter de '
                                      'index.md no está cerrado; no se '
                                      'inserta el aviso de actualización',
        'fetch_failed_console': '⚠️  Advertencia: No se pudo descargar {} de '
                                'GitHub: {}',
        'fetch_error_console': '⚠️  Advertencia: Error al descargar {}: {}',

        # Fail-closed / resume console messages (v1.5.0 redesign)
        'prev_upgrade_incomplete': 'ℹ️  Una actualización anterior a {} quedó incompleta.',
        'prev_upgrade_rerun': '   Se reintentará ahora. El sitio quedó en su versión anterior, así que se vuelven a aplicar los mismos archivos desde cero.',
        'no_tty_continue': '(No hay terminal interactiva — se continúa.)',
        'upgrade_failed_steps': '✗ La actualización no se completó: fallaron {} paso(s) obligatorio(s).',
        'upgrade_completed_with_flags': '⚠️  No se pudieron instalar {} archivo(s); '
                                        'quedan listados en UPGRADE_SUMMARY.md. Aun '
                                        'así, el sitio sí quedó en la versión {}. La '
                                        'falla es de Telar, no de tu sitio: repórtala.',
        'upgrade_not_applied': '  El sitio no se actualizó y su versión quedó sin cambios.',
        'upgrade_reached_version': '  La actualización se detuvo, pero el sitio sí '
                                   'avanzó: quedó en la versión {}. Vuelve a '
                                   'ejecutarla y continuará desde ahí hasta la {}.',
        'transient_retry': '  Suele ser un problema temporal de red.',
        'see_summary_failures': '  Revisa UPGRADE_SUMMARY.md para ver la lista de fallas.',
        'upgrade_failed_data': '✗ La actualización no se completó: falló la regeneración de los datos.',
        'see_summary_details': '  Revisa UPGRADE_SUMMARY.md para más detalles.',
        'data_files_regenerated': '✓ Archivos de datos regenerados',
        'chain_stops': '⚠️  La cadena de migraciones se detiene en {}: ninguna migración registrada continúa desde ahí hacia {}.',
        'chain_stops_note': '    Esto suele significar que la versión actual no es compatible o que falta una migración en la cadena; revísalo a mano antes de continuar.',

        # Phase labels (for migration console output)
        'phase': 'Fase {}',

        # UPGRADE_SUMMARY.md structure
        'summary_title': 'Resumen de actualización',
        'summary_from': 'Desde',
        'summary_to': 'Hasta',
        'summary_date': 'Fecha',
        'summary_automated_changes': 'Cambios automatizados',
        'summary_manual_steps': 'Pasos manuales',
        'summary_failed_count': 'Fallas / requieren atención',
        'automated_changes_applied': 'Cambios automatizados aplicados',
        'failed_needs_attention': 'Fallas / requieren atención manual',
        'failed_section_body': 'Los siguientes cambios no se completaron automáticamente. El sitio **no** se actualizó a la nueva versión. Resuelve estas fallas (usualmente un problema pasajero de red) y ejecuta la actualización de nuevo.',
        'summary_flagged_count': 'Archivos sin instalar',
        'flagged_needs_attention': 'Archivos que no se instalaron',
        'flagged_section_body': 'Estos archivos no forman parte de la versión nueva de Telar, así que no se pudieron instalar. La actualización **sí** terminó y el sitio quedó en esa versión; volver a ejecutarla no cambia nada. Repórtalos para que se corrija esa versión de Telar.',
        'completed_with_warnings': 'Completados con advertencias',
        'warnings_section_body': 'Estos pasos no impidieron la actualización, pero conviene revisarlos:',
        'manual_steps_required': 'Pasos manuales necesarios',
        'complete_after_merge': 'Por favor completa estos pasos:',
        'no_manual_steps': 'No se requieren pasos manuales',
        'all_automated': '¡Todos los cambios han sido automatizados!',
        'resources': 'Recursos',
        'guide': 'guía',
        'full_documentation': 'Documentación completa',
        'changelog': 'CHANGELOG',
        'report_issues': 'Reportar problemas',

        # Category labels (for organizing changes in UPGRADE_SUMMARY.md)
        'category_configuration': 'Configuración',
        'category_layouts': 'Layouts',
        'category_includes': 'Includes',
        'category_styles': 'Estilos',
        'category_scripts': 'Scripts',
        'category_documentation': 'Documentación',
        'category_other': 'Otros',

        # File count suffix (for category headings)
        'file': 'archivo',
        'files': 'archivos',

        # Common messages used across migrations
        'created_directory': 'Directorio creado: {}',
        'moved_file': 'Movido {} → {}',
        'removed_file': 'Archivo eliminado: {}',
        'removed_directory': 'Directorio eliminado: {}',
        'updated_file': 'Se actualizó {}',
        'fetched_file': '{} actualizado: {}',
        'file_exists': '{} ya existe',
        'empty_directory_removed': 'Directorio vacío eliminado: {}',
        'could_not_remove': '⚠️  Advertencia: No se pudo eliminar {}: {}',

        # Safety messages (for preserved user content)
        'kept_modified_files': '⚠️  Se conservaron {} archivos de demostración modificados por el usuario',
        'kept_images_safety': 'ℹ️  Se conservaron {} imágenes de demostración antiguas por seguridad',
        'manual_delete_note': '(Puedes eliminarlas a mano si no las usas)',

        # Sobre record_fetch_failed y la frase que usa coerce_change para
        # clasificar, ver la nota en la seccion en ingles.
        'record_deps_missing': 'La regeneraci\u00f3n de datos necesita dependencias '
                               'que no est\u00e1n instaladas ({}). Sin ellas no se '
                               'puede regenerar nada, as\u00ed que el sitio qued\u00f3 '
                               'sin actualizar. Instala lo que est\u00e1 en '
                               'requirements.txt y vuelve a ejecutar la actualizaci\u00f3n.',
        'record_regeneration_failed': 'Fall\u00f3 la regeneraci\u00f3n de datos '
                                      '(csv_to_json / generate_collections). Ejecuta '
                                      'esos dos scripts a mano y despu\u00e9s vuelve '
                                      'a intentar la actualizaci\u00f3n.',
        'record_migration_aborted': 'La migraci\u00f3n {} \u2192 {} se interrumpi\u00f3: {}',
        'config_note_section_vs_value': '{} es una secci\u00f3n en este sitio y '
                                        'un solo valor en esta versi\u00f3n de '
                                        'Telar: qued\u00f3 como lo trae Telar',
        'config_note_unwritable_value': 'El valor de {} en este sitio no se '
                                        'pudo escribir en YAML: qued\u00f3 el '
                                        'de esta versi\u00f3n de Telar',
        'config_note_release_owns_list': '{} es una lista propia de Telar: la '
                                         'de este sitio no se llev\u00f3 al '
                                         'archivo nuevo',
        'config_note_unwritable_list_item': '{} tiene en este sitio un elemento '
                                            'que no se pudo escribir en YAML: '
                                            'qued\u00f3 la lista de esta '
                                            'versi\u00f3n de Telar',
        'config_note_kept_list_entries': 'Se conservaron en {} las entradas '
                                         'propias de este sitio: {}',
        'config_note_unwritable_not_carried': '{} no se pudo escribir en YAML, '
                                              'as\u00ed que no se llev\u00f3 al '
                                              'archivo nuevo',
        'config_note_carried_into': 'Se llev\u00f3 {} al archivo nuevo, dentro de {}',
        'manual_step_record_version': 'Escribe la versi\u00f3n en `_config.yml`. Este sitio no tiene una secci\u00f3n `telar:` donde escribirla: la actualizaci\u00f3n reescribe esa secci\u00f3n, pero no la crea, porque no sabe qu\u00e9 m\u00e1s guardas ah\u00ed. Agrega `telar:` al principio del archivo y, debajo, con sangr\u00eda, `version: "{}"` y `release_date: "{}"`. Lo dem\u00e1s ya qued\u00f3 hecho. Sin esas l\u00edneas, la pr\u00f3xima actualizaci\u00f3n no sabr\u00e1 en qu\u00e9 versi\u00f3n est\u00e1 este sitio y repetir\u00e1 todo el trabajo sobre contenido que ya est\u00e1 al d\u00eda.',
        'config_note_carried_top_level': 'Se llev\u00f3 {} al archivo nuevo: '
                                         'esta versi\u00f3n de Telar no lo trae',
        'stamp_date_unknown': 'La versi\u00f3n {} de Telar todav\u00eda no tiene '
                              'fecha de lanzamiento registrada, as\u00ed que la '
                              'actualizaci\u00f3n escribe la de hoy. Esto solo '
                              'pasa antes de que el lanzamiento tenga su '
                              'etiqueta de git.',
        'record_protected_unencryptable': (
            'Este sitio tiene historias marcadas como protegidas, y '
            '.github/workflows/build.yml no ejecuta '
            'scripts/encrypt_protected_stories.py. Por eso la '
            'construcci\u00f3n se detiene a prop\u00f3sito, en vez de '
            'publicar sin cifrar el texto de esas historias. La '
            'actualizaci\u00f3n ya termin\u00f3 y los archivos de datos '
            'est\u00e1n al d\u00eda: esto es lo \u00fanico que queda por '
            'hacer. Copia el build.yml actual del repositorio de Telar sobre '
            'el tuyo (\u00e1brelo en GitHub, usa \u00abCopy raw '
            'contents\u00bb, reemplaza el archivo completo y confirma el '
            'cambio). GitHub no permite que una actualizaci\u00f3n escriba '
            'archivos de workflow, y por eso este paso queda en tus manos; el '
            'Compositor de Telar s\u00ed los escribe, as\u00ed que un sitio '
            'actualizado con \u00e9l no tiene que hacer nada de esto. Y si '
            'esas historias no son privadas de verdad, la otra salida es '
            'quitarles la marca de protegidas.'),
        'record_fetch_failed': 'No se pudo descargar {} de GitHub (versi\u00f3n {} de '
                               'Telar). '
                               'Actualiza ese archivo a mano.',
        'record_fetch_absent': '{} no existe en la versi\u00f3n {} de Telar, as\u00ed '
                               'que no se pudo instalar. La actualizaci\u00f3n '
                               'sigui\u00f3 adelante sin ese archivo; por favor '
                               'rep\u00f3rtalo.',
        'record_write_rolled_back': 'No se pudo escribir un archivo del marco, as\u00ed '
                                    'que se deshicieron los cambios: {}',

        # Descripciones de cambios. Ver la nota en la seccion en ingles.
        'change_concurrency_by_hand': 'Grupo de concurrencia en .github/workflows/build.yml: '
                                      'agrega el bloque `concurrency` a ese archivo a mano (o '
                                      'vuelve a copiarlo completo). La actualización que se '
                                      'ejecuta dentro de GitHub Actions no puede modificar '
                                      'archivos de workflow; el Compositor de Telar lo aplica '
                                      'automáticamente. Revisa el paso manual que aparece más '
                                      'abajo.',
        'change_gitattributes_added': 'Se agregó {}: marca el paquete de historias como archivo '
                                      'generado',
        'change_gitattributes_skipped': 'Se omitió {} (ya existía): revisa el paso manual para '
                                        'juntar las marcas de archivo generado',
        'change_gitattributes_absent': '{} no se descargó de GitHub. No es grave: agrégalo a mano '
                                       'si quieres las marcas de archivo generado.',
        'change_chain_wiring_internal': 'Arreglo interno de la cadena de actualización: la '
                                        'migración de la v1.5.4 a la v1.6.0 quedó registrada en '
                                        'scripts/upgrade.py, así que una actualización que empieza '
                                        'desde una versión anterior a la v1.6.0 ya no se detiene en '
                                        'la v1.5.4. En este sitio no cambió ningún archivo.',
        'change_removed_dependabot': 'Se eliminó {}: los pull requests que suben versiones de '
                                     'dependencias ahora los maneja el proceso de lanzamiento de '
                                     'Telar, y no cada sitio por su cuenta',
        'change_could_not_remove_dependabot': 'No se pudo eliminar {}: {}. No es grave: bórralo a mano '
                                              'cuando puedas. Ya no hace nada, porque los pull requests '
                                              'que suben versiones de dependencias los maneja el proceso '
                                              'de lanzamiento de Telar y no cada sitio; las alertas de '
                                              'seguridad de GitHub no cambian.',
        'change_could_not_remove_superseded': 'No se pudo eliminar {}: {}. No es grave: bórralo a mano '
                                              'cuando puedas. Ya nada lo carga, porque los layouts y '
                                              'los scripts que instaló esta actualización usan los '
                                              'archivos que lo reemplazaron.',
        'change_could_not_fetch_config': 'No se pudo descargar _config.yml',
        'change_transformation_aborted': '{} se interrumpió: {}',
        'and_n_more': 'y {} más',
        'change_gitignore_paths': 'Se actualizaron las rutas de .gitignore (components/ → '
                                  'telar-content/)',
        'change_gitignore_section': 'Se actualizó .gitignore: sección {}',
        'change_removed_not_telar': 'Se eliminó {}: ya no forma parte de Telar',
        'change_could_not_remove': 'No se pudo eliminar {}: {}',
        'change_kept_uncheckable': 'Se conservó {}: no se pudo comprobar si lo habías editado',
        'change_kept_edited': 'Se conservó {}: tiene cambios hechos en este sitio',
        'change_removed_demo_term': 'Se eliminó {}: era un término del glosario de demostración '
                                    'que Telar ya no trae',
        'change_both_dirs_present': 'Las carpetas {}/ y {}/ están las dos en el sitio. No se '
                                    'tocó ninguna: júntalas a mano.',
        'change_moved_dir': 'Se movió {}/ → {}/',
        'change_kept_components': 'Se conservó components/: todavía tiene adentro {}',
        'change_removed_empty_components': 'Se eliminó la carpeta components/, que quedó vacía',
        'change_both_files_present': 'Los archivos {} y {} están los dos en el sitio. No se tocó '
                                     'ninguno: júntalos a mano.',
        'change_could_not_move': 'No se pudo mover {}',
        'change_moved_file': 'Se movió {} → {}',
        'change_removed_empty_pages': 'Se eliminó la carpeta pages/, que quedó vacía',
        'change_moved_images': 'Se sacaron {} imagen(es) de las subcarpetas objects/ y '
                               'additional/ a la carpeta que las contiene',
        'change_kept_different_image': 'Se conservó {}/{}/{}: {}/{} es otra imagen, y la que '
                                       'aparece en la hoja de cálculo es esta',
        'change_kept_both_taken': 'Se conservó {}/{}/{}: los nombres {} y {} ya están '
                                  'ocupados en {}/',
        'change_could_not_move_image': 'No se pudo mover {}/{}/{}: {}',
        'change_moved_renamed': 'Se movió {}/{}/{} → {}/{}, con otro nombre porque el '
                                'nombre {} ya estaba ocupado',
        'change_removed_empty_subdir': 'Se eliminó la carpeta {}/{}/, que quedó vacía',
        'change_rewrote_image_paths': 'Se actualizaron {} ruta(s) de imagen para que apunten a la '
                                      'carpeta donde quedaron',
        'change_renamed_column': 'La columna {} ahora se llama {} en {}',
        'change_added_columns': 'Columnas nuevas en {}: {}',
        'change_kept_no_stories': 'Se conservó {}: está en el formato viejo, de clave y '
                                  'valor, pero no nombra ninguna historia',
        'change_rewrote_stories_table': 'Se reescribió {} como una tabla de {} historia(s)',
        'change_kept_config_unreadable': 'Se dejó _config.yml como estaba: no se pudo leer como '
                                         'YAML, así que no hubo forma de pasar los ajustes sin '
                                         'arriesgar el archivo',
        'change_rewrote_config': 'Se reescribió _config.yml a partir del que trae esta '
                                 'versión de Telar, pero con los ajustes propios de este '
                                 'sitio',
        'change_nothing_to_remove': 'No hubo que eliminar {}: no estaba en el sitio',
        'change_removed_superseded': 'Se eliminó {}: lo reemplazan los archivos que instaló esta '
                                     'actualización',
        'change_removed_stale_bundle': 'Se eliminó {}, un archivo de paquete que quedó viejo',
        'change_no_stale_bundles': 'No había archivos de paquete viejos que eliminar',
        'change_removed_dead_file': 'Se eliminó {}, un archivo que ya no se usa',
        'change_no_dead_files': 'No había archivos sin uso que eliminar',
        'deps_installing': '  Instalando las dependencias que faltan, desde {}\u2026',
        'deps_no_manifest': '  \u26a0\ufe0f  Advertencia: no se pueden instalar las '
                            'dependencias que faltan ({}) porque no hay '
                            'requirements.txt junto al script de actualizaci\u00f3n '
                            'ni en el sitio.',
        'deps_pip_failed': '  \u26a0\ufe0f  Advertencia: fall\u00f3 pip install desde {}:\n{}',
        'deps_pip_timeout': '  \u26a0\ufe0f  Advertencia: pip install desde {} '
                            'super\u00f3 el tiempo l\u00edmite',

        'retired_migrations': 'Se elimin\u00f3 scripts/migrations/: este sitio usa '
                              'el lanzador de actualizaci\u00f3n, que descarga una '
                              'copia verificada de las migraciones cada vez que se '
                              'ejecuta.',
        'retire_migrations_warning': 'No se pudo eliminar scripts/migrations/: {}. '
                                     'La actualizaci\u00f3n se complet\u00f3; esa '
                                     'carpeta no se usa y puedes borrarla a mano.',

        # v1.8.0 migration records.
        'v180_removed_stale_manifest': 'Se eliminó migration.json, un archivo que dejó la '
            'actualización a la versión 1.5.4 y que Jekyll publicaba '
            'como una página más del sitio',
        'v180_page_line_updated': 'Se actualizó {}: el contenido predeterminado ahora viene de `{}`',
        'v180_page_line_current': '{} ya tiene la línea de la versión 1.8.0',
        'v180_page_line_own_text': '{} tiene un texto propio en lugar de la línea predeterminada, '
            'así que quedó como estaba. Si quieres el contenido '
            'predeterminado, la línea que debes usar ahora es `{}`',
        'v180_page_absent': 'Este sitio no tiene {}, así que no había nada que actualizar',
        'v180_column_dropped': 'Se eliminó la columna vacía `{}` de `{}`; tus valores están en '
            '`{}`.',
        'v180_column_dropped_all_empty': 'Se eliminó la columna vacía `{}` de `{}`: significa lo '
            'mismo que `{}`, las dos estaban vacías y se conservó '
            '`{}`.',
        'v180_columns_hold_values': '`{}` tiene columnas que significan lo mismo y cada una tiene '
            'valores: {}. Telar no puede escoger entre ellas, así que la '
            'próxima construcción se detendrá. Deja una, pasa a ella los '
            'valores que necesites y borra las demás.',
        'v180_column_in_sheet': 'El sitio toma el contenido de una hoja de cálculo de Google '
            'Sheets, y la próxima construcción vuelve a leerla. Borra la '
            'columna `{}` directamente en la hoja, en la pestaña de la que '
            'sale `{}`; si no, la construcción se detendrá por las mismas dos '
            'columnas.',
        'v180_column_not_removed': 'No se pudo eliminar la columna vacía `{}` de `{}` sin '
            'cambiar nada más en el archivo, así que no se tocó. Bórrala a mano; si no, la '
            'próxima construcción se detendrá.',
        'v180_column_marked_note': 'La columna vacía `{}` de `{}` ahora se llama `{}`, así que '
            'la construcción la ignora. Eliminarla habría cambiado qué '
            'filas lee la construcción en ese archivo.',
        'v180_column_marked_in_sheet': 'El sitio toma el contenido de una hoja de cálculo de '
            'Google Sheets, y la próxima construcción vuelve a '
            'leerla. Cámbiale el nombre a la columna `{}` '
            'directamente en la hoja, en la pestaña de la que sale '
            '`{}`, para que se llame `{}`; si no, la construcción se '
            'detendrá por las mismas dos columnas.',
        'v180_column_kept_for_header_row': 'No se pudo eliminar la columna vacía `{}` de `{}`: '
            'sin ella, la construcción dejaría de reconocer la '
            'segunda fila de nombres de las columnas, la que está'
            ' en el otro idioma, y la publicaría como contenido. '
            'Borra a mano esa columna y esa fila; mientras la '
            'columna siga ahí, la próxima construcción se '
            'detendrá.',
        'v180_reserved_column': '`{}` tiene una columna llamada `{}`, un nombre que Telar reserva '
            'para su propio uso. Cámbiale el nombre a esa columna; si no, la '
            'próxima construcción se detendrá.',
        'v180_sheet_unreadable': 'No se pudo leer `{}` para revisar las columnas: {}',
        'v180_sheets_unchecked': 'No se pudo comprobar si alguna hoja de cálculo tiene dos '
            'columnas que significan lo mismo: la actualización no logró '
            'cargar las reglas que la construcción aplica a las columnas '
            '({}). Si las hay, la próxima construcción se detendrá y dirá '
            'cuáles son.',
        'v180_sheets_clean': 'Ninguna hoja de cálculo tiene dos columnas que signifiquen lo mismo',
        'v180_exclude_added': 'Se agregaron a la lista `exclude:` de _config.yml estas entradas: '
            '{}. Así Jekyll no las publica como páginas del sitio',
        'v180_exclude_present': '_config.yml ya excluye {}',
        'v180_exclude_texts_failed': 'Esta actualización no pudo agregar `telar-content/texts/` a '
            'la lista `exclude:` de _config.yml: `exclude:` tiene un solo'
            ' valor o un conjunto de claves y valores en vez de una '
            'lista, o no se pudo leer el archivo. Convierte `exclude:` a '
            'mano en una lista que incluya `- telar-content/texts/` y '
            'vuelve a ejecutar la actualización. Sin esa entrada, Jekyll '
            'publica una copia sin procesar de los archivos de cada '
            'página, historia y entrada del glosario, y si una página '
            'fija su propia dirección, la construcción se detiene.',
        'v180_exclude_others_failed': 'Esta actualización no pudo agregar {} a la lista `exclude:`'
            ' de _config.yml. Agrega esas entradas a mano debajo de '
            '`exclude:`: corresponden a las pruebas propias de Telar, y '
            'sin ellas Jekyll publica esas pruebas junto con el sitio.',
        'v180_page_keys_removed': 'Se quitó {} de {}: la construcción asigna por su cuenta el '
            'layout y la dirección de cada página',
        'v180_page_key_kept': '{} define `{}: {}`, un valor que la construcción ignora. La página '
            'se publica en {}.',
        'v180_page_source_refused': 'Se dejó {} como estaba: quitar {} habría cambiado la manera '
            'en que se lee el resto del frontmatter. La construcción '
            'ignora las dos claves, así que la página se publica bien de '
            'todos modos.',
        'v180_file_unreadable': 'No se pudo actualizar {}: {}',
        'v180_pages_clean': 'Ningún archivo de página define su propio layout ni su propia '
            'dirección',
        'v180_related_terms_listed': 'Se reescribió `related_terms` en {} como una lista, para que'
            ' la página enlace cada término relacionado',
        'v180_related_terms_refused': 'Se dejó `related_terms` en {} como estaba, porque está '
            'escrito de una forma que esta actualización no sabe '
            'reescribir. Escríbelo como una lista, por ejemplo '
            '`related_terms: ["term-one", "term-two"]`; si no, la página'
            ' no enlazará esos términos.',
        'v180_glossary_clean': 'No hubo que reescribir `related_terms` en ninguna entrada del '
            'glosario',
        'v180_answer_over_limit': 'Historia `{}`, paso {}: la respuesta tiene {} palabras y la '
            'construcción la recorta a {}. Acórtala para que no se pierda el'
            ' final.',
        'v180_answer_content_removed': 'Historia `{}`, paso {}: la respuesta solo muestra texto, '
            'así que la construcción le quita {}. Si quieres conservar '
            'ese contenido, pásalo a un panel.',
        'v180_answer_kind_media': 'las imágenes y los elementos multimedia',
        'v180_answer_kind_widgets': 'los widgets',
        'v180_answer_kind_footnotes': 'las notas al pie',
        'v180_answer_kind_markup': 'el formato de las listas, los títulos y las citas, además de '
            'las tablas, los bloques de código y las líneas divisorias',
        'v180_answers_from_local_copies': 'Las respuestas se revisaron en las copias locales de '
            'las hojas de cálculo. El sitio toma el contenido de una'
            ' hoja de cálculo de Google Sheets, y la próxima '
            'construcción vuelve a leerla, así que haz los cambios '
            'directamente en esa hoja.',
        'v180_answers_unchecked': 'No se pudieron revisar las respuestas de las historias: la '
            'actualización no logró cargar las reglas que la construcción '
            'aplica a las respuestas ({}). La próxima construcción indicará '
            'cada respuesta que recorte.',
        'v180_answers_clean': 'La construcción no recorta ninguna respuesta de las historias ni '
            'les quita contenido',
        'v180_engine_removed': 'Se eliminó {}: la actualización se ejecuta con las herramientas '
            'verificadas que descarga `scripts/upgrade.py`',
        'v180_engine_kept': 'Se conservó {}: no es una copia publicada por Telar, así que '
            'puede ser tuya. La actualización no lo usa; bórralo si nada tuyo depende de él.',
        'v180_engine_not_removed': 'No se pudo eliminar {}: {}. La actualización se completó; ese '
            'archivo no se usa y puedes borrarlo a mano.',
    }
}


def get_message(lang: str, key: str, *args) -> str:
    """
    Get translated message with optional formatting.

    Args:
        lang: Language code ('en' or 'es')
        key: Message key from MESSAGES dict
        *args: Optional format arguments

    Returns:
        Formatted message string in requested language

    Example:
        >>> get_message('en', 'current_version', '0.5.0-beta')
        'Current version: 0.5.0-beta'

        >>> get_message('es', 'current_version', '0.5.0-beta')
        'Versión actual: 0.5.0-beta'
    """
    # Normalize language code
    lang = lang if lang in MESSAGES else 'en'

    # Get message, fallback to English if key not found
    msg = MESSAGES[lang].get(key, MESSAGES['en'].get(key, key))

    # Format if arguments provided
    if args:
        try:
            return msg.format(*args)
        except (IndexError, KeyError):
            # Format failed, return unformatted
            return msg

    return msg


def get_file_count_suffix(lang: str, count: int) -> str:
    """
    Get correct file/files suffix for count.

    Args:
        lang: Language code ('en' or 'es')
        count: Number of files

    Returns:
        'file' or 'files' in appropriate language

    Example:
        >>> get_file_count_suffix('en', 1)
        'file'
        >>> get_file_count_suffix('en', 2)
        'files'
        >>> get_file_count_suffix('es', 1)
        'archivo'
        >>> get_file_count_suffix('es', 2)
        'archivos'
    """
    lang = lang if lang in MESSAGES else 'en'

    if count == 1:
        return MESSAGES[lang]['file']
    else:
        return MESSAGES[lang]['files']
