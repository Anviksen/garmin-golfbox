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
