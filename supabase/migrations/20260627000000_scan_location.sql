-- Configurable scan search location (e.g. "Philippines", "Remote", "Cebu").
-- Empty string = no specific location (scanner falls back to the candidate's
-- profile location / searches broadly).
alter table scan_settings
    add column if not exists location text not null default '';
