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

Version: v1.5.0
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
        'automated_changes_applied': 'Automated Changes Applied',
        'manual_steps_required': 'Manual Steps Required',
        'complete_after_merge': 'Please complete these steps:',
        'no_manual_steps': 'No Manual Steps Required',
        'all_automated': 'All changes have been automated!',
        'resources': 'Resources',
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
        'fetch_warning': '⚠️  Warning: Could not fetch {} from GitHub',
        'file_exists': '{} already exists',
        'empty_directory_removed': 'Removed empty directory: {}',
        'could_not_remove': '⚠️  Warning: Could not remove {}: {}',

        # Safety messages (for preserved user content)
        'kept_modified_files': '⚠️  Kept {} user-modified demo files',
        'kept_images_safety': 'ℹ️  Kept {} old demo images for safety',
        'manual_delete_note': '(You can manually delete these if not using them)',
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
        'automated_changes_applied': 'Cambios automatizados aplicados',
        'manual_steps_required': 'Pasos manuales necesarios',
        'complete_after_merge': 'Por favor completa estos pasos:',
        'no_manual_steps': 'No se requieren pasos manuales',
        'all_automated': '¡Todos los cambios han sido automatizados!',
        'resources': 'Recursos',
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
        'fetch_warning': '⚠️  Advertencia: No se pudo obtener {} de GitHub',
        'file_exists': '{} ya existe',
        'empty_directory_removed': 'Directorio vacío eliminado: {}',
        'could_not_remove': '⚠️  Advertencia: No se pudo eliminar {}: {}',

        # Safety messages (for preserved user content)
        'kept_modified_files': '⚠️  Se conservaron {} archivos de demostración modificados por el usuario',
        'kept_images_safety': 'ℹ️  Se conservaron {} imágenes de demostración antiguas por seguridad',
        'manual_delete_note': '(Puedes eliminarlas manualmente si no las usas)',
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
