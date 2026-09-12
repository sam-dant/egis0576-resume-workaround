#!/bin/bash
# SPDX-License-Identifier: MIT
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
files=(install.sh uninstall.sh scripts/check.sh scripts/diagnose.sh scripts/egis0576-fprintd-wait systemd/system-sleep/50-egis0576-fp-resume.sh)
for file in "${files[@]}"; do bash -n "$file"; done
if command -v shellcheck >/dev/null 2>&1; then
    shellcheck "${files[@]}"
else
    printf '%s\n' 'SKIP: shellcheck is unavailable; bash syntax and behavioral tests still run.'
fi
python3 -m unittest discover -s tests -v
