-- Run this in your Supabase SQL editor to set up the visits table

create table if not exists visits (
  id uuid primary key default gen_random_uuid(),
  visited_at timestamptz not null,
  response text not null check (response in ('Yes', 'No', 'No Answer')),
  created_at timestamptz not null default now()
);

-- Disable RLS for simplicity (anon key has full access)
-- If you want to restrict access, enable RLS and add policies
alter table visits disable row level security;
