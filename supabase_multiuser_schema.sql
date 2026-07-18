-- Multi-bruker-skjema for garmin-golfbox (Supabase/Postgres).
-- Kjøres én gang i Supabase SQL Editor. Se MULTIUSER_PLAN.md for kontekst/beslutninger.
--
-- SIKKERHETSMODELL (viktig – les før du kjører):
--   - `courses` og `attempts` er fortsatt ÅPNE (anon-nøkkelen kan lese/skrive) – de
--     inneholder ingen persondata, kun bane- og telemetridata. Uendret fra i dag.
--   - `users` og `user_round_state` har RLS PÅ og INGEN policies. Det er BEVISST:
--     uten en eksplisitt "using"-policy får anon/authenticated ALDRI tilgang – kun
--     service_role (som omgår RLS by design i Supabase) kan lese/skrive. Jobb-
--     motoren (GitHub Actions) må derfor bruke en ny secret
--     SUPABASE_SERVICE_ROLE_KEY (hentes fra Project Settings → API – den finnes
--     allerede i ethvert Supabase-prosjekt, du oppretter ikke en ny), IKKE
--     SUPABASE_ANON_KEY, for disse to tabellene.
--   - Alt i *_enc-kolonnene er kryptert FØR det sendes hit (se user_crypto.py).
--     Supabase/RLS er andrelinjeforsvar, ikke eneste forsvar – rå passord/tokens
--     skal ALDRI treffe disse kolonnene ukryptert.

create extension if not exists pgcrypto;  -- for gen_random_uuid()

create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  label text not null,                       -- visningsnavn til logglinjer (IKKE i git)
  active boolean not null default true,
  consent_at timestamptz,
  consent_version text,                      -- hvilken samtykketekst de godtok

  -- Garmin: KUN token, ALDRI passord (bevisst valg – se MULTIUSER_PLAN.md).
  -- Kryptert base64-tar av tokenstore-mappen: samme format som GARMIN_TOKENS_B64
  -- er i dag, bare kryptert og lagret i DB i stedet for som GitHub-secret.
  garmin_tokens_enc text,
  garmin_fails int not null default 0,
  garmin_cooldown_until timestamptz,

  -- GolfBox
  golfbox_username_enc text,
  golfbox_password_enc text,
  golfbox_session_enc text,                  -- kryptert storage_state (økt-cache,
                                              -- minimerer faktiske GolfBox-innlogginger)
  golfbox_marker_memberno text,
  golfbox_marker_name text,

  -- Varsling
  notify_email text,
  ntfy_topic text,
  ntfy_server text,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table users enable row level security;
-- Ingen policies med vilje – se sikkerhetsmodell-kommentaren øverst i fila.

-- Erstatter posted.json sine seen/posted/needs_manual/pending-arrays (som vokser
-- ubegrenset, se STATUS.md) med ekte rader – én per (bruker, runde).
create table if not exists user_round_state (
  user_id uuid not null references users(id) on delete cascade,
  garmin_round_id bigint not null,
  status text not null check (status in ('seen', 'posted', 'needs_manual', 'pending')),
  attempts int not null default 0,           -- tee-vente-forsøk (dagens "pending"-teller)
  reason text,
  updated_at timestamptz not null default now(),
  primary key (user_id, garmin_round_id)
);

alter table user_round_state enable row level security;
-- Samme som over: ingen policies, kun service_role.

-- Telemetri: attempts finnes allerede (courses-basen). Får bare en valgfri kobling
-- til hvilken bruker forsøket gjaldt. Nullable – eksisterende rader og fremtidige
-- manuelle test-forsøk (test_rounds.py) er fortsatt gyldige uten den.
alter table attempts add column if not exists user_id uuid references users(id);
