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

A server systemd timer collects public timeline samples at 09:00 Asia/Tehran. No X credentials, cookies, Mac, Codex or Chrome session are needed. Public embeds provide bounded samples, may be unavailable and do not expose reliable view counts. Publishing is manual. The score is a research coverage heuristic, not a calibrated forecast. Human factual review and X's final weighted-length validation remain necessary.

Public GitHub Pages publishing is disabled in this private fork. Do not follow upstream instructions to upload private data.json files.

## Server runtime

The host's system Python 3.6 supports the small public HTTP fetcher. The analysis pipeline uses isolated Python 3.12 without changing system packages:

```sh
docker run --rm --network none -v /opt/insight/twitter:/app -w /app python:3.12-slim python pipeline/run_day.py --profile o2co prepare 2026-10-26
```

The manual importer needs no network; the scheduled collector fetches public embeds and calls the configured AI service. The profile directories must retain their setgid permissions after uploads.

## Daily English research

The server fetches public embeds with `pipeline/fetch_public.py`; `pipeline/server_daily.py` generates four source-linked English drafts per profile and uses the same validated importer as `pipeline/daily_snapshot.py --profile SLUG INPUT.json`. It has no X publishing path. All drafts require `approval_status: pending`; English-only text, matching source accounts, freshness, observed metrics and attribution are checked before any write. Unknown metrics remain null. Dated snapshots live under `profiles/<slug>/history/` and the latest snapshot is published atomically under `daily_research`. Failed imports preserve last-good data; the UI marks research older than 36 hours overdue. Existing full keyword analytics remain separate.

Run `tests/server_daily.py`, `tests/daily_snapshot.py` and `tests/renderer.cjs` for source filtering, safe imports and rendering checks.

Install `deploy/insight-twitter-daily.{service,timer}` in `/etc/systemd/system/`. Create `/opt/insight/twitter/.env.server` mode 0600 with only `INSIGHT_AI_URL`, `INSIGHT_AI_KEY` and `INSIGHT_AI_MODEL`. Use an existing authorized provider. Run `systemctl daemon-reload`, test `systemctl start insight-twitter-daily.service`, then enable `systemctl enable --now insight-twitter-daily.timer`. Persistent timers catch missed runs after reboot. Inspect `journalctl -u insight-twitter-daily.service -n 100` and each profile's private `server-status.json` on failures. Successful profiles skip repeat runs on the same Tehran date; failed profiles can retry independently.

The host fetcher and isolated analysis runtime are separate because the public endpoint responds differently to these HTTP runtimes. Captures older than twenty minutes are rejected. Requests and the whole service have bounded timeouts. Code is read-only, private profile data is writable, and memory is limited. Public endpoint coverage and availability are not guaranteed; use an official read-only X API if complete reliable coverage becomes necessary. Retire the local heartbeat only after server verification.

Daily drafts must come from AI analysis of the freshly collected source posts. No template or editorial fallback is permitted. Provider failures retain the previous snapshot and record a failed server status. A same-day result is reusable only if its generation method is AI, so an older template result is automatically replaced after successful AI recovery. The dedicated job environment can point at the existing server AI router without modifying shared application settings.

Source HTTP rate limits are retried once with a bounded delay (respecting a numeric Retry-After up to ninety seconds). Final failures remain explicit unavailable-source statuses. Model identity is retained in each AI snapshot. Drafts naming configured source-company handles are rejected; the generation instruction requires independent insights for the author brand rather than source advertisements.
