-- Automated Job Scan (spec: 2026-06-26-job-scan-design.md)
create extension if not exists pgcrypto;  -- gen_random_uuid()

-- Single-row config table (id is always true).
create table if not exists scan_settings (
    id              boolean primary key default true check (id),
    search_titles   text[] not null default '{}',
    sites_enabled   text[] not null default '{indeed,onlinejobs_ph,jobstreet,linkedin}',
    picks_per_site  int    not null default 3 check (picks_per_site between 1 and 10),
    enabled         boolean not null default true,
    updated_at      timestamptz not null default now()
);
insert into scan_settings (id) values (true) on conflict (id) do nothing;

create table if not exists scans (
    id            uuid primary key default gen_random_uuid(),
    started_at    timestamptz,
    finished_at   timestamptz,
    status        text not null default 'completed'
                  check (status in ('completed','partial')),
    site_summary  jsonb not null default '{}'::jsonb,
    created_at    timestamptz not null default now()
);

create table if not exists scan_candidates (
    id          uuid primary key default gen_random_uuid(),
    scan_id     uuid not null references scans(id) on delete cascade,
    site        text not null
                check (site in ('indeed','onlinejobs_ph','jobstreet','linkedin')),
    url         text not null unique,
    title       text not null,
    company     text,
    location    text,
    jd_text     text not null,
    fit_reason  text,
    fit_score   numeric,
    status      text not null default 'new'
                check (status in ('new','generated','dismissed')),
    slug        text,
    created_at  timestamptz not null default now()
);

create index if not exists scan_candidates_scan_id_idx on scan_candidates (scan_id);
create index if not exists scan_candidates_status_idx on scan_candidates (status);
