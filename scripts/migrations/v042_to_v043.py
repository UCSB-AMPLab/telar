"""
Migration from Telar v0.4.2-beta to v0.4.3-beta

Changes:
- Updates generate_iiif.py with EXIF orientation handling
- Updates story.js with iPad touch scrolling support
- Updates build.yml with IIIF config change detection
- No configuration file changes needed
"""

from pathlib import Path
import requests

class Migration042to043:
    """Migrate from v0.4.2-beta to v0.4.3-beta"""

    from_version = "0.4.2-beta"
    to_version = "0.4.3-beta"

    def __init__(self, repo_path: Path):
        self.repo_path = Path(repo_path)

    def check_applicable(self) -> bool:
        """Check if this migration should be applied"""
        config_path = self.repo_path / '_config.yml'
        if not config_path.exists():
            return False

        with open(config_path, 'r') as f:
            content = f.read()
            return 'version: "0.4.2-beta"' in content

    def apply(self) -> dict:
        """
        Apply migration from v0.4.2-beta to v0.4.3-beta

        Returns:
            dict: Migration results with status and messages
        """
        results = {
            'success': True,
            'changes': [],
            'warnings': [],
            'errors': []
        }

        try:
            # Update framework files with v0.4.3 code
            self._update_framework_files(results)

            results['changes'].append("✓ Updated framework files with v0.4.3 improvements")
            results['changes'].append("  - EXIF orientation handling in IIIF generation")
            results['changes'].append("  - iPad touch scrolling for stories")
            results['changes'].append("  - IIIF regeneration on config changes")

        except Exception as e:
            results['success'] = False
            results['errors'].append(f"Migration failed: {str(e)}")

        return results

    def _update_framework_files(self, results: dict):
        """Download and update framework files from GitHub"""
        base_url = "https://raw.githubusercontent.com/UCSB-AMPLab/telar/v0.4.3-beta"

        files_to_update = [
            'scripts/generate_iiif.py',
            'assets/js/story.js',
            '.github/workflows/build.yml'
        ]

        for file_path in files_to_update:
            try:
                url = f"{base_url}/{file_path}"
                response = requests.get(url, timeout=30)
                response.raise_for_status()

                target_path = self.repo_path / file_path
                target_path.parent.mkdir(parents=True, exist_ok=True)

                with open(target_path, 'w', encoding='utf-8') as f:
                    f.write(response.text)

                results['changes'].append(f"  Updated: {file_path}")

            except Exception as e:
                results['warnings'].append(f"Could not update {file_path}: {str(e)}")

    def get_manual_steps(self) -> list:
        """
        Return list of manual steps user needs to complete

        Returns:
            list: Manual steps (empty for this migration)
        """
        return [
            "After upgrade completes:",
            "1. Regenerate IIIF tiles to apply EXIF orientation fix:",
            "   - If using GitHub Pages: Push this commit to trigger rebuild",
            "   - If testing locally: Run `python3 scripts/generate_iiif.py`",
            "2. Portrait photos from phones/cameras will now display correctly",
            "3. iPad users can now navigate stories with swipe gestures"
        ]
