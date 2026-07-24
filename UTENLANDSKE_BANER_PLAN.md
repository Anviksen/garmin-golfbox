# Utenlandske baner — kickoff / plan

_Opprettet 20. juli 2026. **Status 23. juli 2026: prototype implementert i
kode, IKKE live-testet ennå** (sandkassen har ikke nettverk til GolfBox). Se
«Implementert 23. juli 2026»-seksjonen nederst for nøyaktig hva som er gjort
og hva som gjenstår før dette kan kobles til automatikken._

Startdokument for et NYTT delprosjekt: la runder spilt på baner UTENFOR Norge
postes til GolfBox, via GolfBox sitt eget frittekst-skjema for
utenlandsrunder (helt annerledes enn dagens katalog-matching mot norske
klubber).

> **Til en ny chat:** Les FØRST `STATUS.md` (arkitektur, hva som virker,
> exit-koder, drift), deretter `CLAUDE.md` (arbeidsprinsipper), deretter
> DENNE fila (les seksjonen «Implementert 23. juli 2026» FØRST – resten av
> fila under er research-notater fra FØR implementasjonen og er delvis
> utdatert, f.eks. antok den at Land måtte GPS-geokodes, noe som viste seg
> unødvendig). `MULTIUSER_PLAN.md` er også nyttig bakgrunn (samme mønster:
> generaliser en person-spesifikk løsning), men ikke strengt nødvendig for
> å starte dette konkrete delprosjektet.

## Mål

I dag: en runde på en bane utenfor Norge (Spania, andre land) ender alltid som
«klubben finnes ikke i GolfBox – kan ikke leveres» (exit-kode 5), fordi
matchingen kun kjenner de 176 norske klubbene i `golfbox_catalog_no.json`.
Målet er en EGEN fyll-ut-strategi for GolfBox sitt utenlandsskjema, som bruker
frittekst i stedet for nedtrekksmatching mot en katalog.

## Det som allerede finnes (bygg på dette)

- `golfbox_post.py` sin eksisterende motor for innlogging, navigasjon til
  score-skjemaet, verifisering mot stille tap (`submit_score`), og
  telemetri-logging – gjenbrukes, kun selve FYLL-UT-DELEN for utenlandske
  runder blir ny kode.
- Garmin-data vi allerede henter per runde (brukes i dag til norsk
  tee-matching, men samme felt finnes trolig for utenlandske runder også –
  Garmin har 41 000+ baner globalt):
  - `courseName` – banenavn
  - `holePars` / par-sekvens – banens par, per hull
  - `teeBoxRating`, `teeBoxSlope` – Baneverdi (CR) og Slopeverdi
  - `teeBox` – Utslagssted (etikett/farge)
  - Hull-for-hull score – har vi allerede, kjernen som fungerer i dag
  - GPS-koordinater (courseSnapshots lat/lon) – kan brukes til land-deteksjon
- Ekte test-runder å utforske MED (Håkons egen historikk, spanske baner som i
  dag er «kan ikke leveres» – bruk `debug_round.py <id>` på disse for å se
  nøyaktig hva Garmin faktisk gir oss):
  - Santa Clara Golf Club Marbella — ID `356502765`
  - Marbella Golf y Country Club — ID `356502741`
  - Los Arqueros Golf — ID `356502726`
  - Calanova Golf Club — ID `356502717`
  - El Chaparral Golf Club — ID `355675553`
  - Alhaurin Golf — ID `355547598`
- Multi-bruker-infrastrukturen (se `MULTIUSER_PLAN.md`) er ferdig og
  produksjonstestet – dette er ortogonalt, ikke noe som må vente på dette
  delprosjektet.

## Feltene i GolfBox sitt utenlandsskjema (fra brukerens beskrivelse)

| GolfBox-felt         | Type        | Sannsynlig Garmin-kilde                  |
|----------------------|-------------|-------------------------------------------|
| Land                 | fritekst    | Ikke fanget i dag – løs via Garmin-data ELLER GPS-basert geokoding (samme mønster som klubbmatching) |
| PCC                  | dropdown 0–+3 | **INGEN** – skjønnsspørsmål om værforhold/banetilstand DEN dagen, se forbehold under |
| Bane                 | fritekst    | `courseName` |
| Utslagssted           | fritekst    | `teeBox` |
| Banens Par           | fritekst    | `holePars` / par-sekvens |
| Baneverdi (CR)       | fritekst    | `teeBoxRating` |
| Slopeverdi           | fritekst    | `teeBoxSlope` |
| Score per hull       | -           | har vi allerede |

## Det store forbeholdet: PCC

PCC kan IKKE utledes fra Garmin-data – det er et menneskelig skjønnsspørsmål
om forholdene den dagen, normalt satt av klubben/spilleren selv. **Anbefaling:
denne velges ALDRI automatisk.** Enten la den alltid stå på 0 og flagg for
manuell dobbeltsjekk (samme mønster som best-effort-tee i dag, ⚠), eller la
feltet alltid kreve en menneskelig bekreftelse før lagring. Dette er i tråd
med sikkerhetsnett-prinsippet i `CLAUDE.md`: aldri poste feil data, heller
flagge.

## Åpne spørsmål å avklare FØRST i den nye chatten

1. **Nøyaktig skjemastruktur i GolfBox** (feltnavn/ID-er for utenlandsskjemaet)
   er IKKE utforsket i kode ennå – krever live inspeksjon, trolig med samme
   type verktøy som `diag_club.py`/`inspect_course_form` bruker for norske
   baner, eller manuell nettleser-inspeksjon først.
2. **Hvor pålitelig er Garmins rating/slope/par-data for utenlandske baner
   faktisk?** Sjekk de 6 kjente Spania-rundene over med `debug_round.py` FØR
   noe kode skrives – det avgjør hvor mye som kan automatiseres.
3. **Hvordan detekteres «dette er en utenlandsk runde»?** Sannsynligvis:
   klubb/bane finnes ikke i `golfbox_catalog_no.json` OG koordinatene faller
   utenfor Norge – men verdt å tenke gjennom som et generelt mønster, ikke en
   spesialsjekk for Spania.
4. PCC: bekreftet over – alltid manuell/flagget, aldri automatisk.
5. Skal dette bygges/testes mot enkelt-bruker-flyten først (som norsk
   bane-matching opprinnelig ble bevist), eller rett inn i multi-bruker-
   pipelinen? Anbefaling: bevis konseptet enkelt/lokalt først (samme
   fremgangsmåte som hele prosjektet har fulgt hele veien), koble til
   multi-bruker etterpå – det er allerede generisk nok til å ta imot det.

## Fase-plan (forslag)

1. **Research:** kjør `debug_round.py` på de 6 kjente Spania-rundene, se
   nøyaktig hva Garmin gir. Inspiser GolfBox sitt utenlandsskjema live (felt-
   ID-er).
2. **Prototype:** én ny funksjon i `golfbox_post.py` (f.eks.
   `fill_foreign_score_form`) som fyller ut frittekst-feltene, PCC alltid
   flagget. Test med `GOLFBOX_AUTO_SUBMIT=0` (fyll, ikke lagre) først, som
   alltid.
3. **Bevis på én ekte runde** (en av de 6 Spania-rundene, eller en ny), med
   ekte lagring, før det generaliseres videre.
4. **Koble til automatikk** (enkelt-bruker og/eller multi-bruker) når bevist.

## Implementert 23. juli 2026 (fase 1+2 av fase-planen over)

**Fase 1 (research) er ferdig.** Live-inspeksjon av GolfBox sitt
utenlandsskjema (`newWHSScore.asp`, via nettleser med ekte innlogging) +
gjennomgang av cachet Garmin-rådata for alle 6 kjente Spania-runder
(`data/scorecards/*.json`) ga svar på ALLE åpne spørsmål over:

- **Land trenger IKKE GPS-geokoding.** Garmin gir det direkte:
  `courseSnapshots[0].country` (f.eks. `"Spain"`, `"Norway"`) – bekreftet på
  alle 6 Spania-runder OG en norsk kontroll-runde.
- **HCP (stroke index) per hull finnes også ferdig hos Garmin:**
  `courseSnapshots[0].tees[].holeHandicaps`, samme 2-sifre-per-hull-format
  som `courseHandicapStr` (f.eks. `"141812081006040216010503090717111513"`).
  Bekreftet at det dekoder til en korrekt permutasjon av 1–18 på ekte data.
- **GolfBox sitt skjema bruker samme `fld_*`-feltkonvensjon** som
  `golfbox_post.py` allerede automatiserer for norske runder – ikke et
  fremmed system. Eksakt feltkart (lest ut av DOM-en live):

  | Felt | GolfBox-ID | Garmin-kilde |
  |---|---|---|
  | «Banen finnes ikke i GolfBox!» | `chk_UnknownCourse` (checkbox) | – |
  | Land | `fld_ManualCountryName` (fritekst) | `country` |
  | PCC | `fld_PCC` (dropdown -1..+3) | ALDRI automatisk – alltid `"0"` |
  | Bane | `fld_ManualCourseName` (fritekst) | `course`/`courseName` |
  | Utslagssted | `fld_ManualTee` (fritekst) | `teeBox` |
  | Banens Par | `fld_CoursePar` (fritekst) | `roundPar` |
  | Baneverdi (CR) | `fld_CourseRating` (fritekst, samme ID som norsk flyt) | `teeBoxRating` |
  | Slopeverdi | `fld_Slope` (fritekst, samme ID som norsk flyt) | `teeBoxSlope` |
  | Par per hull | `Par-1`…`Par-18` (1-indeksert) | `holePars`-strengen |
  | HCP per hull | `HCP-1`…`HCP-18` | `holeHandicaps`-strengen |
  | Slag per hull | `Strokes-1`…`Strokes-18` | `holes[].strokes` (som i dag) |
  | «SH» (spillehandicap) | `fld_TextPHCP` – GolfBox regner selv ut, rør ikke | – |

  Ubekreftet detalj (avklares i live dry-run, se «Gjenstår» under):
  om `chk_InputHoleScores` må hukes av for at Par/HCP/Strokes-feltene skal
  vises, eller om de allerede er synlige når `chk_UnknownCourse` er på.

**Fase 2 (prototype) er ferdig – kode skrevet, IKKE live-testet.** Endringer:

- **`backend/main.py`:** ny `parse_hole_handicaps()` (speiler `parse_pars()`,
  men 2 sifre per hull). `normalize_round()` eksponerer nå `country`,
  `roundPar`, og et `hcp`-felt per hull (matchet på samme tee som spilt).
  Verifisert med ekte utregning mot alle 6 cachede Spania-runder + en norsk
  runde (se test under) – ingen endring i eksisterende felter/oppførsel.
- **`golfbox_post.py`:**
  - `_is_foreign_round(rnd)` – `country` fra Garmin != Norge/Norway. Mangler
    `country` (gammel cachet data), regnes runden som norsk
    (bakoverkompatibelt – null risiko for regresjon på de 176 norske
    klubbene som virker i dag).
  - `_fill_marker()` trukket ut som egen delt funksjon (ren flytting av
    eksisterende, velprøvd kode – ingen logikkendring) så begge skjema-
    varianter kan bruke den identisk.
  - Ny `fill_foreign_score_form()` – huker av `chk_UnknownCourse`, fyller
    Land/PCC/Bane/Utslagssted/Par/CR/Slope + Par-N/HCP-N/Strokes-N per hull.
    Fyller ALDRI et felt den ikke har ekte data for (flagger i stedet, jf.
    sikkerhetsnett-prinsippet i `CLAUDE.md`). PCC er alltid `"0"` og alltid
    flagget «⚠️ DOBBELTSJEKK».
  - `main()` velger nå `fill_foreign_score_form` vs. `fill_score_form` basert
    på `_is_foreign_round(rnd)`, med egen exit-kode-gren for utenlandske
    runder: postet → ALLTID kode 4 (PCC må dobbeltsjekkes, aldri kode 0),
    ufullstendig baneinfo/hull → kode 3 (fullfør selv) eller 6 (Garmin
    synker fortsatt) – kode 5 («klubb finnes ikke») brukes aldri i denne
    grenen, siden det ikke finnes noen klubb-katalog å bomme på.
  - `debug_round.py` oppdatert til å auto-detektere utenlandske runder og
    kalle riktig fyll-funksjon (samme dry-run-prinsipp som før: fyller,
    lagrer ALDRI).
- **`tests/test_logic.py`:** 14 nye enhetstester (landdeteksjon +
  HCP-dekoding, verifisert mot ekte Garmin-tall fra Santa Clara Golf Club
  Marbella). **46/46 bestått i sandkasse (0 nettverk nødvendig), 0
  regresjoner** på de 32 eksisterende testene.

### Skalerings-beslutning (24. juli 2026): tenk «mange brukere», ikke «denne runden»

Etter funn 2/3 stoppet vi opp: ambisjonen er ikke bare at Håkons egne runder
postes riktig, men et verktøy MANGE kan bruke – på sikt kanskje kommersielt,
og ideelt godkjent av Garmin/GolfBox/forbund. Det endrer hva «riktig løsning»
betyr: manuelt oppslag per runde (som løste Torreby-testen) skalerer ikke,
og enkeltrunde-flagging er ikke nok alene når føringen faktisk teller på ekte
WHS-handicap for andre folk.

Bygget derfor to ting, samme kveld:

1. **Automatiske sunnhetssjekker** (`_valid_hcp_set`, `_plausible_cr_slope` i
   `golfbox_post.py`) – helt automatisk, ingen manuelt oppslag. Fanger IKKE
   subtile avvik (som Torreby CR/Slope-saken), men fanger korrupt/umulig data
   (duplikat stroke index, Slope utenfor 55-155 osv.) og blokkerer
   auto-lagring for akkurat den runden i så fall (`course_info=False`).
2. **Delt, verifisert stroke-index-cache** (`foreign_course_registry.py`,
   speiler `course_matcher.py` sitt lærings-mønster for norske baner). Første
   gang NOEN bekrefter riktig Hcp-rekkefølge for en bane mot en troverdig
   kilde, lagres den i `foreign_hcp_db.json` (git-delt) OG i sentralbasen
   (`foreign_course_hcp`-tabell, se `supabase_foreign_hcp_schema.sql` – må
   kjøres én gang i Supabase SQL Editor, samme rutine som
   `supabase_multiuser_schema.sql`). Deretter er banen «kjent god» for ALLE
   fremtidige brukere, helt automatisk, ingen ny sjekk nødvendig. Hills og
   Torreby er allerede registrert (verifisert mot caddee.se i dag).
   `sync_registry.py` synker nå også denne tabellen ned lokalt, samme rutine
   som klubb/bane/tee-basen.

**Fortsatt åpent:** de 6 spanske rundene er ALDRI kryssjekket mot en ekte
kilde (kun sjekket at tallene er en gyldig permutasjon – samme svake sjekk
som nesten lurte oss på Hills). De er derfor fortsatt kun «Garmin
best-effort, sunnhetssjekket, ikke verifisert» – posted automatisk hvis de
består sunnhetssjekkene, men uten den sterke tilliten Hills/Torreby nå har.
Naturlig oppfølging: finn en spansk ekvivalent til caddee.se og verifiser
dem på samme måte.

**Om offisiell godkjenning fra Garmin/GolfBox/forbund:** det er en
forretnings-/avtale-vei (trolig til slutt en offisiell API-integrasjon i
stedet for browser-automatisering), ikke noe flere kodefikser løser alene –
egen, bevisst beslutning senere, se samtalen 24. juli 2026.

### Live-test funn 3 (24. juli 2026): CR/Slope kan avvike litt – akseptert, flagget

Torreby «Gul»-tee: Garmin ga CR 69,7/slope 131, klubbens egen side viste
69,5/129, og to tredjepartskilder ga enda to andre tall. Ikke en systematisk
Garmin-feil (som Hcp-alarmen), men vanlig drift – CR/Slope resertifiseres
periodisk, ulike kilder har ulik snapshot-alder (Garmins banedatabase her:
november 2025). Dette ER faktisk en KJENT, allerede dokumentert begrensning
i prosjektet (`CLAUDE.md`: «Garmin-ratinger er utdaterte»), men den biter
annerledes her: for NORSKE runder skriver vi aldri Garmins rating til
GolfBox (GolfBox har egen lagret CR/Slope per tee) – for UTENLANDSKE runder
ER Garmin eneste kilde, så avviket postes faktisk.

**Beslutning (brukerens eksplisitte krav): alt skal fylles inn automatisk,
ingen manuelt oppslag per runde** – ellers mister automatiseringen poenget.
Løsning: behold Garmin som kilde (som før, ingen endring i hvilke tall som
postes), men legg til en INFO-note i `fill_foreign_score_form()` (ikke en
blokkerende ⚠️, siden avviket er lite og forventet) som minner om at CR/Slope
kan avvike noe – samme mønster som PCC, bare mildere alvorlighetsgrad siden
feilmarginen er liten og godt forstått.

### Live-test funn 2 – OPPKLART 24. juli 2026: falsk alarm, Garmin hadde rett

**Oppdatering samme dag:** Krysset Hcp-per-hull mot Caddee.se (svensk
golf-app koblet til det offisielle svenske handicapsystemet MinGolf) for
BÅDE Hills og Torreby:

- **Torreby:** Garmins `tees[].holeHandicaps` stemte 100 % mot Caddee, alle
  18 hull, PAR òg 100 %.
- **Hills:** Garmins `tees[].holeHandicaps` stemte OGSÅ 100 % mot Caddee,
  alle 18 hull, PAR òg 100 %.

Konklusjon: alarmen under (funn 2, opprinnelig) var en falsk alarm. Kortet vi
sammenlignet mot på Hills sin egen nettside var trolig UTDATERT – Caddee sin
hullbeskrivelse for Hills nevner eksplisitt at banen ble bygget om («Nya hål
nio», «Gamla hål 13 har förlångts», «nytt for 2013»), som forklarer hvorfor
et gammelt scorekort-bilde på klubbens nettside kan vise en annen
hull-rekkefølge enn det som faktisk gjelder i dag. Garmins
`tees[].holeHandicaps`-felt (feltet koden vår faktisk bruker) er nå
kryssjekket riktig på 2 av 2 svenske baner mot en troverdig, MinGolf-koblet
kilde – i tillegg til Par som har stemt på alle 8 baner testet så langt
(6 spanske + 2 svenske). **`_fill_and_settle` osv. i koden endres IKKE** –
ingen kodeendring var nødvendig, kun en feilslutning i den manuelle
sammenligningen som ble oppklart. Anbefaling: fortsett som planlagt,
fortsatt sunn skepsis + visuell sjekk før «Lagre» (som alltid), men ingen
egen «lær opp stroke index per bane»-mekanisme er nødvendig på nåværende
bevisgrunnlag.

### Live-test funn 2 (24. juli 2026, opprinnelig – SE OPPKLARING RETT OVER) – historikk, ikke lenger gjeldende

Testet Hills Golfklubb (Sverige, runde 373781049). Par og CR/Slope stemte
perfekt mot Hills sin egen offisielle scorekort-side. MEN: **stroke index
(Hcp) per hull fra Garmin (`tees[].holeHandicaps`) stemmer IKKE med Hills sitt
offisielle scorekort.** Garmin gir riktig SETT tall (odde 1-17 på front ni,
like 2-18 på bak ni – samme struktur som ekte kort), men fordelt på FEIL hull
– en annen permutasjon enn den klubben faktisk bruker. Eksempel: hull 13 har
offisiell stroke index 16, Garmin ga 18. Det er ikke bare kosmetisk: siden SH
og Jst. score (net-double-bogey-kappet score, brukes i selve
handicap-utregningen) regnes ut av GolfBox FRA stroke index-feltet vi selv
fylte inn, endret feilen faktisk Jst. score-verdien på hull 13 i live-testen
(GolfBox viste Jst.=5 med vår feil-hcp=18; riktig hcp=16 ville trolig gitt
Jst.=6). Dette er nøyaktig den typen feil CLAUDE.md prinsipp 2 advarer mot
("post aldri feil data – flagg heller").

**IKKE bekreftet ennå:** om dette er unikt for Hills, eller om de 6
Spania-rundene (inkl. den allerede LAGREDE Santa Clara-runden) har samme
problem – vi verifiserte den gang kun at Garmin-tallene var en gyldig
permutasjon av 1–18, ALDRI at rekkefølgen faktisk stemte mot banens ekte
scorekort. Det var en svakhet i den opprinnelige verifiseringen.

**Konsekvens: IKKE lagre flere utenlandske runder (inkl. Hills) før dette er
løst.** Par/CR/Slope/Bane/Land/Utslagssted/Slag er fortsatt vist pålitelige
på tvers av 7 testede baner – det er SPESIFIKT stroke-index-feltet fra
Garmin som ikke kan stoles på uten videre. Løsningsretning å vurdere: slutt å
autofylle Hcp-per-hull fra Garmin (samme prinsipp som PCC – ikke gjett), la
feltet stå tomt/flagget for manuell utfylling fra spillerens/klubbens eget
scorekort, ELLER finn en mer pålitelig kilde. Krever avklaring av hvordan
GolfBox oppfører seg når Hcp-per-hull står tomt (feiler lagring, eller
aksepteres score uten net-double-bogey-kapping?) – ikke undersøkt ennå.

### Live-test funn 1 (23. juli 2026) – fikset

Ekte lagring på Santa Clara-runden (356502765) gikk gjennom og alle 18 hull
landet riktig, MEN to avledede GolfBox-felt ble stående feil:

- **«SH» (spillehandicap)** ble ikke regnet ut – sto tomt.
- **«Just. score» per hull** viste `NaN` på alle hull.

Årsak: GolfBox sine gamle ASP-skjemaer regner ut disse avledede feltene med
egne JS-handlere bundet til `input`/`keyup`/`blur`-hendelser. `fr.fill()`
alene i Playwright endrer verdien i DOM-en, men trigger ikke nødvendigvis
disse handlerne – manuell utfylling (ekte tastatur + fokus-bytte) gjør det
naturlig, derfor virket det når brukeren fylte inn selv. **Fiks:** ny
`_fill_and_settle()`-hjelper som fyller OG fyrer av
`input`+`keyup`+`change`+ekte `.blur()` for hvert felt (Land/Bane/
Utslagssted/Par/CR/Slope og Par-N/HCP-N/Strokes-N per hull), som etterligner
en ekte bruker sin sekvens. IKKE live-testet på nytt ennå.

### BEVIST live 23. juli 2026 ✅

Ekte lagring av runde 356502765 (Santa Clara Golf Club Marbella) gjennomført
og bekreftet av brukeren – riktig baneinfo, 18/18 hull, SH og Just. score
regnet ut korrekt (etter event-fiksen over), ingen feilboks. Fase 3 i
fase-planen er dermed fullført.

### Fase 4 (koble til automatikk) – VISER SEG Å VÆRE GJORT ALLEREDE

`auto_sync.py` er 100 % exit-kode-drevet og aner ikke om en runde er norsk
eller utenlandsk – den kaller bare `golfbox_post.py <id> --auto` og tolker
kodene 0/2/3/4/5/6 likt uansett. Siden `fill_foreign_score_form()` bruker
akkurat samme kodeskjema (postet → alltid 4, aldri 0, pga. PCC), og
`.github/workflows/auto-sync.yml` allerede kjører med `GOLFBOX_AUTO_SUBMIT:
"1"`, trengs det **ingen kodeendring i det hele tatt** for å slå dette på i
skyen. Neste gang cron-job.org trigger jobben og en NY runde med
`country != Norge` dukker opp, blir den automatisk postet og flagget for
PCC-dobbeltsjekk via samme push/e-post-varsling som tee-usikkerhet bruker i
dag.

**Én praktisk nyanse:** de 6 kjente Spania-rundene (355547598, 355675553,
356502717, 356502726, 356502741, 356502765) står allerede i
`data/posted.json` sin `"seen"`-liste fra tidligere forsøk (den gang de ga
kode 5 «kan ikke leveres»). `auto_sync.py` behandler aldri en runde som
allerede er `"seen"` på nytt – skyjobben vil derfor IKKE plukke opp disse 6
historiske rundene automatisk, kun NYE utenlandske runder fra nå av. For å
få postet de 6 gamle rundene også: kjør dem manuelt én og én, samme oppskrift
som allerede bevist:

```
GOLFBOX_HEADLESS=0 python3 golfbox_post.py <id>
```

(fyll ut, sjekk visuelt, trykk Lagre selv) – eller, når du stoler på flyten
etter den første, den raskere helautomatiske varianten:

```
GOLFBOX_HEADLESS=1 GOLFBOX_AUTO=1 GOLFBOX_AUTO_SUBMIT=1 python3 golfbox_post.py <id>
```

356502765 er allerede unnagjort (bevist over).
