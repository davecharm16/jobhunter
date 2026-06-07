-- Application tracker (spec: 2026-06-07-application-tracker-design.md)
create extension if not exists pgcrypto;  -- gen_random_uuid()

create table if not exists applications (
    id          uuid primary key default gen_random_uuid(),
    slug        text,
    job_title   text not null,
    company     text,
    url         text,
    status      text not null default 'applied'
                check (status in ('applied','interviewing','offer','rejected','withdrawn')),
    notes       text,
    applied_at  timestamptz not null default now(),
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

-- One tracker row per package; many package-less rows (slug null) allowed.
create unique index if not exists applications_slug_unique
    on applications (slug) where slug is not null;

create table if not exists application_status_history (
    id              uuid primary key default gen_random_uuid(),
    application_id  uuid not null references applications(id) on delete cascade,
    from_status     text,
    to_status       text not null,
    changed_at      timestamptz not null default now()
);

create index if not exists ash_application_id_idx
    on application_status_history (application_id);
