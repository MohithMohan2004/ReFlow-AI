-- ReFlow security hardening for Supabase.
--
-- NOT APPLIED AUTOMATICALLY. Run it yourself, first on a staging copy, then in
-- production: Supabase dashboard -> SQL Editor -> New query -> paste -> Run.
-- Each section says which report item it closes and what to check afterwards.

-- ---------------------------------------------------------------------------
-- Item 5: GraphQL alias batching
-- ReFlow never calls /graphql/v1. Remove the endpoint's access for the public
-- roles (or drop the extension entirely with: drop extension if exists pg_graphql;).
-- Check afterwards:
--   curl -s -X POST "$SUPABASE_URL/graphql/v1" -H "apikey: $SUPABASE_KEY" \
--        -H "Content-Type: application/json" -d '{"query":"{__schema{types{name}}}"}'
--   must return an error / permission denied, not a schema.
-- ---------------------------------------------------------------------------
revoke usage on schema graphql from anon, authenticated;
revoke execute on function graphql.resolve from anon, authenticated;

-- ---------------------------------------------------------------------------
-- Item 12: RLS and views
--
-- ORDER MATTERS: deploy the app version from branch security-hardening FIRST.
-- From that version on, the server reads and writes public.tanker_locations
-- over DATABASE_URL (as the table owner), so the public anon key no longer
-- needs any access. Running step 1 before that deploy stops live tracking.
-- ---------------------------------------------------------------------------

-- Step 1: close public.tanker_locations to the anon and authenticated roles.
drop policy if exists "tanker_locations_anon_all" on public.tanker_locations;
alter table public.tanker_locations enable row level security;
revoke all on table public.tanker_locations from anon, authenticated;

-- Step 2: report. Both queries must return zero rows when you're done.
-- 2a. public tables without RLS:
select c.relname as table_without_rls
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind in ('r', 'p') and not c.relrowsecurity;

-- 2b. public views that run with their owner's rights (bypass RLS):
select c.relname as view_without_security_invoker
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind in ('v', 'm')
  and not exists (
      select 1 from unnest(coalesce(c.reloptions, '{}')) o
      where lower(o) in ('security_invoker=true', 'security_invoker=on', 'security_invoker=1')
  );

-- Step 3 (only after reading step 2's output; other apps may share this
-- Supabase project): turn RLS on for every public table and make every public
-- view run with the caller's rights. Tables then have no policies, so the
-- anon key can't read them; add a policy for anything that must stay public.
-- do $$
-- declare r record;
-- begin
--   for r in select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
--            where n.nspname = 'public' and c.relkind in ('r', 'p') and not c.relrowsecurity loop
--     execute format('alter table public.%I enable row level security', r.relname);
--   end loop;
--   for r in select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
--            where n.nspname = 'public' and c.relkind = 'v' loop
--     execute format('alter view public.%I set (security_invoker = true)', r.relname);
--   end loop;
-- end $$;
--
-- Check afterwards (staging), with the publishable key; both must return [] or 401/403:
--   curl -s "$SUPABASE_URL/rest/v1/tanker_locations?select=*" -H "apikey: $SUPABASE_KEY"
--   curl -s "$SUPABASE_URL/rest/v1/profiles?select=*"         -H "apikey: $SUPABASE_KEY"
-- The Flask app's own orders live in schema "reflow", which PostgREST does not
-- expose (Settings -> API -> Exposed schemas should list only public, graphql_public).
