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

## Status: steg 0 og 1 gjennomført (17. juli 2026)

**Steg 0 (kode, pushet):** `auto_sync.py` har en `UserConfig`-dataclass +
`sync_one_user(cfg)` i stedet for global env-lest config. `golfbox_post.py`/
`fetch_garmin.py` har fått `GOLFBOX_DATA_DIR` slik at GolfBox-økt, logg og
rundedata kan isoleres per bruker. Verifisert: `tests/test_logic.py` (32/32) og
`test_rounds.py --all` (67/79 postbare, 0 regresjoner – kjente gjenstående er
Oustøen/Nittedal/utenlandske baner/`teeBox=None`, alle dokumentert fra før).
Se STATUS.md for detaljer.

**Steg 1 (skjema, IKKE kjørt i Supabase ennå):** `supabase_multiuser_schema.sql`
og `user_crypto.py` er skrevet og selvtestet (kryptering/dekryptering av
tekst, feil/manglende nøkkel gir tydelig feil – ikke stille korrupsjon).

Beslutninger tatt:
- **Kryptering:** Fernet (symmetrisk) med én nøkkel i `ENCRYPTION_KEY` (ny
  GitHub-secret + lokal `.env`), ikke Supabase Vault – enklere, og dere
  kontrollerer nøkkelen fullt ut. Krypterte kolonner er `text` (Fernet-tokens
  er allerede base64), ikke `bytea` – unngår escaping-strev over PostgREST.
- **Tilgang:** `users` og `user_round_state` har RLS PÅ og INGEN policies →
  kun `service_role`-nøkkelen (finnes allerede i ethvert Supabase-prosjekt,
  Project Settings → API – IKKE en ny nøkkel dere oppretter) kan lese/skrive.
  `courses`/`attempts` forblir åpne med anon-nøkkelen, som i dag – ingen
  persondata der. `attempts` fikk en valgfri `user_id`-kolonne.
- **Garmin-token i DB:** samme format som dagens `GARMIN_TOKENS_B64`-secret
  (base64-tar av tokenstore-mappa), bare kryptert i `garmin_tokens_enc` i
  stedet for som GitHub-secret. Fortsatt KUN token, aldri Garmin-passord.

**Steg 1 oppsett fullført og verifisert (18. juli 2026):** SQL kjørt i Supabase
(`users`/`user_round_state` finnes), `ENCRYPTION_KEY` og `SUPABASE_SERVICE_ROLE_KEY`
lagt inn i `.env` og som GitHub-secrets, bekreftet med `python3 user_crypto.py`
(krever `.venv` aktivert – `source .venv/bin/activate` – ellers finner den ikke
`.env` siden `python-dotenv` da ikke er installert).

**Steg 2 (kode, IKKE testet mot ekte Supabase ennå):** `user_store.py`
(service-role-klient – adskilt fra `central_registry.py` sin anon-nøkkel-klient
for courses/attempts) + `provision_user.py` (interaktivt script som samler inn
én brukers data, krypterer sensitive felt, viser sammendrag, og setter inn raden
etter eksplisitt bekreftelse). Verifisert i sandkasse: syntaks, en full simulert
kjøring (riktig kryptering, riktig None-gjennomstrømming for hoppet-over felt),
og to sikkerhetsgater – nei til samtykke stopper før noe skjer, nei til
sluttbekreftelse avbryter uten DB-kall. Ekte nettverksfeil (sandkassen har ikke
Supabase-tilgang) feiler pent med tydelig melding, ikke krasj.

**Steg 2 verifisert mot EKTE Supabase (18. juli 2026):** `provision_user.py`
kjørt for eieren selv (egne Garmin-/GolfBox-creds, gjenbrukt – ingen ny
Garmin-innlogging), rad opprettet (`id=daaf65d2-...`), lest tilbake med
`python3 user_store.py`. Hele kjeden – kryptering, service-role-tilgang,
innsetting, tilbakelesing – er nå reelt bevist, ikke bare sandkasse-simulert.

**Steg 3 (kode, IKKE kjørt live ennå): `run_all_users.py`.** Henter aktive
brukere fra Supabase, dekrypterer, materialiserer Garmin-tokenstore
(tar+base64, samme format som `GARMIN_TOKENS_B64`) og GolfBox-økt til en
isolert temp-mappe per bruker, rekonstruerer `posted.json`-state fra
`user_round_state` + `garmin_fails`/`garmin_cooldown_until` fra brukerraden,
kaller `auto_sync.sync_one_user(cfg)`, og synkroniserer alt (state, evt.
friske tokens/økt) tilbake til Supabase etterpå – UANSETT utfall (også ved
`SystemExit`/uventet feil). Én brukers feil stopper aldri de andre.
`user_store.py` fikk fire nye funksjoner: `get_active_users`, `update_user`,
`get_round_state`, `upsert_round_state`.

Erstatter IKKE dagens enkelt-bruker-workflow – `.github/workflows/auto-sync.yml`
kjører fortsatt `build_legacy_config()` helt uendret. Dette er et separat,
manuelt kjørbart script inntil multi-bruker-fasen er bevist trygg.

Verifisert i sandkasse (ingen nettverk der): `py_compile`, `tests/test_logic.py`
(32/32, uendret), state-konvertering begge veier (`_db_rows_to_state`/
`_state_to_db_rows`) med håndlagde eksempler inkl. ny bruker/blandet
seen+posted+needs_manual+pending, tar+base64-rundtur for Garmin-tokenstore
(inkl. at en simulert token-refresh overlever rundturen), GolfBox-økt-rundtur,
og – viktigst – et eksplisitt test som bekrefter at `_apply_env()` ALDRI lekker
én brukers verdier inn i neste (tom felt hos bruker B fjerner faktisk bruker A
sin gjenværende `os.environ`-verdi, testet direkte).

**Steg 3 verifisert LIVE (18. juli 2026):** `run_all_users.py` kjørt mot ekte
Supabase/Garmin for testbrukeren («Haakon A», `GOLFBOX_AUTO_SUBMIT` usatt –
trygt). Fant 50 runder, satte baseline (riktig – `_initialized=False` for en
fersk bruker), rørte ikke GolfBox (baseline returnerer før posting).
Bekreftet med `user_store.get_round_state()`: 50 rader i `user_round_state`,
alle status `seen`. HELE kjeden – kryptering, service-role, materialisering,
sync_one_user, tilbakeskriving til Supabase – er nå bevist live, ikke bare i
sandkasse. Neste kjøring vil oppdage NYE runder normalt (samme logikk som
enkelt-bruker-systemet har kjørt pålitelig siden 13. juli).

Fremgangsmåte som ble brukt for denne testen (til referanse for neste gang):

```bash
cd ~/Documents/garmin-golfbox
source .venv/bin/activate
echo $GOLFBOX_AUTO_SUBMIT        # MÅ være tomt/ikke satt til "1" for denne testen
python3 run_all_users.py
```

Med `GOLFBOX_AUTO_SUBMIT` usatt fyller `golfbox_post.py` skjemaet men LAGRER
IKKE (samme trygge standard som `GOLFBOX_FORCE_SUBMIT`-testene i
GITHUB_OPPSETT.md). Bekreft i loggen at testbrukeren («Haakon A») behandles,
og at `python3 user_store.py` fortsatt viser riktig bruker etterpå. Sjekk også
i Supabase Table Editor at `user_round_state` har fått rader for testbrukeren.
Sett `GOLFBOX_AUTO_SUBMIT=1` og kjør på nytt KUN når du er trygg på at logikken
er riktig – da lagres ekte runder for testbrukeren (deg selv), som er trygt
siden det er din egen, ekte konto.

**Gjenstår før dette er reelt multi-bruker for VENNER (neste steg):**
1. Kjøre testen over, live.
2. Migrere `_log_attempt` i `golfbox_post.py` til å sende med `user_id` (i dag
   sendes ingen bruker-referanse – trivielt å legge til via samme
   `GOLFBOX_DATA_DIR`-mønster, men ikke gjort ennå).
3. Onboarding: samtykketekst (brukes av `provision_user.py` sin ja/nei-sjekk –
   selve teksten som vises til vennen er ikke skrevet ennå) + Google Form,
   Garmin-token én-og-én (se de opprinnelige åpne spørsmålene over – disse er
   fortsatt ubesvart/manuelle).
4. Egen GitHub Actions-workflow som kjører `run_all_users.py` på en tidsplan,
   når (1)–(3) er bevist trygt.
