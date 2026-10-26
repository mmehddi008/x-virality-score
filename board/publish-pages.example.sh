#!/usr/bin/env bash
set -euo pipefail
printf "%s\n" "Public Pages publishing is disabled: deploy behind authenticated Trackpanel routes. See docs/trackpanel.md." >&2
exit 1
