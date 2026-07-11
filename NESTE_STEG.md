# Status og plan videre – Garmin → Golfbox

Sist oppdatert etter at bane-matcheren (koordinat + katalog + læring) var bevist.

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
