-- ReFlow: roles move from user_metadata (user-editable) to app_metadata
-- (writable only with the service role).
--
-- Run in Supabase -> SQL Editor (staging first). Safe to run BEFORE deploying:
-- the current app still reads user_metadata, and the new app reads
-- app_metadata first. Admins must get app_metadata.role (step 4) BEFORE the
-- new app is deployed, or they lose the admin console until they do.

-- Step 1: new signups copy their *public* role into app_metadata once, at
-- insert. Later edits to user_metadata change nothing. Admin roles are never
-- copied.
create or replace function public.reflow_set_signup_role()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if lower(coalesce(new.raw_user_meta_data ->> 'role', '')) in ('demand', 'stp', 'tanker')
     and coalesce(new.raw_app_meta_data ->> 'role', '') = '' then
    new.raw_app_meta_data := coalesce(new.raw_app_meta_data, '{}'::jsonb)
      || jsonb_build_object('role', lower(new.raw_user_meta_data ->> 'role'));
  end if;
  return new;
end;
$$;

revoke execute on function public.reflow_set_signup_role() from public, anon, authenticated;

drop trigger if exists reflow_signup_role on auth.users;
create trigger reflow_signup_role
  before insert on auth.users
  for each row execute function public.reflow_set_signup_role();

-- Step 2: existing accounts with a public role get it in app_metadata too.
update auth.users
set raw_app_meta_data = coalesce(raw_app_meta_data, '{}'::jsonb)
      || jsonb_build_object('role', lower(raw_user_meta_data ->> 'role'))
where lower(coalesce(raw_user_meta_data ->> 'role', '')) in ('demand', 'stp', 'tanker')
  and coalesce(raw_app_meta_data ->> 'role', '') = '';

-- Step 3: report. Accounts that *claim* an admin role in user_metadata. Only
-- the ones you recognise should get step 4; anyone else set it themselves.
select id, email, raw_user_meta_data ->> 'role' as claimed_role,
       raw_app_meta_data ->> 'role' as app_role, created_at, last_sign_in_at
from auth.users
where lower(coalesce(raw_user_meta_data ->> 'role', '')) in ('admin', 'superadmin')
   or lower(coalesce(raw_app_meta_data ->> 'role', '')) in ('admin', 'superadmin')
order by created_at;

-- Step 4: grant admin roles explicitly, one account at a time.
-- update auth.users
-- set raw_app_meta_data = coalesce(raw_app_meta_data, '{}'::jsonb) || '{"role": "superadmin"}'
-- where email = 'YOUR-EMAIL-HERE';
--
-- update auth.users
-- set raw_app_meta_data = coalesce(raw_app_meta_data, '{}'::jsonb) || '{"role": "admin"}'
-- where email = 'APPROVALS-ADMIN-EMAIL-HERE';

-- Check: every row of step 3 you trust now shows app_role. Sign in again
-- after a change (roles are read at sign-in).
