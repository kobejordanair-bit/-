-- Run this AFTER supabase-schema.sql in Supabase Dashboard → SQL Editor.
-- Shared library: custom texts and essay questions.
-- Private records: typing and essay performance stay in study_entities per user.

create table if not exists public.learning_workspaces (
  id uuid primary key default gen_random_uuid(),
  name text not null check (char_length(trim(name)) between 1 and 100),
  owner_id uuid not null references auth.users(id) on delete cascade,
  invite_code text not null unique default replace(gen_random_uuid()::text, '-', ''),
  created_at timestamptz not null default now()
);

create table if not exists public.learning_workspace_members (
  workspace_id uuid not null references public.learning_workspaces(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null check (role in ('owner', 'member')) default 'member',
  joined_at timestamptz not null default now(),
  primary key (workspace_id, user_id)
);

create table if not exists public.shared_learning_entities (
  workspace_id uuid not null references public.learning_workspaces(id) on delete cascade,
  entity_type text not null check (entity_type in ('custom_text', 'essay_question')),
  entity_id text not null,
  payload jsonb not null default '{}'::jsonb,
  client_updated_at timestamptz not null default now(),
  deleted_at timestamptz,
  updated_at timestamptz not null default now(),
  primary key (workspace_id, entity_type, entity_id)
);

create index if not exists shared_learning_entities_workspace_type_idx
  on public.shared_learning_entities (workspace_id, entity_type, client_updated_at desc);

create or replace function public.is_learning_workspace_member(p_workspace_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from public.learning_workspace_members
    where workspace_id = p_workspace_id and user_id = auth.uid()
  );
$$;

alter table public.learning_workspaces enable row level security;
alter table public.learning_workspace_members enable row level security;
alter table public.shared_learning_entities enable row level security;

drop policy if exists "Members read learning workspaces" on public.learning_workspaces;
create policy "Members read learning workspaces"
on public.learning_workspaces for select to authenticated
using (public.is_learning_workspace_member(id));

drop policy if exists "Members read workspace members" on public.learning_workspace_members;
create policy "Members read workspace members"
on public.learning_workspace_members for select to authenticated
using (public.is_learning_workspace_member(workspace_id));

drop policy if exists "Members manage shared learning entities" on public.shared_learning_entities;
create policy "Members manage shared learning entities"
on public.shared_learning_entities for all to authenticated
using (public.is_learning_workspace_member(workspace_id))
with check (public.is_learning_workspace_member(workspace_id));

create or replace function public.create_learning_workspace(p_name text)
returns table (workspace_id uuid, workspace_name text, invite_code text)
language plpgsql
security definer
set search_path = public
as $$
declare
  created_workspace public.learning_workspaces;
begin
  if auth.uid() is null then
    raise exception 'Authentication required';
  end if;
  insert into public.learning_workspaces (name, owner_id)
  values (trim(p_name), auth.uid())
  returning * into created_workspace;
  insert into public.learning_workspace_members (workspace_id, user_id, role)
  values (created_workspace.id, auth.uid(), 'owner');
  return query select created_workspace.id, created_workspace.name, created_workspace.invite_code;
end;
$$;

create or replace function public.join_learning_workspace(p_invite_code text)
returns table (workspace_id uuid, workspace_name text)
language plpgsql
security definer
set search_path = public
as $$
declare
  found_workspace public.learning_workspaces;
begin
  if auth.uid() is null then
    raise exception 'Authentication required';
  end if;
  select * into found_workspace
  from public.learning_workspaces
  where invite_code = lower(trim(p_invite_code));
  if found_workspace.id is null then
    raise exception 'Invite code not found';
  end if;
  insert into public.learning_workspace_members (workspace_id, user_id, role)
  values (found_workspace.id, auth.uid(), 'member')
  on conflict (workspace_id, user_id) do nothing;
  return query select found_workspace.id, found_workspace.name;
end;
$$;

grant execute on function public.create_learning_workspace(text) to authenticated;
grant execute on function public.join_learning_workspace(text) to authenticated;
