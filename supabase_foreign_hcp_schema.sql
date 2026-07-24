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
