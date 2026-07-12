# Status og plan videre – Garmin → Golfbox

Sist oppdatert etter at bane-matcheren (koordinat + katalog + læring) var bevist.

---

## ✅ LØST: riktig bane uten forhåndsspilling (par/navn-matching)

Systemet velger nå riktig GolfBox-bane for en helt ny bane, første gang:
GPS → klubb, navn/hull-scoring (utelukker kort-/dame-/tour-baner) → bane, tee fra
Garmin-runden. Banevalget re-asserteres til det fester (GolfBox sin async
`GetCourses`-ombygging nullstiller ellers til standardbanen). Par-matching er
autoritativ ved tvil, og læringen sperrer mot baner som ikke matcher runden.
Bevist på Østmarka (18-hull, tee 47) og pushet.

Små rester (valgfritt): slett testdubletter av Østmarka i GolfBox «Til godkjennelse»,
og slett raden «Narvesen Tour - Damer - 39» i Supabase-tabellen `courses`.

---

## ⏳ Tidligere åpne oppgaver

**1. Fullfør bane-valg-forbedringen (kodet lokalt, IKKE testet/pushet ennå).**
   Vi gjorde bane-utvelgingen hull-antall-bevisst i `golfbox_post.py`
   (funksjonen `choose_course`): matcher ikke banenavnet, og klubben har flere
   baner, velger den nå banen som matcher antall spilte hull (18/9). Gjelder ALLE
   klubber, ikke bare Østmarka.
   - Test lokalt (synlig, lagrer ikke):
     ```
     python3 fetch_garmin.py
     GOLFBOX_AUTO_SUBMIT=0 python3 golfbox_post.py 371938926
     ```
     Se på «Bane:»-linja. «valgt (18 hull)» = løst. «❗ Fant ikke … Baner: [ … ]»
     = lim inn banenavnene, så finjusterer vi (navnene mangler kanskje hull-tall).
   - Når testen er god: `git add -A && git commit -m "Hull-bevisst banevalg" && git pull --rebase && git push`

**2. Østmarka-runden (371938926) ligger som «needs_manual» i skyen.**
   Den ble funnet og fylt ut, men holdt igjen av sikkerhetsnettet (banen matchet
   ikke). Etter fiks #1 (eller fyll den én gang via web-appen «Send til Golfbox»
   → velg riktig Østmarka-bane → Lagre). Da læres banen og deles til sentralbasen.

**3. (Kvalitet, lav prioritet) Katalog-databug.** `golfbox_catalog_no.json` har
   feil banenavn for de siste klubbene (Vrådal/Østmarka/Ålesund viser «Vrådal
   Golf») – katalog-byggeren rakk ikke å laste banene på nytt før den leste dem.
   Påvirker IKKE matchingen (koordinat-matcher bruker kun klubb-nivå). Fiks ved
   behov: legg inn en `wait_for` på at #fld_Course endrer seg etter klubb-bytte i
   `build_golfbox_catalog.py`, og kjør den på nytt.

**4. (Kosmetisk) Node 20-advarsel** i GitHub Actions – ufarlig. Kan fjernes senere
   ved å oppdatere `actions/checkout` og `actions/setup-python`.

---

## 🚀 UTRULLET I SKYEN (fullt automatisk)

Kjører på GitHub Actions hvert 10. min (07–23 norsk tid), uavhengig av Macen:
Garmin → matcher bane mot sentralbasen → logger inn på Golfbox SELV
(fornyer økten automatisk via GOLFBOX_USERNAME/PASSWORD om den er utløpt) →
fyller ut + setter markør → lagrer til godkjenning. Du godkjenner på mobilen.

- Repo: github.com/Anviksen/garmin-golfbox (privat drift via secrets)
- 7 secrets satt: GARMIN_TOKENS_B64, GOLFBOX_STATE_B64, GOLFBOX_MARKER_MEMBERNO,
  GOLFBOX_USERNAME, GOLFBOX_PASSWORD, SUPABASE_URL, SUPABASE_ANON_KEY
- Selvhelbredende innlogging bevist ende-til-ende («✅ LAGRET i Golfbox»).
- Manuell kjøring: `gh workflow run auto-sync.yml` · følg: `gh run watch`

---

## ✅ Hva som er ferdig og bevist

**Kjernen (Garmin → Golfbox, helautomatisk):**
- Henter alle runder fra Garmin med hull-for-hull data.
- Dashboard: runder, scorekort, trend, handicap-estimat, kart, scoring-DNA,
  fairway-dispersjon, hull-heatmap, «skjul runde», «Send til Golfbox».
- «Send til Golfbox» fyller klubb, bane, tee, dato, alle hull **og markør**, og kan
  auto-lagre til «Til godkjennelse» (bevist ende-til-ende, exit-kode 0 = lagret).
- Auto-sync til skyen (GitHub Actions + cron-job.org) – klart, ikke deployet ennå.

**Bane-matching (produktkjernen) – bevist:**
- 3 lag: 1) manuell mapping 2) LÆRT GPS (presis, fra faktisk spill)
  3) katalog med OSM-koordinater 4) fuzzy navn.
- Selv-lærende: retter du en bane manuelt én gang, huskes den (navn + GPS) for alltid.
- Test: Oppegård → katalog (132 m) ✓, Mørk → lært (2 m) ✓, Oslo sentrum → ingen ✓.

**Datasettet (norsk):**
- `golfbox_catalog_no.json` – 176 klubber med baner + tee-er (fasit).
- 123/176 klubber med koordinater (112 presise fra OSM + resten geokodet).
- Resten fylles av GPS-læring når banene spilles.

**Nøkkelfiler:**
- `course_matcher.py` – matcheren  ·  `course_db.json` – lærte GPS-baner
- `golfbox_catalog_no.json` – katalog m/koordinater
- `golfbox_course_map.json` – manuelle/lærte navne-mappinger
- `build_golfbox_catalog.py` · `enrich_catalog_osm.py` · `geocode_catalog.py`
- `golfbox_post.py` · `auto_sync.py` · `.github/workflows/auto-sync.yml`

Nyttige kommandoer:
```
python3 course_matcher.py                 # status
python3 course_matcher.py <lat> <lon>     # test en posisjon
python3 build_golfbox_catalog.py          # hent katalog (per land: GOLFBOX_COUNTRY=dk ...)
python3 enrich_catalog_osm.py             # fest presise OSM-koordinater
```

---

## ▶️ Mulige neste steg

1. **Flere land (Norden):** kjør `build_golfbox_catalog.py` + `enrich_catalog_osm.py`
   med `GOLFBOX_COUNTRY=dk/se/is/fi` (krever innlogging i det landets Golfbox).
2. **Sentralisere basen:** flytt `course_db.json` + katalog til delt skylagring, så alle
   brukere leser fra og bidrar til samme base (nettverkseffekt).
3. **Deploye auto-sync til skyen:** følg `GITHUB_OPPSETT.md`.
4. **Bedre katalog-dekning:** hente tee-koordinater / flere OSM-tagger for de ~53 uten.

Partnerskap/lovlighet: parkert bevisst – vi fokuserer på å lage løsningen best mulig
først.

---

## 🔎 Kjente forbehold
- Bortebaner uten koordinater fylles av læring (spill dem én gang).
- Utenlandske baner (Spania) = egen Golfbox-flyt, dekkes ikke.
- Golfbox-økt må fornyes innimellom (dager–uker) fra mobil/PC.
- Kjør ⛳ én runde av gangen lokalt (flere samtidig kræsjer nettleseren).

## Neste gang: si «fortsett», så tar vi neste steg.
