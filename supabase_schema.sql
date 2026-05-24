-- Run this in your Supabase SQL editor

create table if not exists visits (
  id bigint primary key,
  datetime timestamptz not null,
  response text not null default '',
  note text not null default '',
  logged_at timestamptz not null default now()
);

alter table visits disable row level security;
