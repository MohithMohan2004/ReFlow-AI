-- Run this once in the Supabase SQL editor (Project -> SQL Editor -> New query)
-- Stores the LATEST known GPS location for each tanker operator.
-- One row per tanker_operator_id (upserted on every ping from the browser).

create table if not exists public.tanker_locations (
    tanker_operator_id text primary key,
    user_id text,
    tanker_operator_name text,
    latitude double precision not null,
    longitude double precision not null,
    accuracy double precision,
    speed double precision,
    heading double precision,
    recorded_at timestamptz,
    updated_at timestamptz default now()
);

-- Keep lookups by operator fast (primary key already covers this, index kept
-- here in case the table is later changed to a history table instead).
create index if not exists idx_tanker_locations_operator
    on public.tanker_locations (tanker_operator_id);

-- Row Level Security.
-- The Flask server reads and writes this table over its own database
-- connection (DATABASE_URL, as the table owner), so the public anon key needs
-- no access at all. RLS on with no policies = anon/authenticated see nothing.
-- (The old "tanker_locations_anon_all" policy let anyone with the publishable
-- key read and overwrite every truck's location.)
alter table public.tanker_locations enable row level security;

drop policy if exists "tanker_locations_anon_all" on public.tanker_locations;

revoke all on table public.tanker_locations from anon, authenticated;
