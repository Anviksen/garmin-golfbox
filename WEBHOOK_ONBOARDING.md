# Helautomatisk onboarding (alternativ B)

_Bygget 24. juli 2026, som svar på et konkret ønske: «jeg vil ikke måtte være
på Mac-en for hver ny venn». Dette er «alternativ B» skissert i
`MULTIUSER_PLAN.md` steg 6 (helautomatisk webhook), nå faktisk bygget._

## Hva dette gjør

I dag: venn fyller ut Google-skjemaet → du kjører `provision_user.py` manuelt
på Mac-en → kontoen opprettes.

Nå: venn fyller ut Google-skjemaet → **Google sender svaret automatisk til en
database** → en skyjobb plukker det opp innen 15 minutter, logger inn på
Garmin, oppretter kontoen, og sletter passordene fra den midlertidige
databaseraden → **du får et varsel** (push/e-post) om at personen er lagt
til, eller om noe gikk galt og trenger din hjelp. Ingenting krever at du er
ved Mac-en.

**Bevisste valg tatt i chatten 24. juli 2026** (spurt via spørsmål, ikke
gjettet): du varsles hver gang noen nye legges til (ikke helt stille), og nye
brukeres aller første runde postes i full automatikk med en gang (ingen egen
prøve-periode med kun utfylling).

## Sikkerhetsarkitektur (viktig å forstå)

Repoet er **offentlig**. GitHub Actions-logger fra et offentlig repo er også
offentlig synlige. Derfor er løsningen bygget slik at **klartekst-passord
ALDRI går gjennom GitHub i det hele tatt**:

```
Google-skjema → Google Apps Script → Supabase (pending_signups)
                                              ↓
                          GitHub Actions (process-signups.yml, hvert 15. min)
                                              ↓
                     leser via SUPABASE_SERVICE_ROLE_KEY (aldri i klartekst i logg),
                     logger inn på Garmin, krypterer, oppretter i `users`,
                     SLETTER pending_signups-raden med det samme
```

Apps Script kjører i ditt eget Google-miljø – loggene der er kun synlige for
deg, aldri offentlige. Det er derfor trygt at passordene passerer akkurat
DER, men ingen andre steder i kjeden.

## Oppsett (gjør dette én gang)

### 1. Supabase: opprett `pending_signups`-tabellen

Kjør `supabase_pending_signups_schema.sql` i Supabase SQL Editor (samme
fremgangsmåte som de andre SQL-migrasjonene i repoet).

### 2. Google Apps Script

Se den fyldige oppskriften øverst i `google_apps_script_signup.gs` (kopier
hele fila inn i skjemaets skript-editor). Kort versjon:

1. Åpne påmeldingsskjemaet i Google Forms → ⋮ (tre prikker) → **Skript-redigering**.
2. Lim inn hele `google_apps_script_signup.gs`.
3. Tannhjul-ikonet (**Prosjektinnstillinger**) → **Skriptegenskaper** → legg til:
   - `SUPABASE_URL` = samme verdi som `SUPABASE_URL` i `.env`
   - `SUPABASE_SERVICE_ROLE_KEY` = fra Supabase → Project Settings → API →
     `service_role` (**ikke** `anon`-nøkkelen)
4. Klokke-ikonet (**Utløsere**) → **Legg til utløser** → funksjon
   `onFormSubmit`, hendelseskilde «Fra skjema», hendelsestype «Ved innsending
   av skjema».
5. Send inn en test-besvarelse selv (bruk falske/egne test-verdier, ikke et
   ekte passord du bruker andre steder) og bekreft at en rad dukker opp i
   Supabase Table Editor → `pending_signups`.

### 3. GitHub: bekreft secrets

`.github/workflows/process-signups.yml` bruker secrets som **allerede finnes**
fra `multiuser-sync.yml`/`auto-sync.yml`: `SUPABASE_URL`,
`SUPABASE_SERVICE_ROLE_KEY`, `ENCRYPTION_KEY`, `GMAIL_USER`,
`GMAIL_APP_PASSWORD`. Bekreft at `NOTIFY_EMAIL` og `NTFY_TOPIC` (dine egne,
til varsling om nye brukere) også finnes som secrets – de ble sannsynligvis
satt opp allerede for `auto-sync.yml`.

### 4. Test hele kjeden

1. Send inn en ekte test-besvarelse i skjemaet (kan være deg selv med en
   sekundær test, eller vent på neste ekte venn).
2. Trigger `process-signups.yml` manuelt («Run workflow» i Actions-fanen) i
   stedet for å vente på tidsplanen.
3. Sjekk kjøringsloggen: ble Garmin-innlogging forsøkt, ble brukeren
   opprettet (`python3 user_store.py` viser den), ble `pending_signups`-raden
   slettet, kom det et varsel til deg?

## Feilhåndtering

- **Garmin-innlogging feiler** (feil passord, MFA, Garmin nede): raden
  markeres `failed` i `pending_signups` (IKKE slettet – ligger klar for
  manuell oppfølging), du får et varsel med årsak. Løses ved å kjøre
  `python3 provision_user.py` manuelt for personen (samme flyt som før), og
  deretter slette raden i Supabase selv.
- **MFA på Garmin-kontoen:** støttes IKKE i den automatiske flyten (en
  skyjobb kan ikke taste inn en engangskode) – feiler raskt og tydelig i
  stedet for å henge, med beskjed om å kjøre `provision_user.py` manuelt.
- **Retries:** et forsøk som feiler prøves automatisk på nytt inntil
  `MAX_SIGNUP_ATTEMPTS` (2) i `process_pending_signups.py`, deretter gir
  systemet opp og venter på manuell handling – for å unngå evig loop mot en
  permanent ødelagt påmelding (f.eks. feil passord skrevet inn).
- **Rate-limiting:** kun ÉN påmelding behandles per kjøring, uansett hvor
  mange som venter – samme forsiktighetsprinsipp som
  `MULTIUSER_PLAN.md` alltid har hatt for Garmin-innlogging.

## Admin-dashbord: «Kjør nå»-knapper (valgfritt)

`admin_dashboard.py` kan trigge en skyjobb manuelt (utenom tidsplanen) med en
knapp, via `github_actions.py`. Krever en egen GitHub-token:

1. GitHub → innstillinger for kontoen din → **Developer settings** →
   **Fine-grained tokens** → **Generate new token**.
2. Sett **Repository access** til KUN `garmin-golfbox` (ikke alle repoer).
3. Under **Permissions** → **Actions**: sett til **Read and write**. Ingen
   andre rettigheter trengs.
4. Kopier tokenet og legg det i `.env`:
   ```
   GITHUB_PAT=github_pat_...
   ```
5. Uten dette satt: dashbordet fungerer helt fint, men skjuler
   «Kjør nå»-knappene i stedet for å vise noe som ville feilet.

Samme type token (og samme minste-privilegium-prinsipp) som cron-job.org
allerede bruker for å trigge `auto-sync.yml` – grei anledning til også å
rotere den gamle PAT-en som ved et uhell havnet i klartekst i chatten
tidligere (se `MULTIUSER_PLAN.md` steg 6, notert som ugjort).

## Driftsnotat (uendret prinsipp, se `SAMTYKKE_OG_PAMELDING.md` del 5)

Selv om onboardingen nå er automatisk, bør du fortsatt jevnlig slette gamle
svar fra selve Google Forms-arket (skjemaets egen svar-oversikt) – de
inneholder klartekst-passord helt til Apps Script har sendt dem videre, og
Google Forms-arket er en egen kopi utenfor `pending_signups`-flyten.
