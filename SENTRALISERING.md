# Sentralisering – én delt bane-database for alle brukere

Dette flytter bane-basen til skyen (Supabase, gratis), så alle brukere leser fra og
bidrar til SAMME base. Når én bruker lærer en ny bane, får alle andre den automatisk.

Uten dette oppsettet kjører alt lokalt som før – sentralbasen er et valgfritt lag.

Estimert tid: ~15 min én gang.

---

## Hvorfor Supabase

Gratis, ekte database (Postgres) med et ferdig REST-API og ingen server å drifte.
Rikelig gratis-kvote for dette formålet.

---

## Steg 1 – Opprett prosjekt

1. Gå til [supabase.com](https://supabase.com) → **Start your project** → logg inn
   (GitHub-konto funker).
2. **New project**. Velg navn (f.eks. `golf-registry`), et passord (lagres av
   Supabase), og region **Europe (Frankfurt)** e.l. Opprett.
3. Vent ~1 min mens databasen settes opp.

## Steg 2 – Lag tabellen

Åpne **SQL Editor** (venstre meny) → **New query** → lim inn og kjør:

```sql
create table if not exists courses (
  id bigint generated always as identity primary key,
  lat double precision not null,
  lon double precision not null,
  club text not null,
  course text default '',
  tee text default '',
  garmin_name text default '',
  country text default 'no',
  source text default 'learned',
  updated_at timestamptz default now()
);

alter table courses enable row level security;

-- MVP: la hvem som helst lese og bidra (åpen felles-base).
create policy "les alle" on courses for select using (true);
create policy "bidra" on courses for insert with check (true);
```

## Steg 3 – Hent nøklene

**Project Settings** (tannhjulet) → **API**:
- **Project URL** → `SUPABASE_URL`
- **Project API keys → anon public** → `SUPABASE_ANON_KEY`

Legg dem i `.env`:

```
SUPABASE_URL=https://xxxxxxxx.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOi...
```

## Steg 4 – Test tilkoblingen

```bash
cd ~/Documents/garmin-golfbox
source .venv/bin/activate
python3 central_registry.py
```
Skal si: «Sentralbasen (…) har 0 baner.»

## Steg 5 – Seed basen (last opp det du har)

```bash
python3 seed_central.py
```
Laster opp dine lærte baner + katalogen med koordinater (~130 baner). Kjør
`python3 central_registry.py` igjen – nå skal tallet stemme.

## Steg 6 – Synk ned (på hver maskin / før auto-sync)

```bash
python3 sync_registry.py
```
Henter alt fra sentralbasen inn i den lokale `course_db.json`. Kjør dette på nye
maskiner, eller jevnlig, så alle har hele basen.

---

## Slik virker det i praksis

- **Lære:** når du (eller en annen bruker) retter en bane manuelt, sendes den opp til
  sentralbasen automatisk (via `central_registry.contribute`).
- **Lese:** `sync_registry.py` henter alt ned til den lokale matcheren. Kjør det i
  auto-sync-arbeidsflyten (før posting) så skyen alltid har siste base.
- **Nettverkseffekt:** jo flere som bruker det, jo mer komplett blir basen – for alle.

## Videre (når du vil)
- Legge `sync_registry.py` inn i GitHub Actions-arbeidsflyten (kjør før auto_sync).
- Server-side dedup (unik-constraint på avrundede koordinater) for å holde basen ren.
- Egen «anon key» per bruker / rate-limiting hvis basen åpnes for mange.
