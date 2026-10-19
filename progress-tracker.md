# Progress Tracker

Update this file after every meaningful implementation change. Record only work that has actually been completed and reported; do not mark code as implemented merely because a prompt or plan exists.

## Current Phase

- **Phase 0 complete: requirements and architecture audit.**
- **Phase 1 complete: enforce manual-only behavior.** All email delivery pathways disabled.

## Current Goal

- Prevent the application from delivering email or LinkedIn messages through any UI action, REST/API endpoint, background job, scheduler, provider integration, direct SMTP route, MCP tool, webhook, or retry handler.
- Preserve the existing database and useful contact/template/sequence functionality while preparing the foundation for stored drafts and a manual outreach queue.

## Completed

- Defined the target as a manual outreach workspace, not an automated cold-email platform.
- Received an architecture audit identifying the existing FastAPI, React/Vite, SQLAlchemy/PostgreSQL, APScheduler, authentication, contact, sequence, queue, and sender components.
- Identified key existing areas to inspect during implementation, including `app/main.py`, `app/jobs.py`, `app/sender.py`, `app/queue_logic.py`, `app/routers/schedule.py`, `app/routers/campaigns.py`, `app/models.py`, and frontend campaign/lead pages. These paths came from the audit and must be confirmed against the checked-out code before editing.
- Established the hard requirement that marking a message sent must only change local application state; it must never call a delivery provider.
- Established the preference to retain the current stack and avoid destructive database cleanup during early phases.
- **Phase 1 implementation complete: manual-only enforcement active.** All email delivery pathways disabled:
  - **APScheduler job removed**: `run_slot_scan_job` (the per-minute slot scanner that dispatched `send_slot_job` tasks) removed from `app/main.py` lifespan. Maintenance jobs (unibox sync, Office365 webhook renewal, telemetry heartbeat, backup schedule) remain active.
  - **Queue slot creation blocked**: `reserve_slots_for_new_leads_bulk` in `app/queue_logic.py` returns early when `settings.manual_mode` is true. This covers lead enrollment via bulk add, CSV import, and background email verification.
  - **Global recalculation blocked**: `recalculate_all_campaigns` in `app/routers/schedule.py` clears the queue only and returns without creating new slots when `settings.manual_mode` is true. All callers (campaign/lead/inbox patches, inbox changes, manual recalc endpoint) now respect this guard.
  - **Test-send endpoints disabled**: Three endpoints now return 403 in manual mode:
    - `POST /api/campaigns/{campaign_id}/send-test` (`app/routers/campaigns.py`)
    - `POST /api/inboxes/{inbox_id}/send-test` (`app/routers/smtp.py`)
    - `POST /api/unibox/send` (`app/routers/unibox.py`)
  - **New `manual_mode` setting**: Added `QUICKLY_MANUAL_MODE` environment variable and `settings.manual_mode` in `app/settings_manager.py`, persisted in database, defaults to `false`.

## In Progress

- No implementation change is currently in progress. Phase 1 is complete.

## Next Up

1. Proceed to authentication review (Phase 2): inspect email/password login flow, extend if needed, ensure first-admin creation works without external email delivery.
2. Project/group and CSV improvements (Phase 3): evaluate if `Campaign` model can serve as project container, design contact groups/lists.
3. Templates and mixed-channel sequences (Phase 4): adapt sequence editor for manual draft generation, add LinkedIn DM channel.
4. Manual draft queue (Phase 5): implement stored drafts with due-time eligibility, manual sent-status action, next-step due calculation.
5. UI updates (Phase 6): hide/disable legacy inbox connection, reply sync, tracking, analytics pages if not needed for core workflow.

## Open Questions

- Does the checked-out application already provide a usable email/password login form and route, or is the current app-login flow only Google/Microsoft OAuth? The architecture audit mentions JWT/password hashing but also OAuth app login; inspect actual route and frontend behavior before deciding.
- Can the existing `Campaign` model safely act as the user-facing project/sequence container, or does the target require a distinct `Project` model? Avoid duplicated concepts unless the existing model cannot support the workflow cleanly.
- Should contact groups/lists be represented by an existing model or a new model linked to projects and contacts?
- Should draft snapshots use a new draft/message model, or can an existing model be extended safely without retaining semantics tied to automatic delivery? Decide after inspecting model dependencies.
- Confirm scheduling semantics for each sequence step, including user-selected timezone, delays from manually recorded sent time, pause/resume behavior, and overdue drafts.
- Decide whether legacy inbox connection, reply synchronization, tracking, and analytics pages should be hidden/disabled initially or removed in a later cleanup. They are not required for the core manual-only workflow.
- Decide how first-admin creation and any subsequent account invitations/registration should work without external email delivery.

## Architecture Decisions

- **Keep the current infrastructure.** Reuse FastAPI, React/Vite, SQLAlchemy, PostgreSQL, existing auth utilities, lead/contact handling, and template rendering where practical. Do not rebuild from scratch.
- **Manual-only means no app delivery at all.** Do not add `Send Now`, a send-test action, direct SMTP sending, or a fallback sender. The user copies content and sends it outside the application.
- **Due time means "available in the manual queue."** No timer, scheduler, startup job, or background worker may send a message when it becomes due.
- **A manual sent-status action is local-only.** Store the status and timestamp; then calculate when the next step becomes due. Do not call an external provider.
- **Keep existing data during early phases.** Use additive/backward-compatible migrations. Do not drop legacy tables/columns until the new workflow is stable and the user explicitly approves cleanup.
- **Do not require Google or Microsoft for app login.** Review existing email/password support first and extend it if needed; do not create a parallel authentication system.
- **Email and LinkedIn are draft channels only.** Email steps require an email address; LinkedIn DM steps require a LinkedIn profile URL. Do not integrate with LinkedIn messaging APIs or browser automation.
- **No test/validation commands by default.** The user has instructed the coding agent not to run tests, builds, linting, type checks, or the app. Report changes as unverified unless validation is explicitly authorized later.
- **No automatic Git operations.** Do not commit, push, or deploy without an explicit user request.

## Session Notes

- Repository: `rafsan-scrapes/email_marketer`, the user's customized Quickly fork.
- Deployment: Railway, sourced from the user's GitHub repository.
- User is relatively new to this deployment workflow; implementation instructions should be explicit and incremental.
- Architecture audit summary: FastAPI backend; React 18/Vite/Tailwind frontend; SQLAlchemy async with PostgreSQL; APScheduler; JWT cookies/API keys; existing lead/contact import, campaigns, sequences, and provider-based email delivery.
- Important audit correction: an earlier suggested implementation included a `POST /api/campaigns/{id}/send-now` endpoint. **Do not implement it.** It conflicts with the user's requirement to copy drafts and send them outside the app.
- Desired sequence workflow: generate and store personalized subject/body or LinkedIn DM for each contact and step; make drafts eligible at due time; user copies and sends externally; user marks sent; next step due time is calculated from that manual timestamp plus the configured delay.
- **Files modified in Phase 1:**
  - `app/settings_manager.py` — added `manual_mode` setting (env var `QUICKLY_MANUAL_MODE`, DB-persisted)
  - `app/main.py` — removed `run_slot_scan_job` from APScheduler registration; removed import
  - `app/queue_logic.py` — added early-return guard in `reserve_slots_for_new_leads_bulk`
  - `app/routers/schedule.py` — added early-return guard in `recalculate_all_campaigns`
  - `app/routers/campaigns.py` — added 403 guard in `send_test_email` endpoint
  - `app/routers/smtp.py` — added 403 guard in `send_test_email` endpoint
  - `app/routers/unibox.py` — added 403 guard in `send_unibox_email` endpoint
- No database migrations required in this phase (additive setting only).
- To enable manual mode: set `QUICKLY_MANUAL_MODE=true` in environment (`.env` or deployment config).