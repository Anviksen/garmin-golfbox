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

**Steg 4 gjennomført (18. juli 2026): `_log_attempt` sender nå `user_id`.**
`central_registry._ATTEMPT_FIELDS` fikk `user_id`. `golfbox_post.py` sender
`os.getenv("GOLFBOX_USER_ID")` (None i enkelt-bruker-modus – uendret
oppførsel). `auto_sync._apply_env()` setter `GOLFBOX_USER_ID` KUN når
`cfg.user_id != "local"` (ellers ville "local" feilet UUID-castingen mot
`attempts.user_id` i Supabase). Verifisert: legacy-kjøring setter aldri
variabelen, multi-bruker-kjøring setter riktig UUID, og den fjernes korrekt
ved bytte tilbake til legacy (ingen lekkasje mellom kjøringer).

**Onboarding-tekster skrevet (18. juli 2026): `SAMTYKKE_OG_PAMELDING.md`.**
Intro, sikkerhetsinfo (plassert rett før passord-feltene – ærlig om kryptering
OG om at dette er et hobbyprosjekt uten garantier), samtykke-avkrysning
(inkl. den ærlige Garmin-ToS-formuleringen fra tidligere i planen), full
feltliste til selve Google-skjemaet, og et driftsnotat (slett skjema-svar med
passord rett etter provisjonering – ikke la dem bli liggende i et regneark).
**Google-skjemaet er bygget og publisert (18. juli 2026)** – se lenke og
detaljer i `SAMTYKKE_OG_PAMELDING.md`. Delt med «alle som har lenken».
Verifisert live i nettleser: alle felt, sikkerhetsinfo-blokk og
samtykke-avkrysning gjengis riktig for en respondent.

**Steg 5 gjennomført (18. juli 2026): drift/feilsøking + skyjobb for multi-bruker.**
Bygget som svar på konkrete spørsmål om skala/kost/drift (se chat-historikk):

- **`telemetry.py`** filtrerer nå på bruker: `python3 telemetry.py <navn>` viser
  kun én persons forsøk, og uten argument vises en «forsøk per bruker»-oversikt
  når multi-bruker-data finnes. Slår opp visningsnavn via `user_store` (best
  effort – virker som før hvis service-role ikke er satt opp). Verifisert i
  sandkasse: eksakt/delvis/tvetydig navnesøk, og at manglende nettverkstilgang
  feiler til tom liste i stedet for krasj.
- **`run_all_users.py`** logger nå vedvarende til `data/run_all_users.log`
  (egen fil på toppnivå, IKKE inni temp-mappa som slettes) – en kjøring kan
  gjennomgås etterpå. Verifisert i sandkasse.
- **`test_user_notify.py <navn-eller-id>`** – nytt verktøy: sender en EKTE
  test-e-post + test-push til én bestemt brukers registrerte kontaktinfo, uten
  å vente på en ekte golfrunde. Nyttig both for å bevise varslingskjeden virker
  OG som generelt feilsøkingsverktøy («jeg fikk ikke varsel» → kjør denne).
  Oppslags-logikken (navn/id, tvetydighet) verifisert i sandkasse; selve
  sendingen krever ekte nettverk – kjør på Mac-en.
- **`.github/workflows/multiuser-sync.yml`** – ny, SEPARAT skyjobb (rører ikke
  `auto-sync.yml`). Ingen Garmin/Golfbox-secrets i workflowen (hentes kryptert
  fra Supabase per bruker i selve scriptet). Laster opp `run_all_users.log`
  som nedlastbar artifact etter hver kjøring.

**LIVE bevist i skyen (18. juli 2026):** Kjørt manuelt via «Run workflow» –
run #1, **success, 53 sekunder**. Loggen viste korrekt oppførsel: fant 1 aktiv
bruker, logget inn på Garmin, fant 50 runder, ingen nye (baseline satt fra
tidligere lokal test) → «Ingen nye runder. Ferdig.» Ingen GolfBox-interaksjon
forsøkt (korrekt – ingenting nytt å poste). Artifact med loggen lastet opp
korrekt. HELE kjeden bevist i den faktiske cloud-runneren, ikke bare lokalt.

**Svar på driftsspørsmålene (fra chatten, til referanse):**
- Ingen hardkodet maks-grense i koden; kun reelt bevist for 1 bruker så langt.
- Kostnad: $0 i dag (offentlig repo = gratis Actions; Supabase gratis-plan gir
  500 MB DB / 5 GB egress/mnd – langt unna med tekstrader for en vennegjeng).
- Kjøring er STRENGT sekvensiell med vilje – 10 samtidige runder køer opp,
  kolliderer ikke.

---

## Steg 6: Garmin-innlogging automatisert i provisjonering + tidsplan lagt til (18. juli 2026)

**Bakgrunn:** Brukeren spurte om «alt en bruker trenger å gjøre er å fylle ut
skjemaet, så går de live med engang» – svaret var nei, av tre grunner: (1)
Garmin-token krevde en egen i-person-økt, (2) `multiuser-sync.yml` hadde ingen
tidsplan (kun manuell trigger), (3) `GOLFBOX_AUTO_SUBMIT="0"` (dry run). Punkt
(2) er nå løst (schedule lagt til, samme mønster som `auto-sync.yml` – hvert
10. min i golf-timene). Punkt (1) er løst med en bevisst avveining – se under.
Punkt (3) er en bevisst gjenværende brems (se «gjenstår»).

**Avveining som ble diskutert og valgt:** To alternativer ble lagt fram:
(A) owner-trigget – skjemaet samler Garmin e-post/passord, ett samlet script
gjør innlogging + provisjonering, eier ser og bekrefter fortsatt før kontoen
opprettes; (B) helautomatisk webhook – null menneskelig involvering, kontoen
opprettes i samme sekund skjemaet sendes inn. Valgt: **(A) nå, med uttalt mål
om (B) senere.** Begrunnelse: prosjektets kjerneprinsipp «sikkerhetsnett over
dekning» tilsier å beholde ett menneskelig sjekkpunkt så lenge det er billig å
gjøre det – webhook-automatisering er notert som fremtidig retning, ikke
forkastet.

**Endringer:**
- **`provision_user.py`** har en ny funksjon `_login_garmin_and_capture_token
  (email, password)` som logger inn med `garminconnect` (samme mønster som
  `fetch_garmin.py`, inkl. MFA-håndtering via interaktiv prompt), fanger
  tokenet, pakker til samme base64-tar-format som `GARMIN_TOKENS_B64`.
  Passordet sendes KUN til selve login()-kallet, skrives aldri til disk, og
  variabelen nulles ut i den kallende koden rett etter. Filsti-fallback
  (manuell fanging) beholdt for edge-case-bruk. `CONSENT_VERSION` bumpet til
  `v2-garmin-passord-i-skjema`. Verifisert i sandkasse: feiler pent uten
  nettverk/med feil creds (ingen krasj, ingen lekkasje av passordet i
  feilmeldinger), og full interaktiv flyt med korrekt feltrekkefølge.
- **`SAMTYKKE_OG_PAMELDING.md` og det publiserte Google-skjemaet** oppdatert i
  tandem: sikkerhetsinfo og samtykketekst nevner nå eksplisitt at
  Garmin-passord spørres om men aldri lagres, to nye påkrevde felt
  («Garmin-epost», «Garmin-passord») lagt til rett etter samtykke-avkrysningen
  og før GolfBox-feltene, driftsnotatet utvidet til å dekke sletting av
  BEGGE passord fra skjema-svar. Verifisert live i nettleseren (respondent-
  visning): riktig rekkefølge, riktig tekst, ingen brutte referanser til at
  Garmin «ikke er med i skjemaet» (den linjen er fjernet/endret).
- **`.github/workflows/multiuser-sync.yml`**: `schedule: "*/10 5-20 * * *"`
  lagt til – men dette er IKKE nok alene (samme innsikt som for
  `auto-sync.yml`: GitHubs egen `schedule`-trigger er hardt strupt på
  gratis-nivå, reelt sett hver 2.–3. time). Den PÅLITELIGE triggeren er en
  ny, separat **cron-job.org**-jobb («Multi-bruker-sync», klonet fra den
  eksisterende «Golfbox auto-sync»-jobben så Authorization-headeren/PAT-en
  ble kopiert uten at noen måtte taste den inn på nytt), som pinger
  `multiuser-sync.yml` sitt dispatch-endepunkt hvert 5. minutt – bekreftet
  live i cron-job.org-dashboardet (neste kjøring synkronisert med den gamle
  jobben). Trygt å automatisere nå fordi `GOLFBOX_AUTO_SUBMIT="0"` fortsatt
  gjelder (dry run).
- **NB (sikkerhet):** PAT-verdien til cron-job.org-triggeren ble ved et uhell
  limt inn i klartekst i chatten under oppsettet. Lav alvorlighet (fine-grained
  token, kun «Actions: Read and write» på dette ene repoet – ingen kode- eller
  hemmelighetstilgang), men bør roteres som god praksis: ny PAT på GitHub →
  oppdater Authorization-header i BEGGE cron-job.org-jobbene → slett den gamle
  PAT-en. Ikke gjort ennå per dags dato – enkel oppgave for en senere øyeblikk.

**Gjenstår før dette er reelt multi-bruker for VENNER (neste steg):**
1. Kjør `test_user_notify.py` for testbrukeren for å bevise push-varsling live
   (e-post allerede bekreftet manuelt av bruker).
2. Del skjema-lenken med første ekte venn. Når svaret kommer inn: kjør
   `provision_user.py`, oppgi Garmin-epost/passord fra svaret – scriptet
   logger inn og provisjonerer i ett, ingen i-person-økt lenger nødvendig.
   Slett skjema-svaret (begge passord) fra Google Forms-arket etterpå.
3. La tidsplanen kjøre en syklus eller to i dry run, se loggene/artifactene i
   Actions-fanen, bekreft at nye brukere behandles korrekt.
4. Når (1)–(3) er bevist trygt over tid: sett `GOLFBOX_AUTO_SUBMIT="1"` –
   dette er bevisst IKKE gjort automatisk, det er en beslutning å ta sammen.
5. Fremtidig retning (uttalt mål, ikke bygget ennå): helautomatisk
   webhook-provisjonering (alternativ B over) – krever en bro mellom Google
   Forms (Apps Script) og en trigger-endepunkt, siden Google Forms ikke kan
   kalle GitHub Actions direkte. Egen, avgrenset økt når det blir aktuelt.
6. (Parkert på brukerens ønske) NGF/GolfBox-kontakt om offisiell API – ikke
   noe tema akkurat nå, kan tas opp igjen senere ved behov.

## Ende-til-ende-test pågår (19. juli 2026)

Full brukerreise gjennomført for reell test: skjema fylt ut selv (som
«testvenn»), `provision_user.py` kjørt med ekte Garmin-/GolfBox-creds.
`auto-sync.yml` disablet manuelt og gammel testrad slettet først, for å unngå
duplikat-posting mens testen pågår. `GOLFBOX_AUTO_SUBMIT="1"` satt midlertidig
i `multiuser-sync.yml` for at testen skal telle fullt ut.

**Observasjon verdt å ta vare på:** Garmin-innloggingen under provisjonering
fikk **429 (rate limited)** på to av tre interne fallback-strategier i
`garminconnect`-biblioteket, før den tredje lyktes. Konkret bekreftelse på
risikoen fra den tidlige ToS-diskusjonen (Garmins Cloudflare-innstramming) –
ikke krise (det gikk bra), men et tegn på at IP-en/kontoen er nærmere Garmins
grense enn antatt. Verdt å følge med på ved fremtidige provisjoneringer; hvis
429 begynner å vinne over alle fallback-strategiene, er det tid for en pause
mellom provisjoneringer, ikke bare mellom vanlige synk-kjøringer.

**To ting fikset underveis i testen (avdekket av reell bruk, ikke planlagt):**
- `provision_user.py` genererer nå selv et tilfeldig ntfy-emne (spurte
  tidligere brukeren om å finne på en selv, uten forklaring på hvordan
  mottakeren faktisk kobler seg på). Se punkt 6 i `SAMTYKKE_OG_PAMELDING.md`
  for den nye guiden.
- Bekreftet (igjen) at skjema-svar ikke leses automatisk inn i
  `provision_user.py` – eier må kopiere fra regnearket manuelt. Notert som
  fremtidig forbedring, ikke bygget nå.

**Ny testbruker:** «Haakon Erla», id `898c6160-f3ae-4799-8eb7-8ca1fcd27df5`.
Ingen `user_round_state` ennå → neste kjøring av `multiuser-sync.yml` vil sette
en BASELINE (markere alle eksisterende runder som sett, poste ingenting) –
akkurat som første kjøring alltid har gjort i enkelt-bruker-systemet. En EKTE
ny runde spilt/registrert ETTER dette tidspunktet er det som faktisk beviser
posting-kjeden. Gjenstår: spille/registrere en ny runde, vente 5–10 min,
bekrefte i GolfBox + varsel + Actions-logg.
