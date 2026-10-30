# Database ER & Schema

## Principles
- No FLOAT for money/credits — NUMERIC(19,4)
- credit_ledger IMMUTABLE (INSERT only)
- Webhook UNIQUE(provider, provider_event_id)
- Soft deletes + retention policy

## Core tables
users, organizations, organization_members, white_label_configs,
projects, scenes, assets, timelines, timeline_tracks, clips, jobs,
ai_providers, ai_models, user_ai_connections, ai_usage_events,
tariff_plans, subscriptions, orders, payments, refunds, webhook_events,
credit_accounts, credit_reservations, credit_ledger,
licenses, license_installations, entitlement_records, collab_sessions, collab_events

See Alembic migrations 001–008 for full DDL.

## Indexes
jobs(organization_id, status) · ai_usage_events(organization_id, created_at) ·
credit_ledger(account_id, created_at) · webhook_events UNIQUE · payments UNIQUE
