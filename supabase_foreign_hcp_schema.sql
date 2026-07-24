-- Delt, verifisert stroke-index-database for utenlandske baner (Supabase/Postgres).
-- Kjøres én gang i Supabase SQL Editor. Se foreign_course_registry.py og
-- UTENLANDSKE_BANER_PLAN.md for kontekst/bakgrunn.
--
-- Samme sikkerhetsmodell som `courses`/`attempts` (SENTRALISERING.md): åpen
-- tabell, anon-nøkkelen kan lese/skrive. Ingen persondata – kun bane- og
-- stroke-index-data, samme sensitivitetsnivå som den eksisterende `courses`.

create table if not exists foreign_course_hcp (
  course_global_id bigint primary key,   -- Garmins courseGlobalId, stabilt per bane
  "courseName" text,
  country text,
  "holeHandicaps" text not null,         -- bekreftet riktig, 2 sifre per hull (Garmins format)
  "verifiedAgainst" text,                -- kilde brukt til bekreftelse (f.eks. "caddee.se")
  "verifiedBy" text,                     -- hvem bekreftet (valgfritt)
  "verifiedAt" timestamptz,
  created_at timestamptz not null default now()
);

-- Nye tabeller arver IKKE alltid anon/authenticated sine standard-rettigheter
-- i Supabase (i motsetning til `courses`/`attempts`, satt opp tidlig i
-- prosjektet) – uten denne feiler skriving med "401 Unauthorized" selv om
-- SUPABASE_ANON_KEY er riktig. Trygt å kjøre på nytt om tabellen alt finnes.
grant select, insert, update on foreign_course_hcp to anon, authenticated;

-- Nyere Supabase-prosjekter slår noen ganger PÅ Row Level Security som
-- standard på tabeller laget i SQL Editor. Denne tabellen er ÅPEN med
-- vilje – samme sikkerhetsmodell som `courses`/`attempts` (se
-- supabase_multiuser_schema.sql): ingen persondata, kun bane-/
-- stroke-index-data. RLS PÅ uten policies ville blokkert anon-nøkkelen
-- helt uansett GRANT over.
alter table foreign_course_hcp disable row level security;
