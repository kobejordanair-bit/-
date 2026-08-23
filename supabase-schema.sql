-- Run this once in Supabase Dashboard → SQL Editor.
-- Each authenticated user can read and write only their own rows.

create table if not exists public.study_entities (
  user_id uuid not null references auth.users(id) on delete cascade,
  entity_type text not null check (entity_type in ('custom_text', 'practice_record', 'essay_question', 'essay_record')),
  entity_id text not null,
  payload jsonb not null default '{}'::jsonb,
  client_updated_at timestamptz not null default now(),
  deleted_at timestamptz,
  updated_at timestamptz not null default now(),
  primary key (user_id, entity_type, entity_id)
);

create index if not exists study_entities_user_type_idx
  on public.study_entities (user_id, entity_type, client_updated_at desc);

create or replace function public.touch_study_entities_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists study_entities_touch_updated_at on public.study_entities;
create trigger study_entities_touch_updated_at
before update on public.study_entities
for each row execute function public.touch_study_entities_updated_at();

alter table public.study_entities enable row level security;

drop policy if exists "Users manage only their own study entities" on public.study_entities;
create policy "Users manage only their own study entities"
on public.study_entities
for all to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);
