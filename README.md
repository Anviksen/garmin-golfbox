# Garmin → Golfbox — Fase 1: Hent golfdata fra Garmin Connect

Dette er første del av prosjektet: å hente all golf scorecard-data (hull-for-hull
og slag-for-slag) fra Garmin Connect og lagre den som JSON på maskinen din.

Alt kjører **lokalt på din egen Mac**. Garmin-passordet ditt forlater aldri
maskinen, og legges aldri inn i noen chat.

---

## Hva du trenger

- En Mac med Python 3 (kommer forhåndsinstallert; sjekk med `python3 --version`).
- Garmin Connect-konto (samme innlogging som i Garmin Connect-appen).
- At rundene fra din **Approach S50** er synkronisert til Garmin Connect-appen.

---

## Steg-for-steg

Åpne **Terminal** (finnes i Programmer → Verktøy) og kjør kommandoene under, én
linje av gangen.

### 1. Gå inn i prosjektmappa

```bash
cd ~/Documents/garmin-golfbox
```

### 2. Lag et isolert Python-miljø og installer bibliotekene

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Etter dette ser du `(.venv)` foran linja i Terminal. Det betyr at miljøet er aktivt.

### 3. Legg inn Garmin-innloggingen din

Lag en `.env`-fil ved å kopiere malen:

```bash
cp .env.example .env
```

Åpne så `.env` (f.eks. `open -e .env`) og fyll inn din e-post og passord:

```
GARMIN_EMAIL=din.epost@example.com
GARMIN_PASSWORD=ditt-garmin-passord
```

Denne fila ligger i `.gitignore` og deles aldri.

### 4. Kjør henteprogrammet

```bash
python3 fetch_garmin.py
```

- Første gang logger det inn med e-post/passord. Har du **tofaktor (MFA)** på,
  blir du bedt om å skrive inn engangskoden.
- Etterpå lagres en innloggings-token lokalt (`~/.garminconnect`), så senere
  kjøringer går automatisk uten passord.
- Programmet henter oversikt over alle runder, og deretter hull-for-hull og
  slag-for-slag data for hver runde.

### 5. Bekreft at dataen ser riktig ut

```bash
python3 inspect_data.py
```

Dette skriver ut en liste over rundene dine og et hull-for-hull-eksempel, slik at
du kan sjekke at Approach S50-dataen kom korrekt gjennom.

---

## Hvor havner dataen

Alt lagres i mappa `data/`:

| Fil / mappe                | Innhold                                        |
|----------------------------|------------------------------------------------|
| `data/summary.json`        | Rå oversikt over alle runder                   |
| `data/scorecards/<id>.json`| Hull-for-hull detaljer (par, slag, putts) per runde |
| `data/shots/<id>.json`     | Slag-for-slag data per runde                   |
| `data/all_rounds.json`     | Alt samlet i én fil (brukes videre i Fase 2)   |

---

## Neste gang du vil hente nye runder

```bash
cd ~/Documents/garmin-golfbox
source .venv/bin/activate
python3 fetch_garmin.py
```

---

## Feilsøking

- **`command not found: python3`** — installer Python fra https://www.python.org/downloads/
- **Innlogging feiler / MFA** — sjekk e-post og passord i `.env`. Ved gjentatte
  feil, slett mappa `~/.garminconnect` og prøv på nytt.
- **"Ingen runder funnet"** — åpne Garmin Connect-appen på telefonen og sørg for
  at S50-rundene er synkronisert til Garmin Connect først.
- **`externally-managed-environment` ved pip** — sørg for at du kjørte
  `source .venv/bin/activate` (punkt 2) før `pip install`.

---

---

## Fase 2 – Golf-dashboard (webapp)

Et lokalt dashboard (FastAPI-backend + React-frontend) som viser alle rundene
dine, hull-for-hull scorecard, og trend over tid. Har også en «Sync fra Garmin»-
knapp som henter nye runder.

### Start dashboardet

Sørg for at venv er aktiv og at avhengighetene er installert:

```bash
cd ~/Documents/garmin-golfbox
source .venv/bin/activate
pip install -r requirements.txt
```

Start så serveren – enkleste vei:

```bash
./start_dashboard.sh
```

(Første gang må du kanskje gjøre den kjørbar: `chmod +x start_dashboard.sh`.)

Eller start manuelt:

```bash
uvicorn backend.main:app --port 8000
```

Åpne så **http://localhost:8000** i nettleseren. Stopp serveren med **Ctrl-C**.

### Hva du får se

- **Oversikt:** nøkkeltall (antall runder, snitt mot par, beste runde, fairway%)
  og en trendgraf over score mot par.
- **Runder:** liste sortert nyeste først – klikk en runde for å se hele
  scorecardet hull for hull, med par, slag (fargekodet) og fairway-treff.
- **Sync fra Garmin:** henter nye runder rett fra dashboardet.

> Merk: putts og slag-for-slag vises ikke, fordi Approach S50 ikke registrerer
> dette. Alt annet (score, par, fairway) er med.

---

---

## Fase 3 – Auto-posting til Golfbox

Mål: én knapp som sender en runde til Golfbox, med forhåndsvisning og bekreftelse.

### Steg 1 – Kartlegg score-skjemaet (nå)

Installer Playwright (nettleser-automatisering) én gang:

```bash
cd ~/Documents/garmin-golfbox
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Kjør så kartleggings-scriptet:

```bash
python3 golfbox_map.py
```

Det åpner en nettleser. Logg inn i Golfbox, gå til **«Min GolfBox» → «Innlever
score»**, og få frem selve scorekort-skjemaet (kryss gjerne av «Tast inn
hullscorer»). Kom tilbake til Terminal og trykk **ENTER** – scriptet lagrer hele
skjemaet (inkl. iframes) i `data/golfbox_map/`.

### Steg 2 – Send en runde til Golfbox

I dashboardet har hver runde nå en **⛳-knapp** (og en «⛳ Send til Golfbox»-knapp
når du åpner en runde). Når du trykker:

1. En ekte nettleser åpnes på maskinen din og går til Golfbox «Innlever score».
2. **Første gang** logger du inn manuelt i vinduet. Økten lagres i en egen profil
   (`data/golfbox_profile/`), så senere er du allerede innlogget.
3. Scriptet fyller inn dato, rundetype, 9/18 hull, bane/tee (beste treff) og alle
   hull-scorer automatisk.
4. Det **stopper** og lar vinduet stå åpent. Du sjekker at bane/tee stemmer, legger
   til **markør**, og trykker **«Lagre»** i Golfbox selv.

> Ingenting sendes inn automatisk – du bekrefter alltid selv. En handicaptellende
> runde krever markør; sett gjerne en standard-markør i `.env`
> (`GOLFBOX_MARKER_MEMBERNO` eller `GOLFBOX_MARKER_NAME`).

Du kan også kjøre det direkte fra Terminal:

```bash
python3 golfbox_post.py <runde-id>
```

Bane- og tee-navn kan avvike mellom Garmin og Golfbox, så sjekk alltid disse to før
du lagrer.

### Navne-mapping for baner som ikke matcher

De fleste norske klubber matches automatisk. For baner der Garmin-navnet ikke finnes
i GolfBox (f.eks. «Aas Gård Golfpark»), kan du legge inn en manuell mapping i
`golfbox_course_map.json`:

```json
{
  "Aas Gård Golfpark": { "club": "Ås Gård Golfklubb", "course": "18-hull", "tee": "57" }
}
```

Nøkkelen er Garmin-banenavnet (slik det står i runde-listen), og du fyller inn
klubb/bane/tee nøyaktig slik GolfBox skriver det. Tomme felt hoppes over. Utenlandske
baner registreres via GolfBox sin egen «utenlandsk bane»-flyt og dekkes ikke her.
