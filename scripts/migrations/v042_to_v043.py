"""
Migration from Telar v0.4.2-beta to v0.4.3-beta

Changes:
- Updates generate_iiif.py with EXIF orientation handling
- Updates story.js with iPad touch scrolling support
- Updates build.yml with IIIF config change detection
- No configuration file changes needed
"""

from pathlib import Path
from typing import List, Dict
try:
    import requests
except ImportError:
    requests = None

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
        if requests is None:
            results['errors'].append("requests library not installed. Run: pip install requests")
            raise ImportError("requests library required for migration")

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

    def get_manual_steps(self) -> List[Dict[str, str]]:
        """
        Manual steps for users to complete after migration.

        v0.4.3 updates build.yml workflow which requires manual update since
        GitHub Actions workflows only take effect when committed to the repository.

        Returns:
            list: Manual steps as dicts with 'description' key
        """
        return [
            {
                'description': 'Update your GitHub Actions build workflow file: This update adds smart detection so IIIF tiles automatically regenerate when you change _config.yml settings. Without this update, you would need to manually regenerate tiles after config changes. (1) Open this link in a new tab: https://raw.githubusercontent.com/UCSB-AMPLab/telar/main/.github/workflows/build.yml (2) Select all the text (Ctrl+A on Windows/Linux, Cmd+A on Mac) and copy it (Ctrl+C or Cmd+C) (3) Go to your GitHub repository and click on the .github/workflows/build.yml file (4) Click the pencil (Edit) icon in the top-right corner (5) Select all the existing content in the editor and delete it (6) Paste the new content you copied in step 2 (7) Scroll to the bottom and click the green "Commit changes" button to save. Note: GitHub Actions workflow files only take effect once they are committed to your repository, which is why this manual step is necessary.',
                'doc_url': 'https://raw.githubusercontent.com/UCSB-AMPLab/telar/main/.github/workflows/build.yml'
            },
        ]
