# Multi-bruker-plattform — kickoff / plan

_Opprettet 13. juli 2026. Dette er startdokumentet for et NYTT prosjekt: å la venner
(og på sikt flere) bruke Garmin→GolfBox-automatikken, ikke bare eieren._

> **Til en ny chat:** Les FØRST denne fila, så `STATUS.md` og `CLAUDE.md` i samme
> mappe. `STATUS.md` beskriver det fungerende single-user-systemet som denne
> plattformen skal bygge på. `CLAUDE.md` beskriver arbeidsprinsippene (generelle
> løsninger, sikkerhetsnett, tørr-test før commit, bruker committer fra Mac, norsk).

## Mål

Gå fra ett personlig verktøy til en liten tjeneste der andre kan melde seg på og få
rundene sine automatisk fra Garmin til GolfBox — med sentral telemetri så eieren
(utvikleren) kan feilsøke alles feil ett sted og fikse i koden.

Ønsket brukeropplevelse: personen fyller ut ett skjema (Garmin-innlogging,
GolfBox-innlogging, markør-medlemsnr, e-post, push-preferanse, samtykke), får en kort
oppskrift på push-varsel, og kan melde seg av når som helst. Resten skjer av seg selv.

## Det som allerede finnes (bygg på dette – ikke fra scratch)

Single-user-systemet i denne mappa er velprøvd og gjenbrukes i stor grad:
- `golfbox_post.py` — klubb/bane/tee-matching + GolfBox-utfylling (den tyngste logikken)
- `course_matcher.py` — koordinat-basert klubbmatch + delt katalog
- `notify.py` — e-post + ntfy push
- `central_registry.py` + Supabase — delt banebase OG `attempts`-telemetri (grunnmur!)
- `auto_sync.py` — oppdager nye runder, exit-koder (0/2/3/4/5/6), backoff, pending-retry
- Erfaringer/fallgruver: se `STATUS.md` og `CLAUDE.md` (ø/æ/å-folding, tee-etikett før
  rating, Garmin-forsinkelse → vent, tee-løse baner, n_holes fra scorede hull, osv.)

Kjernematchingen er altså løst. Multi-bruker handler mest om ALT RUNDT: hvem, hvor
lagres det, hvordan kjøres det per bruker, og – viktigst – sikkerhet.

## Den store saken: forvaltning av andres innlogginger

Dette er tyngdepunktet i hele prosjektet og bør styre designet.
- I dag ligger EIERENS creds i GitHub-secrets. For andre må vi lagre DERES passord.
- GolfBox krever brukernavn/passord (nettleser-automasjon) → vanskelig å unngå å lagre.
- Garmin kan reduseres til å lagre kun TOKEN (ikke passord) hvis onboarding gjøres rett.
- Krav: kryptering i ro, streng tilgangskontroll, tydelig samtykke, ærlighet om at dette
  ikke er et selskap med sikkerhetsgarantier, plan for hva som skjer ved lekkasje.
- Beslutning som må tas tidlig: hvor mye ansvar vil eieren påta seg? (Se åpne spørsmål.)

## Arkitektur-skifte (skisse – skal detaljeres i ny chat)

Single-user GitHub Actions skalerer ikke rent til mange. Sannsynlig retning:
- **Database (Supabase Postgres):** tabeller for `users` (config + krypterte creds),
  `attempts` (utvid med `user_id`), `rounds_state` (per-bruker «seen/pending»).
- **Onboarding:** enkelt webskjema → skriver til `users`. Push-emne genereres per bruker.
- **Jobb-motor:** en scheduler som itererer aktive brukere og kjører kjernejobben per
  bruker (gjenbruk `auto_sync`-logikken, parametrisert på bruker). Kandidater: Supabase
  edge functions + pg_cron, eller en liten host (Fly.io/Railway/Render), eller beholde
  GitHub Actions med en matrise – vurderes mot cred-sikkerhet.
- **Sentral telemetri/feilkø:** `attempts` med `user_id` + et status-dashboard (kan
  gjenbruke web-view/artifact). Eier ser alt, feilsøker hos seg selv.
- **Per-bruker varsling + opt-out:** ntfy-emne per bruker; `active`-flagg + avmeldingslenke.

## Garmin-volum ved flere brukere

- Godt: hver bruker har SITT eget token = egen rate-limit-bøtte. Dere deler ikke grensen.
- Følsomt: totalvolum vokser lineært; og ONBOARDING (første Garmin-innlogging per person)
  er det 429-utsatte steget – gjør det forsiktig, én om gangen, aldri i loop.
- Backoff-mekanismen (allerede bygd i `auto_sync.py`) blir per-bruker.
- Behold dagtids-vindu og fornuftig intervall per bruker.

## Fase-plan (ikke bygg SaaS med en gang)

- **Fase 1 – «noen venner»:** Supabase som DB, kryptert cred-lagring, enkelt skjema, én
  scheduler som itererer brukere, telemetri per bruker, opt-out-flagg. Bevis modellen
  med 3–5 personer. Minimalt, ikke overbygd.
- **Fase 2 – hvis det vokser:** selvbetjening, hardere sikkerhet/auth, evt. hostede
  nettleser-arbeidere, bedre dashboard, retningslinjer/vilkår.

## Åpne spørsmål å avklare FØRST i den nye chatten

1. Hvor stort skal dette bli? (3 venner vs. «alle i Norge» → påvirker alt.)
2. Hvor mye cred-ansvar vil eieren påta seg? Aksepterer vi å lagre GolfBox-passord
   kryptert, eller finnes en mindre eksponert vei?
3. Hvor skal jobb-motoren kjøre? (Supabase-funksjoner vs. liten host vs. GitHub-matrise.)
4. Hvordan onboardes Garmin-token trygt uten å trigge 429? (Én-gangs-flyt.)
5. Hvordan håndteres samtykke/ansvar (ToS-eksponering på vegne av andre)?
6. Skjema-teknologi: enkelt (Google Form + manuell provisjonering) vs. eget webskjema.

## Sikkerhet & personvern (må være med fra dag én)

- Krypter creds i ro; aldri i klartekst i repo/logg. Egen nøkkel utenfor DB.
- Minimer hva som lagres (token > passord der mulig).
- Samtykke + enkel, ekte sletting ved opt-out.
- Aldri commit av andres data til et offentlig repo. (Enkelt-bruker-repoet er offentlig
  fordi det bare er eierens egne, ufølsomme metadata – det gjelder IKKE flere brukere.)
