# Progress Tracker

Update this file after every meaningful implementation change. Record only work that has actually been completed and reported; do not mark code as implemented merely because a prompt or plan exists.

## Current Phase

- **Phase 0 complete: requirements and architecture audit.**
- **Phase 1 complete: enforce manual-only behavior.** All email delivery pathways disabled.
- **Phase 2 complete: native email-and-password authentication.** Users can register and sign in with email/password without OAuth.
- **Phase 3 complete: project and contact-management workflow.** Projects, contact groups, CSV import with column mapping, and lead management implemented.
- **Phase 4 complete: templates, mixed-channel sequences, draft generation, and local draft scheduling.**

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
- **Phase 2 implementation complete: native email-and-password authentication:**
  - **Backend (`app/routers/auth.py`):**
    - Updated `RegisterRequest` schema: email + password + password_confirm + optional username (derived from email if not provided)
    - Updated `LoginRequest` schema: email + password (replaced username)
    - Updated `POST /api/auth/register`: First user registers with email/password, becomes admin. Username derived from email local-part, made unique with counter suffix.
    - Updated `POST /api/auth/login`: Authenticates by email instead of username.
    - Updated `POST /api/auth/users` (admin): Admin creates users with email/password, username derived from email.
    - Password strength validation enforced (min 8 chars, uppercase, lowercase, digit).
    - Password confirmation required on registration.
    - Email normalization (lowercase) and uniqueness enforced.
    - Helpful error messages without exposing account existence.
  - **Frontend (`frontend/src/pages/Login.jsx`):**
    - Added email/password registration form with password confirmation.
    - Added email/password login form.
    - Toggle between login/register modes.
    - OAuth buttons (Google/Microsoft) remain available as alternative ("Or continue with email" divider).
    - Form validation, loading states, error display.
    - On success, redirects to `/` where AuthContext picks up cookies.
    - Preserved backup restore wizard for first user.
  - **Preserved existing OAuth flow** (`app_oauth.py`): Google/Microsoft app login still works, matches by email, links to existing accounts.
  - **No database migrations required**: Existing User model already has nullable `password_hash` for OAuth users, unique email/username constraints.
  - **No outbound email required** for registration or login.
  - **Session management**: Uses existing JWT in httpOnly cookies (30-min access, 7-day refresh), auto-refresh, logout endpoint.
  - **First admin**: Creates account via email/password on fresh DB; subsequent registrations blocked (admin-only user creation).
  - **All data access protected**: Existing `get_current_user` dependency enforces auth on all protected routes.
- **Phase 3 implementation complete: project and contact-management workflow:**
  - **Extended Lead model** (`app/models.py`):
    - Added `first_name`, `last_name`, `linkedin_url`, `company`, `title`, `website` fields
    - Made `email` nullable to support LinkedIn-only contacts
    - Added `do_not_contact` boolean flag for opt-out
    - Added `updated_at` timestamp
    - Added `group_links` relationship for contact group membership
  - **New ContactGroup and ContactGroupLead models** (`app/models.py`):
    - `ContactGroup`: belongs to a campaign (project), has name, description, timestamps
    - `ContactGroupLead`: many-to-many association with unique constraint on (group_id, lead_id)
    - Added relationships and cascading deletes
  - **Extended Campaign model** (`app/models.py`):
    - Added `owner_id` foreign key to User (project ownership)
    - Added `contact_groups` relationship
  - **Extended User model** (`app/models.py`):
    - Added `owned_campaigns` relationship
  - **Database migrations** (`app/database.py`):
    - Added columns for new Lead fields, Campaign.owner_id
    - Created `contact_group` and `contact_group_lead` tables with indexes
  - **New schemas** (`app/schemas.py`):
    - `ProjectCreate`, `ProjectUpdate`, `ProjectResponse`
    - `ContactGroupCreate`, `ContactGroupUpdate`, `ContactGroupResponse`
    - `LeadCreateExtended`, `LeadUpdateExtended`, `LeadResponseExtended`
    - CSV import schemas: `CSVImportPreviewRequest/Response`, `CSVImportExecuteRequest/Response`
    - Contact group member schemas: `ContactGroupLeadAdd`, `ContactGroupLeadResponse`
  - **New API router** (`app/routers/projects.py`):
    - Project CRUD: `POST/GET/PATCH/DELETE /api/projects`, `GET /api/projects/{id}`
    - Contact Group CRUD: `POST/GET/PATCH/DELETE /api/projects/{id}/groups`, `GET /api/groups/{id}`
    - Contact Group Members: `POST/GET/DELETE /api/groups/{id}/members`
    - Lead management: `POST/GET/PATCH/DELETE /api/projects/{id}/leads`
    - CSV Import: `POST /api/projects/{id}/import/preview`, `POST /api/projects/{id}/import/execute`
  - **Authorization**:
    - `get_user_project` dependency verifies project ownership
    - `get_user_contact_group` dependency verifies group ownership via project
    - All endpoints require authentication and ownership
  - **CSV Import Features**:
    - Preview endpoint shows first 20 rows with validation
    - Automatic column mapping detection (email, name, first_name, last_name, linkedin_url, company, title, website)
    - Custom CSV columns preserved in `custom_data` JSON field
    - Validation for email format and LinkedIn URL format
    - Duplicate detection (within file and against database)
    - Three duplicate strategies: "skip" (default), "update", "separate"
    - Supports LinkedIn-only contacts (no email required)
    - Detailed results: imported, updated, skipped, duplicates, errors with details
  - **Lead Management**:
    - Create leads with email and/or LinkedIn URL
    - Search, filter (do_not_contact), pagination
    - Full CRUD with validation
    - Automatic do_not_contact enforcement (can be checked before enrollment)
  - **Files modified in Phase 3:**
    - `app/models.py` — extended Lead, added ContactGroup/ContactGroupLead, extended Campaign/User
    - `app/database.py` — added migrations for new columns and tables
    - `app/schemas.py` — added Project, ContactGroup, Lead extended, CSV import schemas
    - `app/routers/projects.py` — new router with all project/group/lead/import endpoints
    - `app/main.py` — registered projects router
  - **Supported CSV Format** (example):
    ```csv
    email,name,first_name,last_name,linkedin_url,company,title,website,custom_field1,custom_field2
    john@example.com,John Doe,John,Doe,https://linkedin.com/in/johndoe,Acme Inc,CEO,https://acme.com,value1,value2
    jane@example.com,Jane Smith,Jane,Smith,,Globex Corp,CTO,https://globex.com,value3,value4
    ,LinkedIn Only,,,https://linkedin.com/in/linkedinonly,Startup XYZ,Founder,https://startup.xyz,value5,value6
    ```
- **Phase 4 implementation complete: templates, mixed-channel sequences, draft generation, and local draft scheduling:**
  - **New Template model** (`app/models.py`):
    - Reusable templates for email (subject + body, HTML/plain) and LinkedIn DM (body only)
    - Owner-scoped (per-user), with channel field ("email" | "linkedin_dm")
    - Placeholders like `{{first_name}}`, `{{company}}`, `{{custom_csv_column}}` resolved against contact fields
  - **Extended Sequence model** (`app/models.py`):
    - Added `channel` field ("email" | "linkedin_dm") defaulting to "email"
    - Added `drafts` relationship to Draft model
  - **New Draft model** (`app/models.py`):
    - Stores personalized message snapshots per contact per sequence step
    - Fields: campaign_id, sequence_id, lead_id, channel, subject (email), body, status (pending/due/sent/skipped/blocked), due_at, sent_at
    - Relationships to Campaign, Sequence, Lead
    - Preserves rendered content so future template edits don't affect generated drafts
  - **Extended User model** (`app/models.py`):
    - Added `templates` relationship
  - **Database migrations** (`app/database.py`):
    - Created `template` table with indexes
    - Created `draft` table with indexes on campaign_id, sequence_id, lead_id, status, due_at
    - Added `channel` column to `sequence` table (default "email")
  - **New schemas** (`app/schemas.py`):
    - `TemplateCreate`, `TemplateUpdate`, `TemplateResponse`
    - Extended `SequenceCreate`, `SequenceUpdate`, `SequenceResponse` with `channel` field
    - `DraftResponse`, `DraftBatchResponse`, `EnrollContactsRequest`, `DraftStatusUpdate`
  - **New API router** (`app/routers/templates.py`):
    - Template CRUD: `GET/POST /api/templates`, `GET/PATCH/DELETE /api/templates/{id}`
    - Template preview: `POST /api/templates/preview` (renders against a lead, reports missing/unknown placeholders)
    - Draft generation/enrollment: `POST /api/templates/enroll` (enrolls contacts by group or lead IDs, generates personalized drafts for all sequence steps, validates channel eligibility and missing placeholders)
    - Draft management: `GET /api/templates/projects/{project_id}/drafts`, `GET/PATCH /api/templates/drafts/{id}`
    - Manual sent-status action: `POST /api/templates/drafts/{id}/mark-sent` (marks draft sent, calculates next step due time from actual sent time + configured delay, never triggers delivery)
  - **Frontend integration points** (API ready):
    - Template editor with live preview against selected contact
    - Sequence builder with channel selection (email/LinkedIn DM) and delay configuration
    - Enrollment modal with validation (missing fields, channel eligibility)
    - Draft queue view with status filters and "Mark as sent" action
  - **Key behaviors implemented**:
    - Placeholder resolution against standard contact fields + custom CSV data
    - Missing field detection with clear warnings (no silent failures)
    - Channel eligibility: email steps require email address, LinkedIn DM steps require LinkedIn URL
    - First step scheduled at user-selected date/time/timezone
    - Subsequent steps due based on *actual manual sent time* + step delay
    - Draft snapshots stored at enrollment time (template edits don't affect existing drafts)
    - No automatic delivery anywhere — "Mark as sent" only updates local state
  - **Files modified in Phase 4:**
    - `app/models.py` — added Template, Draft models; extended Sequence, User, Campaign
    - `app/database.py` — added migrations for template, draft tables and sequence.channel column
    - `app/schemas.py` — added Template, extended Sequence, Draft schemas
    - `app/routers/templates.py` — new router with all template/sequence/draft endpoints
    - `app/main.py` — registered templates router

## In Progress

- No implementation change is currently in progress. Phase 4 is complete.

## Next Up

1. Manual draft queue UI (Phase 5): implement frontend for draft queue with due-time eligibility, manual sent-status action, next-step due calculation.
2. UI updates (Phase 6): hide/disable legacy inbox connection, reply sync, tracking, analytics pages if not needed for core workflow.

## Open Questions

- Can the existing `Campaign` model safely act as the user-facing project/sequence container, or does the target require a distinct `Project` model? Avoid duplicated concepts unless the existing model cannot support the workflow cleanly.
- Should contact groups/lists be represented by an existing model or a new model linked to projects and contacts?
- Should draft snapshots use a new draft/message model, or can an existing model be extended safely without retaining semantics tied to automatic delivery? Decide after inspecting model dependencies.
- Confirm scheduling semantics for each sequence step, including user-selected timezone, delays from manually recorded sent time, pause/resume behavior, and overdue drafts.
- Decide whether legacy inbox connection, reply synchronization, tracking, and analytics pages should be hidden/disabled initially or removed in a later cleanup. They are not required for the core manual-only workflow.

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
- **Files modified in Phase 2:**
  - `app/routers/auth.py` — updated RegisterRequest/LoginRequest schemas, register/login/admin-create endpoints
  - `frontend/src/pages/Login.jsx` — added email/password forms with toggle, validation, error handling
- **Files modified in Phase 3:**
  - `app/models.py` — extended Lead, added ContactGroup/ContactGroupLead, extended Campaign/User
  - `app/database.py` — added migrations for new columns and tables
  - `app/schemas.py` — added Project, ContactGroup, Lead extended, CSV import schemas
  - `app/routers/projects.py` — new router with all project/group/lead/import endpoints
  - `app/main.py` — registered projects router
- **Files modified in Phase 4:**
  - `app/models.py` — added Template, Draft models; extended Sequence, User, Campaign
  - `app/database.py` — added migrations for template, draft tables and sequence.channel column
  - `app/schemas.py` — added Template, extended Sequence, Draft schemas
  - `app/routers/templates.py` — new router with all template/sequence/draft endpoints
  - `app/main.py` — registered templates router
- No database migrations required in Phase 1-2 (additive settings only, existing User model compatible).
- Phase 3-4 migrations are additive and will run automatically on startup via `app/database.py:_run_migrations()`.
- To enable manual mode: set `QUICKLY_MANUAL_MODE=true` in environment (`.env` or deployment config).
- After deployment: visit the app URL, you'll see the login page with email/password forms. On a fresh database, create the first admin account using email and password. No OAuth credentials required.