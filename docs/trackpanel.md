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

## Per-project model settings

Trackpanel administrators can read and save a model ID at `/twitter/<profile>/ai-settings` (GET/PUT). Writes require a same-origin request and accept only the model field; credentials and provider endpoints are not exposed. Mount `/opt/insight/twitter/settings:/twitter/settings` writable only for the panel user (directory 0750, files 0640; owner/group 10001), while profiles stay read-only in the panel. The isolated runner needs supplementary group 10001 to read panel-owned settings with all capabilities dropped. Seed `settings/<profile>.json` with matching `profile_id` and the existing model. Python reads the same directory on every run (`XVS_SETTINGS_ROOT` overrides it); missing settings retain the configured environment default. Corrupt or mismatched settings fail closed.

The board distinguishes the saved model, latest attempt status and last successful model. Saving affects the next daily run, not the snapshot currently displayed; no run or publication is triggered by Save. Same-day reuse requires the saved model to match the successful model. A model ID can be syntactically valid but unavailable upstream; only a successful run establishes availability. Atomic settings writes prevent partial reads; simultaneous administrator saves use last-write-wins.

## Research dashboard and editable sources

The private workspace has Overview, Research, Drafts, Sources & controls, and AI & strategy tabs. Summary counts and activity bars describe the latest collected sample, never predicted reach or fabricated virality. Unknown engagement stays unknown; drafts stay pending.

Administrators can save one to twenty unique X handles, one to eight drafts per run, and a one-to-seven-day window through `/twitter/<profile>/research-settings`. Sources and controls share the private settings file with the model. Both save routes serialize updates and preserve each other's fields. Host collection, model generation and the validated snapshot importer use the same effective configuration. A configuration fingerprint prevents same-day reuse after a setting changes. Saves affect the next run; they neither follow accounts nor publish content. If settings change during generation, final import validates against current settings and can reject the old configuration, preserving last-good research.

### Shared AI connection
Trackpanel `/settings/ai` manages the OpenAI-compatible base URL and write-only API key, shared by both research profiles. Admin-only `/api/ai/connection` stores `settings/shared-ai.json` (0640, panel UID/group 10001); the daily container requires group 10001. Never commit this file. Empty key preserves the saved key only when the endpoint is unchanged. `/api/ai/connection/test` performs a bounded request without following redirects or returning provider error text. Other Trackpanel modules retain their existing connections; this migration does not reconfigure their automation.

The runner reads the shared connection on every generation request; environment credentials are a migration fallback only when the file is absent. Corrupt saved configuration fails closed. The connection revision participates in the same-day skip check. Model overrides remain per profile, and all generated drafts stay pending approval.

Run now uses the project's saved model and research settings, forcing a fresh server collection. The host `insight-twitter-manual.timer` checks private requests every fifteen seconds. Scheduled and manual jobs share `deploy/run-research.sh` and a host lock; requests cannot overlap generation. GET/POST `/twitter/{profile}/run` are admin-only and POST requires same origin. Completion links refresh the dashboard; failures retain the last good research. No X write capability is added.
