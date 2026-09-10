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

Version: v1.7.0
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
        'migration_stopped': '✗ Stopping: this migration did not complete. '
                             'The site is left unchanged.',
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
        'upgrade_not_applied': '  The site was NOT upgraded and its version was left unchanged.',
        'transient_retry': '  This is usually a transient network problem — run the upgrade again.',
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
        'record_fetch_failed': 'Could not fetch {} from GitHub ({}). '
                               'Update it by hand \u2014 {}',
        'record_write_rolled_back': 'A framework file could not be written, so the '
                                    'changes were rolled back: {}',
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
                             'migración no se completó. El sitio queda sin '
                             'cambios.',
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
        'upgrade_not_applied': '  El sitio no se actualizó y su versión quedó sin cambios.',
        'transient_retry': '  Suele ser un problema temporal de red; vuelve a ejecutar la actualización.',
        'see_summary_failures': '  Revisa UPGRADE_SUMMARY.md para ver la lista de fallas.',
        'upgrade_failed_data': '✗ La actualización no se completó: falló la regeneración de los datos.',
        'see_summary_details': '  Revisa UPGRADE_SUMMARY.md para más detalles.',
        'data_files_regenerated': '✓ Archivos de datos regenerados',
        'chain_stops': '⚠️  La cadena de migraciones se detiene en {}: ninguna migración registrada continúa desde ahí hacia {}.',
        'chain_stops_note': '    Esto suele significar que la versión actual no es compatible o que falta una migración en la cadena; revísalo manualmente antes de continuar.',

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
        'category_other': 'Otro',

        # File count suffix (for category headings)
        'file': 'archivo',
        'files': 'archivos',

        # Common messages used across migrations
        'created_directory': 'Directorio creado: {}',
        'moved_file': 'Movido {} → {}',
        'removed_file': 'Archivo eliminado: {}',
        'removed_directory': 'Directorio eliminado: {}',
        'updated_file': '{} actualizado',
        'fetched_file': '{} actualizado: {}',
        'file_exists': '{} ya existe',
        'empty_directory_removed': 'Directorio vacío eliminado: {}',
        'could_not_remove': '⚠️  Advertencia: No se pudo eliminar {}: {}',

        # Safety messages (for preserved user content)
        'kept_modified_files': '⚠️  Se conservaron {} archivos de demostración modificados por el usuario',
        'kept_images_safety': 'ℹ️  Se conservaron {} imágenes de demostración antiguas por seguridad',
        'manual_delete_note': '(Puedes eliminarlas manualmente si no las usas)',

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
        'record_fetch_failed': 'No se pudo descargar {} de GitHub ({}). '
                               'Actual\u00edzalo a mano \u2014 {}',
        'record_write_rolled_back': 'No se pudo escribir un archivo del marco, as\u00ed '
                                    'que se deshicieron los cambios: {}',
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
