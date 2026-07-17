# Garmin → GolfBox — Status og oversikt

_Sist oppdatert: 13. juli 2026_

Dette dokumentet er «hukommelsen» til prosjektet. Les det først i en ny chat/økt,
så er all kontekst på plass uten å grave i historikken.

## Hva systemet gjør

Du spiller en golfrunde med Garmin-klokka (Approach S50). Innen få minutter blir
runden automatisk lagt inn i GolfBox (norsk WHS-handicap) — riktig klubb, bane, tee
og score — og lagt til godkjenning hos markøren. Alt kjører i skyen (GitHub Actions),
helt uten at Mac-en din er på. Du får push på mobilen når noe skjer.

Flyt: Garmin Connect → (hver ~5–10 min) GitHub Actions → oppdag FERDIG runde → match
klubb/bane/tee → fyll GolfBox-skjema via Playwright → lagre → varsle (mobil + e-post).

**KJERNE-REGEL:** Garmin synker en runde LIVE mens den spilles (`roundInProgress=True`,
med delvis score). Vi behandler KUN runder der `roundInProgress=False` (du har trykket
«save round» på klokka). Ellers ville vi prøvd å poste en halvspilt runde, feilet, og
aldri postet den ferdige. Filtreres i `auto_sync.garmin_summary_ids()` – pågående runder
markeres ikke som sett, så de plukkes opp automatisk når de er ferdigstilt.

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
- **.github/workflows/auto-sync.yml** — selve jobben. Lås mot dobbel-posting, timeout
  20 min, secrets for alt følsomt. Trigges av cron-job.org (se under), ikke GitHubs
  egen schedule (som er hardt strupt til hver 2.–3. time og bare er en treg reserve).

## Exit-koder (golfbox_post --auto → auto_sync)

- **0** = lagret rent
- **4** = lagret, men tee valgt på skjønn (⚠ dobbeltsjekk)
- **2** = GolfBox-økt utløpt (stopp, prøv igjen senere — ikke marker som sett)
- **3** = klubb OK, men bane/tee ikke bekreftet (kan fullføres i web-appen)
- **5** = klubben finnes ikke i GolfBox (privat/utland → kan ikke leveres)
- **6** = Garmin-data ufullstendig ennå (tee/rating ELLER hull-score/<10 hull) → VENT,
  prøv igjen opp til `MAX_TEE_WAIT`=12 (~60 min), så needs_manual.

`submit_score` returnerer nå tre-tilstand: **"saved"** (skjema lukket + fortsatt innlogget),
**"session"** (skjema lukket men innloggingsside vises = økt utløpt → kode 2, prøv igjen),
**"unsaved"** (skjema åpent ELLER synlig GolfBox-feilboks `.alert-danger` → manuell). Kun
"saved" regnes som postet. Dette lukker «stille tap».

## Kveldens herding (15. juli 2026) — les denne

Mange generelle robusthets-fikser ble lagt til (alle mønster-fikser, verifisert live):
- **Eksakt banenavn-prioritet** i `choose_course` (Garmin «~ Vestmork» → GolfBox «Vestmork»,
  selv om «9»-baner ellers scorer høyere for 9-hullsrunder). Utelukker placeholder-baner.
- **9-hulls rating-dobling** for tee-match (Garmin gir ~halv rating; GolfBox viser 18-hulls CR).
- **Vent på stabil bane-liste** etter klubb-bytte (async-race: unngå feil-klubb-bane).
- **n_holes fra ANTALL SCOREDE HULL** (ikke `holesCompleted`); 9-hull fylles posisjonelt (back-nine).
- **Ufullstendige runder postes UMIDDELBART** (hull-antall er autoritativt, ≥10 hull for 18-runde).
  **VIKTIG PRINSIPP: vi gjetter IKKE GolfBox sine hull-regler — GolfBox er dommer.** Vi forsøker
  å lagre, og den positive verifiseringen fanger evt. avvisning. (GolfBox godtar f.eks. hull 1 +
  baksida, men ikke Haugers spredte mønster – dette klarte vi ikke å gjette riktig, derfor lar vi
  GolfBox avgjøre.) «Ikke alle hull»-popup bekreftes automatisk (JS-dialog).
- **Positiv verifisering mot stille tap (kjernen):** etter «Lagre» sjekkes GolfBox sin røde
  feilboks (`.alert-danger`/`.tblError`) + innloggingsside (økt-utløp). En runde markeres ALDRI
  postet uten faktisk å ligge i GolfBox. `submit_score` → "saved"/"session"(kode 2, prøv igjen)/
  "unsaved"(manual). Kjente GolfBox-feilkoder oversettes til lesbar norsk.
- **Grunn i varsel:** push/mail sier nå HVORFOR («GolfBox avviste: godtar ikke dette hull-mønsteret»,
  «Garmin mangler tee/rating ennå», «kun X av 18 hull», «klubben finnes ikke i GolfBox»).
- **Vent vs. flagg-straks:** kode 6 (VENT) KUN ved EKTE forsinkelser – tee/rating mangler ennå,
  eller 0 score (fortsatt opplasting). Alt annet flagges/forsøkes UMIDDELBART. Prinsipp: si ifra
  straks med riktig årsak; vent kun når data faktisk kan komme.
- **Farge-multisett:** «Red/Red» → «Haga RØD+RØD» (spilte samme løkke to ganger) — multisett,
  ikke sett, så gjentatt farge matcher.
- **Spilletidspunkt:** setter nå BÅDE `#fld_ScoreDate` og `#fld_ScoreTime` fra Garmins start-tid
  omregnet til norsk tid (Europe/Oslo). GolfBox fylte ellers klokkeslettet med en rar standardverdi.
  Dato bruker også norsk tid nå (sen kveldsrunde havner ikke på feil dag pga. UTC).
- **Garmin-backoff** ved 429/token-feil (eskalerende pause + varsel), **inkrementell state-lagring**
  etter hver runde (ingen dobbel-post ved timeout), **placeholder-baner læres/velges aldri**.
- **Trigger:** cron-job.org pinger dispatch hvert 5. min, dagtid 08–22 (se Trigger-seksjon).
- Debug-verktøy: `debug_round.py <id>` (ekte utfylling, poster ikke), `diag_club.py "<klubb>"`,
  env `GOLFBOX_FORCE_SUBMIT=1` + `GOLFBOX_DEBUG_SAVE=1` (dump GolfBox-respons ved lagring).

## Multi-bruker steg 0: config parametrisert (17. juli 2026) — IKKE testet live ennå

Forberedelse før flere brukere (se MULTIUSER_PLAN.md). Oppdaget at `golfbox_post.py`
og `auto_sync.py` allerede kjører via subprocess+env (ikke direkte funksjonskall), så
`golfbox_post.py` trengte nesten ingen endring — det er `auto_sync.py` som holdt
global, import-tidspunkt-config.

- **`auto_sync.py`:** ny `UserConfig`-dataclass + `build_legacy_config()` (bygger
  identisk config fra `.env`/secrets som før) + `_apply_env(cfg)` (speiler cfg inn i
  `os.environ` for varigheten av én brukers kjøring — subprosesser og `notify.py`
  arver riktig verdier automatisk). `main()` er nå `sync_one_user(cfg)`; ny tynn
  `main()` kaller `sync_one_user(build_legacy_config())`. Bonus-fiks: `load_dotenv()`
  kjøres nå FØR config bygges (før ble `.env`-verdier for `GARMINTOKENS`/
  `GOLFBOX_TEE_WAIT_TRIES` aldri lest lokalt — kun ekte env-variabler virket).
- **`golfbox_post.py`/`fetch_garmin.py`:** ny `GOLFBOX_DATA_DIR`-env (default uendret:
  `data/`) styrer `STATE_FILE` (økt/`golfbox_state.json`), `LOG_FILE`,
  `last_reason.txt`, `golfbox_error.txt` og Garmin-rundedata. Uten dette ville to
  brukeres GolfBox-økter kollidert i samme fil i en fremtidig loop. `golfbox_course_map.json`
  (lærte bane-mappinger) er BEVISST fortsatt delt/global — nettverkseffekt, ikke per bruker.
  Designkrav: brukere må behandles STRENGT SEKVENSIELT (aldri parallelt) siden env
  speiles inn i samme prosess.
- **Verifisert i sandkasse (ingen nettverkstilgang der):** `py_compile` alle tre
  filer, `tests/test_logic.py` (32/32 bestått, uendret), og et eget smoke-test som
  bygger både legacy-config og en simulert fremtidig bruker-config og bekrefter
  isolasjon (ulik `data_dir`/creds/tokenstore, delt `COURSE_MAP_FILE` upåvirket).
- **IKKE verifisert:** ekte kjøring (`python3 auto_sync.py` / `test_rounds.py --all`)
  krever nettverk til Garmin/GolfBox/Supabase — må kjøres på Mac-en FØR commit, som
  vanlig (se CLAUDE.md: tørr-test før commit).
- **Neste steg mot multi-bruker:** Supabase-skjema (`users`, `user_round_state`) +
  kryptering + en løkke som bygger én `UserConfig` per aktiv bruker og kaller
  `sync_one_user()` sekvensielt — selve synk-logikken er nå klar for det.

## Kode-review (16. juli 2026)

Gjennomført opprydding (commitet):
- **Enhetstester** i `tests/test_logic.py` (32 stk, ingen nettleser) – kjør `python3
  tests/test_logic.py` FØR hver commit. Dekker norm/folding, farge-multisett, n_holes,
  `_holes_contiguous`, `_holes_postable`, dato/tid, GolfBox-feiltekst, bane-scoring.
- **Stille except-er som skjulte logikk-feil logger nå** (fanget `_pick_reason`-typen).
  De 54 nettleser-I/O-except-ene er bevisst stille (best-effort).
- **Ren beslutnings-logikk trukket ut** til testbare funksjoner (`_holes_contiguous`,
  `_holes_postable`).

Dokumentert GJENSTÅENDE teknisk gjeld (egen fokusert økt, regresjon som port etter hvert uttrekk):
- **`golfbox_post.py` er en ~1850-linjers monolitt.** Bør splittes i moduler
  (matching / skjema-utfylling / submit / sesjon).
- **Gud-funksjoner:** `fill_score_form` (~330 linjer) og `main` (~280) bør dekomponeres
  (`fyll_dato/klubb/bane/hull/markør/tee`). De er lineære/lesbare nå, så dette er lesbarhet,
  ikke korrekthet – lav hast, men viktig før multi-bruker.
- Duplikat: `_color_set` vs `_color_multiset` (behold multisett, `_color_set` er ubrukt nå).

## Hva som er bevist å virke

Live-testet fra klokka 15.07: farge-løkke-baner (Haga Red/Blue m.fl.), fler-bane-klubb (Losby
Ostmork+Vestmork), ny klubb (Groruddalen), 9-hull (Grønmo) — alle traff. Regresjon (`test_rounds.py
--all`, 61 runder): ~48 postes, 0 ekte regresjoner. Resten er «rene» kategorier: baner utenfor
norsk GolfBox (Spania/Oustøen/Nittedal) = «kan ikke leveres», eller teeBox=None = venter på Garmin.
Én kjent grense: en runde med hull-hull *midt inne* (klokka synket ikke alt) avvises av GolfBox og
må legges inn manuelt.

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
- 18-hullsrunder der Garmin mangler score på ett+ hull (du glemte å registrere et hull
  på klokka) kan ikke auto-postes – flagges «fullfør selv» med hvilke hull som mangler.
  Legg inn hullet i Garmin og re-sync, eller fyll det i dashbordet. `n_holes` utledes
  nå fra antall scorede hull (ikke `holesCompleted`), så klassifiseringen 9/18 er robust.
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

## Trigger (hvordan jobben faktisk startes)

GitHubs innebygde `schedule`-cron er hardt strupt på gratis-nivå (fyrer bare hver
2.–3. time), så den alene er ikke nok. Den PÅLITELIGE triggeren er **cron-job.org**:

- En gratis cron-job.org-konto pinger GitHub sitt dispatch-endepunkt hvert **5. min**:
  `POST https://api.github.com/repos/Anviksen/garmin-golfbox/actions/workflows/auto-sync.yml/dispatches`
  med header `Authorization: Bearer <PAT>`, `Accept: application/vnd.github+json`,
  `Content-Type: application/json`, body `{"ref":"main"}`. Suksess = HTTP 204.
- **PAT:** fine-grained GitHub-token med KUN «Actions: Read and write» på denne ene
  repoen (minste privilegium). Har en utløpsdato — **fornyes før den går ut**, ellers
  slutter triggeren å fyre. Sett ny PAT i cron-job.org sin Authorization-header.
- **Feilvarsling er på** i cron-job.org (e-post hvis pingen feiler), så triggeren
  aldri dør stille. Får du slik e-post: sjekk om PAT-en er utløpt.
- Verifisert 13.07.2026: dispatch-kjøringer hvert ~5. min, latens ~5–10 min.
- Ingen runde går tapt selv om triggeren stopper en stund: neste kjøring tar ALLE
  nye runder siden sist. Trigger-svikt = forsinkelse, ikke tap.

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
