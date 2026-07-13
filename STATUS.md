# Garmin → GolfBox — Status og oversikt

_Sist oppdatert: 13. juli 2026_

Dette dokumentet er «hukommelsen» til prosjektet. Les det først i en ny chat/økt,
så er all kontekst på plass uten å grave i historikken.

## Hva systemet gjør

Du spiller en golfrunde med Garmin-klokka (Approach S50). Innen få minutter blir
runden automatisk lagt inn i GolfBox (norsk WHS-handicap) — riktig klubb, bane, tee
og score — og lagt til godkjenning hos markøren. Alt kjører i skyen (GitHub Actions),
helt uten at Mac-en din er på. Du får push på mobilen når noe skjer.

Flyt: Garmin Connect → (hver ~10 min) GitHub Actions → oppdag ny runde → match
klubb/bane/tee → fyll GolfBox-skjema via Playwright → lagre → varsle (mobil + e-post).

## Arkitektur / nøkkelfiler

- **auto_sync.py** — hjernen i skyen. Oppdager nye runder, kaller golfbox_post per
  runde, styrer state (`data/posted.json`), og varsler. Exit-koder fra golfbox_post
  avgjør handling.
- **golfbox_post.py** (~1560 linjer) — kjernen. Playwright-automasjon av GolfBox sitt
  score-skjema. Matcher klubb (koordinat), bane (navn/par-probe) og tee (etikett/rating).
- **course_matcher.py** — koordinat-basert klubbmatch mot katalogen + lært base.
- **backend/main.py** — FastAPI + normalisering av Garmin-data (også brukt av CLI).
- **notify.py** — varsling: e-post (Gmail) + push (ntfy.sh).
- **central_registry.py** — delt base i Supabase (baner + telemetri/attempts).
- **golfbox_catalog_no.json** — 176 norske klubber m/ koordinater og baner.
- **.github/workflows/auto-sync.yml** — cron hvert 10. min (07–23 norsk tid), lås mot
  dobbel-posting, timeout 20 min, secrets for alt følsomt.

## Exit-koder (golfbox_post --auto → auto_sync)

- **0** = lagret rent
- **4** = lagret, men tee valgt på skjønn (⚠ dobbeltsjekk)
- **2** = GolfBox-økt utløpt (stopp, prøv igjen senere — ikke marker som sett)
- **3** = klubb OK, men bane/tee ikke bekreftet (kan fullføres i web-appen)
- **5** = klubben finnes ikke i GolfBox (privat/utland → kan ikke leveres)
- **6** = Garmin har ikke tee-data ennå (VENT — prøv igjen, opp til `MAX_TEE_WAIT`=4)

## Hva som er bevist å virke

Regresjon (43 runder mot live GolfBox): **34 postes automatisk**, 0 regresjoner.
Bekreftet ende-til-ende fra klokka: runder lander i GolfBox, mail + push kommer.
De resterende er «rene» kategorier: baner utenfor norsk GolfBox (Spania, Oustøen,
Nittedal) håndteres ærlig som «kan ikke leveres», og Garmin-datahull fanges av retry.

## Viktige designvalg (og hvorfor)

- **Generelle løsninger, ikke bane-lapper.** Hver feil vi fant ble løst som et mønster
  som dekker mange baner. De store:
  - ø/æ/å-folding (Garmin stripper norske tegn, GolfBox beholder) — 47 klubber.
  - Eksakt tee-etikett («56»=«56») FØR rating (Garmins 2019-ratinger er utdaterte) — 74 klubber.
  - Hopp over tee-løse placeholder-baner (f.eks. «Narvesen Tour») — 19 klubber.
  - Re-assert bane rett før tee (GolfBox reverterer til standardbane) — 60 fler-bane-klubber.
  - «Hovedbane»-fallback: eneste ordentlige bane når par-probe er tvetydig.
- **Sikkerhetsnett over dekning.** Systemet poster ALDRI feil data — heller flagge for
  manuell fullføring enn å gjette. Best-effort tee merkes alltid «⚠ DOBBELTSJEKK».
- **Vent på Garmin i stedet for å gi opp.** Tee-data fylles med forsinkelse; kode 6 lar
  runden prøve igjen (typisk 2. syklus) før den evt. ber deg fullføre selv.
- **Ærlig varsling.** Tre kategorier: 🔴 fullfør, 🟡 dobbeltsjekk, ⛔ kan ikke leveres.
  E-post kun ved unntak; push ved både suksess og problemer.
- **Delt base (Supabase).** Én bruker spiller en ny bane → alle andre får godt av det
  (nettverkseffekt). Telemetri («attempts») gir en datadrevet feilkø.

## Kjente begrensninger / edge-cases

- **Fullføring krever i dag det lokale dashbordet** (Mac). For fremtidige sky-brukere
  uten Mac finnes ingen hostet fullførings-flyt ennå — større fremtidig bygg.
- Runder der Garmin ALDRI fyller tee-data (`teeBox=None`) går til «fullfør selv».
- `seen`/`pending`-listene i posted.json vokser sakte (kosmetisk).
- En runde som venter på tee-data OG faller ut av Garmins siste-50-vindu løses ikke
  (svært sjeldent for én bruker).
- Nittedal er ikke i katalogen (176 klubber) — enten scrape-hull eller ikke i GolfBox.

## Test- og debugverktøy

- **test_rounds.py** `--all` eller `<id>` — tørr-match alle/utvalgte runder mot live
  GolfBox (poster INGENTING). Viser klubb/bane/tee ✓/⚠/✗. Fasiten på dekning.
- **debug_round.py** `<id>` — full dump: alle noter + hva som faktisk står valgt i skjemaet.
- **diag_club.py** `"<klubb>"` — list en klubbs baner + tees live (avslører tee-løse baner).
- **telemetry.py** — datadrevet feilkø fra Supabase `attempts` (ekte runder).
- **test_notify.py** `<id>` / **notify.py** — test varsling uten å poste.
- **audit_clubs.py**, **test_clubs.py** — katalog-/koordinat-kvalitet.

Kjør alltid med `GOLFBOX_HEADLESS=1` og aktivert `.venv` på Mac-en.

## Sikkerhet

- `.env`, `data/golfbox_state.json`, nettleserprofil er gitignorert — aldri delt.
- Ingen passord/medlemsnr/nøkler i sporede filer (verifisert).
- Alt følsomt i skyen via `${{ secrets }}` (inkl. base64 Garmin-token + GolfBox-økt).
- Supabase anon-nøkkel er den offentlige RLS-nøkkelen.
- Markør må være medspiller (14-24068), ikke deg selv (14-25124).

## Drift / vedlikehold

- **GitHub-secrets** (10): GARMIN_TOKENS_B64, GOLFBOX_STATE_B64, GOLFBOX_USERNAME,
  GOLFBOX_PASSWORD, GOLFBOX_MARKER_MEMBERNO, SUPABASE_URL, SUPABASE_ANON_KEY,
  GMAIL_USER, GMAIL_APP_PASSWORD, NOTIFY_EMAIL, NTFY_TOPIC.
- **Push-emne (ntfy):** `golfbox-06cf5283e6da9b46` (abonnert i ntfy-appen).
- **Hvis GolfBox-økten utløper** (kode 2 gjentatte ganger): logg inn på nytt lokalt,
  oppdater `GOLFBOX_STATE_B64`-secret. (Auto-login fra brukernavn/passord finnes også.)
- **Git fra Mac:** ved «diverged» pga. skyens auto-commits: `git pull --rebase && git push`.

## Neste steg / idéer

- Hostet fullførings-flyt (så sky-brukere uten Mac kan fullføre needs_manual).
- Telemetri-drevet forbedring: la ekte runder fylle feilkøen, fiks toppen.
- Rull ut til flere brukere (delt base gir nettverkseffekt).
- Rydde `seen`/`pending`-vekst; håndtere «falt ut av 50-vindu»-edge.
- Undersøke Nittedal (i GolfBox eller ikke?).
- Vurder ukentlig digest-mail som oppsummering.
