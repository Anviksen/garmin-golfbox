-- Helautomatisk onboarding: Google-skjemaet skriver hit direkte (via Google Apps
-- Script), en skyjobb (process_pending_signups.py) plukker opp EN rad om gangen,
-- logger inn på Garmin, krypterer, og flytter personen til `users`. Se
-- WEBHOOK_ONBOARDING.md for hele oppsettet og MULTIUSER_PLAN.md steg 6 for
-- bakgrunn (dette er «alternativ B» nevnt der).
--
-- SIKKERHETSMODELL: samme som `users`/`user_round_state`
-- (supabase_multiuser_schema.sql) – RLS PÅ og INGEN policies, så KUN
-- service_role-nøkkelen kommer til (aldri anon). Denne tabellen inneholder
-- KLARTEKST-passord (midlertidig, til de er behandlet) – enda strengere grunn
-- til aldri å åpne den for anon/authenticated. Google Apps Script bruker
-- service_role-nøkkelen (lagret i Apps Script sine "Script Properties", ikke i
-- selve skriptteksten) til å sette inn rader.

create table if not exists pending_signups (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  label text not null,
  consent_version text,

  -- Klartekst inntil process_pending_signups.py har behandlet raden - da
  -- krypteres det som skal vare (Garmin-TOKEN, ikke passord) inn i `users`,
  -- og HELE denne raden slettes umiddelbart etterpå. Ligger den lenge, er
  -- noe galt (se status/error_message).
  garmin_email text,
  garmin_password text,
  golfbox_username text,
  golfbox_password text,
  golfbox_marker_memberno text,
  golfbox_marker_name text,
  notify_email text,
  wants_push boolean not null default false,

  status text not null default 'pending'
    check (status in ('pending', 'processing', 'failed')),
  error_message text,
  attempts int not null default 0
);

alter table pending_signups enable row level security;
-- Ingen policies med vilje – se sikkerhetsmodell-kommentaren øverst.
