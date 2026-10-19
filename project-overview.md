# Quickly Manual Outreach Workspace

## Overview

This project customizes the existing `rafsan-scrapes/email_marketer` fork of Quickly into a manual outreach workspace for managing contacts, importing CSV files, personalizing email and LinkedIn direct-message templates, organizing multi-step sequences, and preparing drafts for manual delivery. The application stores each contact's rendered message content and due date so the user can copy the subject and body (or LinkedIn DM), send it outside the application, and then record the message as sent. The application must not deliver emails or LinkedIn messages automatically or through an in-app send action. The goal is to reuse Quickly's existing React/Vite frontend, FastAPI backend, SQLAlchemy/PostgreSQL data layer, contact import, and personalization logic instead of rebuilding the core infrastructure.

## Goals

1. Make all outreach **manual-only**: generate, save, schedule, and display drafts, but never deliver a message from the app or its background jobs.
2. Let the user create an account and sign in using email and password without requiring Google or Microsoft sign-in or an email-provider connection.
3. Organize outreach into projects and contact groups, with CSV imports that preserve custom columns and support contacts who have an email address, a LinkedIn URL, or both.
4. Support reusable email subject/body templates and LinkedIn DM body templates, with placeholders populated from standard contact fields and arbitrary CSV columns.
5. Support multi-step sequences with configurable channels and delays, storing a personalized snapshot for each contact and step.
6. Provide a manual outreach queue where the user can see upcoming, due, blocked, skipped, and completed drafts; copy their content; open a contact's LinkedIn profile; and record manual completion.
7. Preserve existing user and contact data and deploy changes through the existing GitHub-to-Railway workflow without replacing the core technology stack.

## Core User Flow

1. The user registers or signs in using the application's email-and-password authentication.
2. The user creates or opens a project and creates a contact group/list.
3. The user imports a CSV, previews the rows, maps columns, and preserves unmapped columns as custom contact fields.
4. The user creates or selects reusable email and/or LinkedIn DM templates, using placeholders such as `{{first_name}}`, `{{company}}`, `{{title}}`, and `{{custom_csv_column}}`.
5. The user creates a sequence with ordered email and LinkedIn DM steps, delays, and an initial due date/time with a defined timezone.
6. The user enrolls eligible contacts. The application renders and stores a content snapshot for each step and contact, records scheduling metadata, and flags any step that lacks the required contact fields. **Enrollment must not send anything.**
7. The manual outreach queue shows drafts that are upcoming, due, blocked, or completed. A due time makes a draft available to the user; it never triggers delivery.
8. The user copies the email subject/body or LinkedIn DM, sends it outside the application, then returns to the app and explicitly marks it sent. The app records the status and sent timestamp locally.
9. The next sequence step becomes due according to its configured delay from the manually recorded sent time. The user can skip a step, stop a contact's sequence, pause/resume a sequence, or mark a contact as do-not-contact.

## Features

### Authentication and Account Security

- Use email/password registration and login without requiring Google or Microsoft OAuth.
- Reuse the existing secure password hashing and JWT/session implementation where appropriate rather than creating a duplicate authentication system.
- Preserve the current first-administrator/account-creation protections and make the desired account provisioning flow explicit.
- Enforce authorization in the backend so a user cannot access another user's projects, groups, contacts, templates, sequences, or drafts.
- Do not require an outbound email service merely to create an account or log in.

### Projects, Groups, Contacts, and CSV Import

- Provide projects for organizing campaigns or outreach initiatives and groups/lists within projects.
- Reuse the existing campaign/lead domain where this is safe and avoids duplicating concepts; add a separate project or group model only when the existing models cannot support the intended workflow cleanly.
- Support contact fields including first name, last name, full name, email, company, title, website, LinkedIn URL, and arbitrary custom CSV fields.
- Allow contacts to be imported with an email, a LinkedIn URL, or both; neither channel's identifier should be mandatory when the other is usable.
- Provide CSV preview, field mapping, validation feedback, duplicate handling, and import summaries.
- Allow contact search, editing, archiving, and do-not-contact/opt-out status.

### Templates and Personalization

- Store reusable email templates with separate subject and body fields.
- Store reusable LinkedIn DM templates with a body and no subject.
- Resolve placeholders against standard contact fields and custom CSV fields.
- Preview templates against a selected contact and flag missing or unknown placeholders.
- Store rendered subject/body snapshots for generated drafts so later template edits do not silently change already generated messages.

### Sequences and Draft Scheduling

- Allow ordered steps with a channel (`email` or `linkedin_dm`), a template or editable message content, and a configurable delay.
- Schedule the first step using a user-selected date/time and timezone.
- Calculate the next step's due time from the time the user manually marks the preceding step as sent, plus the configured delay.
- Generate and store future step content when enrolling a contact, but do not make a follow-up eligible until the preceding step is manually marked sent.
- Provide pause, resume, skip, and stop controls that affect local sequence/draft state only.
- Represent scheduling as draft eligibility, not as an instruction to send.

### Manual Outreach Queue

- Show upcoming, due, blocked, skipped, stopped, and completed drafts.
- Filter by project, group, contact, channel, sequence, status, and due date.
- Show contact details, available email/LinkedIn destination, sequence step, and scheduled time.
- Provide copy-subject, copy-body, copy-subject-and-body, and copy-DM actions.
- Provide an option to open a contact's LinkedIn profile when a valid URL exists.
- Provide a confirmation step before marking a draft sent, then store the user's action and timestamp locally.
- Never make the “Mark as sent” action call an email provider or any external message-delivery API.

### Manual-Only Safety and Data Preservation

- Disable all actual delivery paths, including automatic scheduler jobs, retry handlers, bulk-send actions, direct SMTP sending, provider-based sending, and indirect API/MCP/webhook paths that could trigger delivery.
- Do not add a `Send Now` button or any other in-app delivery action.
- Do not keep an automatically re-enableable sending-mode flag as the primary safeguard.
- Do not register background delivery jobs on application startup. Scheduled times may be calculated or queried by the application, but they must never dispatch a message.
- Preserve existing tables and data in initial implementation stages. Prefer additive, backward-compatible migrations; do not drop `QueueSlot`, `EmailLog`, `CampaignLead`, inbox/account tables, or existing columns as part of the initial safety changes.
- Existing sender/provider code may be retained temporarily if needed to avoid breaking imports or startup, but all reachable delivery entry points must be disabled. Remove obsolete provider features only after dependencies and data impact are understood.

## Scope

### In Scope

- Customizing the existing Quickly repository rather than rebuilding the application from scratch.
- Email/password application authentication without requiring Google sign-in.
- Project and group/list organization, contact management, CSV import, and arbitrary contact fields.
- Reusable email and LinkedIn DM templates with placeholder personalization.
- Mixed-channel, multi-step sequences with delays and manual sent-state transitions.
- Persisted per-contact, per-step draft snapshots and a manual outreach queue.
- Local scheduling/status updates that never trigger external delivery.
- Backend authorization, safe database migrations, preserving existing records, and maintaining the current Railway deployment setup.
- Updating documentation and this progress tracker after each meaningful implementation change.

### Out of Scope

- Automatic email sending, scheduled email delivery, automated retries, automated follow-up dispatch, or bulk sending.
- Sending email from within the app, including a `Send Now` action, SMTP send form, Gmail API delivery, or Microsoft Graph delivery.
- Sending LinkedIn messages through an API, browser automation, or any other app-driven mechanism. LinkedIn messages are drafts for the user to send manually.
- Requiring the user to connect a Google or Microsoft account to register or sign in.
- Requiring connected sending inboxes for the core workflow.
- Rebuilding the React/Vite frontend, FastAPI backend, or PostgreSQL infrastructure solely to support this workflow.
- Destructive cleanup of legacy scheduling/sending tables during the initial implementation.
- New analytics, open/click tracking, inbox synchronization, or provider integrations unless a later explicit requirement establishes a need for them.

## Success Criteria

1. A user can register and sign in using email and password without Google/Microsoft OAuth or a connected sending inbox.
2. The user can create a project and a group, import a CSV, map fields, and retain custom columns for placeholders.
3. Contacts with only a LinkedIn URL can participate in LinkedIn DM steps; contacts with only an email address can participate in email steps.
4. Email subject/body and LinkedIn DM templates render contact-specific standard and custom-field placeholders correctly, with missing fields clearly flagged.
5. Enrolling contacts generates persisted, personalized draft snapshots for each sequence step without sending any message.
6. Drafts become eligible for the manual queue at their configured due time; the scheduler and application startup never deliver messages.
7. Copy actions copy the stored content accurately. Opening LinkedIn opens the supplied profile URL only. Marking a draft sent updates local state and timestamp only.
8. A later sequence step becomes due based on the configured delay after the previous step is manually marked sent, not based on a scheduled automatic send.
9. No frontend, REST API, background worker, scheduler, SMTP path, provider integration, MCP tool, webhook, or retry path can deliver a message from the application.
10. Existing accounts and records remain intact through additive migrations; no initial implementation step drops existing tables or columns.
11. All code changes are made in the existing repository and can continue to be deployed through the existing GitHub-to-Railway workflow.

## Implementation and Agent Working Rules

- Read the relevant existing code before changing it; architecture-audit findings must be confirmed against the repository.
- Make changes directly when asked to implement a phase; do not stop at recommendations or a plan.
- Preserve uncommitted work and unrelated changes. Never reset or discard existing modifications.
- Do not run tests, smoke tests, builds, linting, type checks, or the application unless the user explicitly authorizes validation. Do not install dependencies.
- Do not commit, push, or deploy unless the user explicitly asks.
- Do not print or expose credentials, tokens, `.env` values, or other secrets.
- After each meaningful change, update `progress-tracker.md` with files changed, work completed, known limitations, and the next step.
- In completion reports, clearly identify unverified behavior when validation commands were not run.
