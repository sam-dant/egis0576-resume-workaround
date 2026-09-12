#!/bin/bash
# SPDX-License-Identifier: MIT
set -euo pipefail
BASE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec python3 "$BASE/lib/manage.py" uninstall "$@"
