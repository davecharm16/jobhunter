-- Single-row live status for the in-progress scan (drives the dashboard banner).
create table if not exists scan_status (
    id           boolean primary key default true check (id),
    status       text not null default 'idle',  -- idle | running | completed | error
    started_at   timestamptz,
    finished_at  timestamptz,
    new_count    int not null default 0,
    site_summary jsonb not null default '{}',
    updated_at   timestamptz not null default now()
);

insert into scan_status (id) values (true) on conflict (id) do nothing;
