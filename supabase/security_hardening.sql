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
