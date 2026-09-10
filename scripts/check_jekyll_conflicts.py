#!/usr/bin/env python3
"""
Fail the build when Jekyll reported a destination conflict.

Reads a saved `jekyll build` log and exits 1 if any conflict appears.
Jekyll reports these as warnings and exits 0; see telar/build_conflicts.py
for why that is not survivable for a site with protected stories.

Usage: python3 scripts/check_jekyll_conflicts.py <build-log>

Version: v1.7.0
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from telar.build_conflicts import (  # noqa: E402
    find_conflicts,
    format_failure,
    is_complete_build_log,
)


def main():
    parser = argparse.ArgumentParser(
        description='Fail the build on a Jekyll destination conflict.'
    )
    parser.add_argument('log', help='File holding the jekyll build output')
    args = parser.parse_args()

    log = Path(args.log)
    if not log.exists():
        print(f"❌ {log}: build log not found — the Jekyll step must save its "
              "output for this gate to read.")
        raise SystemExit(1)

    output = log.read_text(encoding='utf-8', errors='replace')

    # Silence is not success. If this log is not a finished build at the
    # default log level, no conflict would have been printed whether or not
    # one occurred, and passing here would be a guess dressed as a gate.
    if not is_complete_build_log(output):
        print(f"❌ {log}: this is not a completed Jekyll build log, so it "
              "cannot show whether destinations collided. The build must run "
              "at the default log level and save all of its output "
              "(JEKYLL_LOG_LEVEL=error suppresses the warning this gate "
              "reads).")
        raise SystemExit(1)

    conflicts = find_conflicts(output)
    if not conflicts:
        print("✓ No destination conflicts in the Jekyll build.")
        return

    message = format_failure(conflicts)
    print(f"\n❌ {message}")
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        annotation = message.replace('%', '%25').replace('\r', '%0D')
        annotation = annotation.replace('\n', '%0A')
        print(f"::error title=Jekyll destination conflict::{annotation}")
    raise SystemExit(1)


if __name__ == '__main__':
    main()
