#!/bin/bash
# Hourly timers call this; schedule.py decides which profiles are due (hours set in the panel).
# "hunt <slug>" or "<slug>" is a manual run from the panel queue and skips the schedule.
set -euo pipefail
exec 9>/opt/insight/twitter/research.lock
flock -w 1200 9
profiles=(o2co bitoff)
force=()
container=insight-twitter-daily
docker_args=(--network insight_insight-net --group-add 10001 --read-only --tmpfs /tmp:rw,nosuid,noexec,size=32m --cap-drop ALL --security-opt no-new-privileges --memory 256m --cpus 1 --env-file /opt/insight/twitter/.env.server -v /opt/insight/twitter:/app:ro -v /opt/insight/twitter/profiles:/app/profiles:rw -w /app)
due() { python3 -B /opt/insight/twitter/pipeline/schedule.py "$1" "$2"; }
if [ "${1:-}" = hunt ]; then
  manual=
  if [ -n "${2:-}" ]; then
    case "$2" in o2co|bitoff) profiles=("$2"); manual=1;; *) exit 2;; esac
  fi
  # A failed profile does not stop the others.
  status=0
  for p in "${profiles[@]}"; do
    [ -n "$manual" ] || due hunt "$p" || continue
    docker run --rm --name "insight-twitter-hunt-$p" "${docker_args[@]}" python:3.12-slim python -B pipeline/hunt.py "$p" || status=1
  done
  exit $status
fi
if [ "$#" -gt 0 ]; then
  case "$1" in o2co|bitoff) profiles=("$1"); force=(--force); container="insight-twitter-manual-$1";; *) exit 2;; esac
else
  scheduled=()
  for p in "${profiles[@]}"; do due research "$p" && scheduled+=("$p"); done
  [ "${#scheduled[@]}" -gt 0 ] || exit 0
  profiles=("${scheduled[@]}")
fi
python3 -B /opt/insight/twitter/pipeline/fetch_public.py /opt/insight/twitter/profiles /opt/insight/twitter/public-timelines.json "${profiles[@]}"
trap 'docker rm -f "$container" >/dev/null 2>&1 || true' EXIT
docker run --rm --name "$container" "${docker_args[@]}" -e XVS_TIMELINES_FILE=/app/public-timelines.json python:3.12-slim python -B pipeline/server_daily.py "${force[@]}" "${profiles[@]}"
