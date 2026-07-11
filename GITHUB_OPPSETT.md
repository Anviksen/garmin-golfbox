# Oppsett: full automatikk i skyen (GitHub Actions + cron-job.org)

Denne guiden setter opp at nye golfrunder **automatisk** havner i Golfbox til
godkjenning – gratis, uten kredittkort, uavhengig av Macen din.

Estimert tid: 30–45 min én gang. Etterpå: kun ~1 min «forny Golfbox-innlogging»
innimellom.

> Rekkefølgen betyr noe. Ta stegene ovenfra og ned.

---

## Før du starter (sjekk at dette finnes lokalt)

Fra tidligere faser skal du allerede ha:
- `~/.garminconnect/` (Garmin-innlogging – laget da du kjørte `fetch_garmin.py`)
- `data/golfbox_state.json` (Golfbox-innlogging – laget da du brukte ⛳-knappen)

Har du begge, er du klar.

---

## Steg 1 – Legg markøren i .env

Åpne `.env` og legg inn markørens (medspillerens) medlemsnummer:

```
GOLFBOX_MARKER_MEMBERNO=XX-XXXXX
```

> Dette er IKKE ditt eget nummer, men den du fører score med. Uten en gyldig markør
> kan ikke en handicaprunde lagres automatisk.

---

## Steg 2 – Legg prosjektet på GitHub (offentlig repo)

Enklest med **GitHub CLI**. I Terminal:

```bash
# Installer GitHub CLI (én gang)
brew install gh

# Logg inn (åpner nettleser)
gh auth login

# Gå til prosjektet og lag repoet + push
cd ~/Documents/garmin-golfbox
git init
git add .
git commit -m "Garmin-Golfbox automatikk"
gh repo create garmin-golfbox --public --source=. --push
```

`.gitignore` sørger for at `.env`, `data/` og innloggingsfiler IKKE lastes opp –
kun koden. (Sjekk gjerne på github.com/Anviksen/garmin-golfbox at det stemmer.)

---

## Steg 3 – Lag de to «hemmelighetene» (secrets)

GitHub trenger Garmin- og Golfbox-innloggingen din kryptert. Lag tekststrenger av
dem i Terminal (de kopieres rett til utklippstavla med `pbcopy`):

**Garmin-token:**
```bash
tar czf - -C ~ .garminconnect | base64 | pbcopy
```
Nå ligger en lang tekst på utklippstavla. Gå til:
`github.com/Anviksen/garmin-golfbox` → **Settings** → **Secrets and variables** →
**Actions** → **New repository secret**
- Name: `GARMIN_TOKENS_B64`
- Secret: lim inn (Cmd-V) → **Add secret**

**Golfbox-økt:**
```bash
base64 -i data/golfbox_state.json | pbcopy
```
Ny secret:
- Name: `GOLFBOX_STATE_B64`
- Secret: lim inn → **Add secret**

**Markør:** en secret til:
- Name: `GOLFBOX_MARKER_MEMBERNO`
- Secret: markørens medlemsnummer (samme som i `.env`)

---

## Steg 4 – Test at det virker

På GitHub: fanen **Actions** → «Auto-sync Garmin til Golfbox» → **Run workflow**.

- **Første kjøring** setter en «baseline»: den markerer alle dagens runder som
  allerede sett og poster INGENTING (så hele historikken ikke sendes inn). Det er
  meningen!
- Åpne kjøringen og les loggen. Ser du «Baseline satt … Ingen posting første gang»,
  fungerer alt.

Neste gang du spiller en NY runde, blir den plukket opp og lagt i Golfbox.

---

## Steg 5 – Gjør det raskt (cron-job.org hvert 5. min)

GitHub sin egen tidsplan er treg (10–30 min). Vi bruker en gratis vekkerklokke i
stedet.

1. Lag en **fine-grained Personal Access Token** på GitHub:
   `Settings` (din profil) → `Developer settings` → `Personal access tokens` →
   `Fine-grained tokens` → **Generate new token**
   - Repository access: **Only select repositories** → `garmin-golfbox`
   - Permissions → Repository → **Actions: Read and write**
   - Generate → **kopier tokenet** (vises kun én gang).

2. Lag gratis konto på **cron-job.org** → **Create cronjob**:
   - Title: `Golf auto-sync`
   - URL:
     `https://api.github.com/repos/Anviksen/garmin-golfbox/actions/workflows/auto-sync.yml/dispatches`
   - Schedule: **Every 5 minutes**
   - Under **Advanced** → Request method: **POST**
   - Headers:
     - `Authorization: Bearer DITT_TOKEN_HER`
     - `Accept: application/vnd.github+json`
   - Request body: `{"ref":"main"}`
   - Save.

Nå dyttes jobben i gang hvert 5. minutt, og runder dukker opp i Golfbox ~5–12 min
etter at du lagrer på klokka.

---

## Den eneste tilbakevendende oppgaven: forny Golfbox-økten

Golfbox logger deg ut innimellom (anslagsvis hver få dager–par uker). Da vil en
kjøring feile med «Golfbox-økt utløpt». Slik fornyer du (tar ~1 min):

1. På Macen: kjør ⛳-flyten én gang (start dashboardet, trykk «Send til Golfbox»,
   logg inn). Det oppdaterer `data/golfbox_state.json`.
2. Lag ny secret-tekst:
   ```bash
   base64 -i data/golfbox_state.json | pbcopy
   ```
3. På GitHub: Settings → Secrets → `GOLFBOX_STATE_B64` → **Update** → lim inn.

Ferdig – automatikken ruller videre.

> Garmin-token fornyer seg selv og varer ~et år. Den trenger du normalt aldri røre.

---

## Nyttig å vite

- **Skru av auto-lagring midlertidig:** i `.github/workflows/auto-sync.yml`, sett
  `GOLFBOX_AUTO_SUBMIT: "0"`. Da fylles runden ut, men lagres ikke (nyttig for test).
- **Sikkerhetsnett:** roboten lagrer kun når klubb + bane + tee + markør er trygt
  matchet. Bommer den (f.eks. Aas Gård / utenlandsk bane), flagges runden i
  `data/posted.json` under `needs_manual` i stedet, og sendes aldri inn feil.
- **Se hva som skjer:** fanen **Actions** viser hver kjøring med full logg.
- **Tidssoner:** GitHub sin reserve-tidsplan er i UTC. cron-job.org bruker din
  tidssone.
```
