# Private profiles

Use Python 3.10+ and Node for checks. No added third-party dependency.

Each `profiles/<slug>/` contains `config.json`, `data.json`, `ledger.json` and `digests/`. Both config and data must declare the matching `profile_id`. Copy the existing example config/data, set the identity/date, and supply genuine collected data. Private profiles are ignored by Git; never commit credentials, drafts or browser sessions.

```sh
python3 pipeline/run_day.py --profile example prepare 2026-10-26
# Complete the generated search requests and review draft/radar JSON inputs.
python3 pipeline/run_day.py --profile example 2026-10-26
python3 tests/smoke.py
python3 tests/profiles.py
node tests/renderer.cjs
```

The board date must match the run. `--skip-drafts` produces a partial result, not a completed daily run. Board publication is atomic and cooperating daily/leaderboard writers share a profile lock; auxiliary digest files are not one multi-file transaction. Direct individual pipeline commands are maintenance tools: do not run them concurrently with a daily run.

Trackpanel serves `/twitter`, `/twitter/<slug>/` and authenticated JSON through its existing admin session. Profiles are directory-isolated but share the panel's admin audience; this is not multi-tenant access control. The read-only mount is `/opt/insight/twitter/profiles:/twitter/profiles:ro`; `INSIGHT_TWITTER_DIR` overrides the container path for tests/custom installs. Keep server directories root:10001 mode 2750 and files 0640 so atomic replacements inherit the panel-readable group.

A daily Codex heartbeat collects through the authorized local Chrome session at 09:00 Asia/Tehran. No server X credentials are stored. The Mac, Codex and logged-in Chrome must be available. Browser observations are dated samples, not exhaustive search results. Publishing is manual. The score is a research coverage heuristic, not a calibrated forecast. Draft checks are syntactic; human factual review and X's final weighted-length validation remain necessary.

Public GitHub Pages publishing is disabled in this private fork. Do not follow upstream instructions to upload private data.json files.

## Server runtime

The host's system Python 3.6 is too old. Use the isolated Python 3.12 runtime without changing system packages:

```sh
docker run --rm --network none -v /opt/insight/twitter:/app -w /app python:3.12-slim python pipeline/run_day.py --profile o2co prepare 2026-10-26
```

The pipeline needs no network: collection happens separately. For tests use a read-only mount and `python tests/smoke.py`. The profile directories must retain their setgid permissions after uploads.

## Daily English research

The heartbeat reads source posts through browser UI, generates four source-linked English drafts per profile, and imports one JSON snapshot using `pipeline/daily_snapshot.py --profile SLUG INPUT.json`. It has no X publishing path. All drafts require `approval_status: pending`; English-only text, matching source accounts, freshness, observed metrics and attribution are checked before any write. Unknown metrics remain null. Dated snapshots live under `profiles/<slug>/history/` and the board's latest snapshot is published atomically under `daily_research`. Failed or stale imports preserve the last-good board; the UI marks research older than 36 hours overdue. Existing full keyword analytics remain separate and are not falsely marked complete by a sampled daily update.

See `tests/daily_snapshot.py` for the input contract and run it alongside `tests/renderer.cjs`. The first run was executed end-to-end; the next scheduled trigger remains an unattended-runtime check, not a tested guarantee of browser availability.
