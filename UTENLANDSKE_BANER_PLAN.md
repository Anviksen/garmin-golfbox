# Utenlandske baner — kickoff / plan

_Opprettet 20. juli 2026. Startdokument for et NYTT delprosjekt: la runder
spilt på baner UTENFOR Norge postes til GolfBox, via GolfBox sitt eget
frittekst-skjema for utenlandsrunder (helt annerledes enn dagens
katalog-matching mot norske klubber)._

> **Til en ny chat:** Les FØRST `STATUS.md` (arkitektur, hva som virker,
> exit-koder, drift), deretter `CLAUDE.md` (arbeidsprinsipper), deretter
> DENNE fila. `MULTIUSER_PLAN.md` er også nyttig bakgrunn (samme mønster:
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
