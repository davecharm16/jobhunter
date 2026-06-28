-- Snapshot the generated CV + cover letter into the application at apply-time,
-- so a tracked job's artifacts survive even if ./out/ is wiped and can be
-- re-downloaded from the Applications page.
alter table applications add column if not exists cv_markdown text;
alter table applications add column if not exists cover_letter_markdown text;
