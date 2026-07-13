# CLAUDE.md — arbeidsprinsipper for dette prosjektet

Les **STATUS.md** først for full kontekst (arkitektur, hva som virker, exit-koder,
drift). Denne fila er *hvordan vi jobber* — prinsippene enhver økt skal følge.

## Kjerneprinsipper

1. **Generelle løsninger, ikke bane-lapper.** Når vi finner en feil på én bane, løs den
   som et mønster som dekker mange baner. Spør alltid: «hvor mange andre baner har samme
   underliggende problem?» og fiks det der.
2. **Sikkerhetsnett over dekning.** Post ALDRI feil data til GolfBox. Ved tvil: flagg for
   manuell fullføring i stedet for å gjette. Best-effort tee merkes alltid «⚠ DOBBELTSJEKK».
3. **Tørr-test før commit.** Kjør `test_rounds.py` (poster ingenting) og bekreft at
   endringen løfter dekning uten regresjoner FØR vi committer. Ikke la noe gå til
   tilfeldighetene.
4. **Repoet er hukommelsen.** Oppdater STATUS.md når noe vesentlig endres. Chatten er
   forbigående; koden og docs er sannheten.

## Arbeidsflyt (viktig — lærte dette den harde måten)

- **Claude redigerer filer; brukeren committer og pusher fra Mac-en.** Sandkassens git
  kan ikke pushe og etterlater lås-filer som skaper kaos. Aldri `git commit` fra sandkassen.
- **Commit ofte, i små steg**, med beskrivende meldinger. Én logisk endring per commit.
- Ved «diverged» pga. skyens auto-commits: `git pull --rebase && git push`.
- Fokuserte økter: én oppgave per chat. Start med å lese STATUS.md.

## Testing (kjør på Mac-en, ikke i sandkassen)

Aktiver alltid `.venv` og sett `GOLFBOX_HEADLESS=1`. Sandkassen har ikke nettverk til
GolfBox/Supabase/ntfy og kan ikke kjøre Playwright-flyten.

- `python3 test_rounds.py --all` — fasiten: tørr-match alle runder, viser ✓/⚠/✗.
- `python3 debug_round.py <id>` — full dump av noter + faktisk valgt bane/tee.
- `python3 diag_club.py "<klubb>"` — list en klubbs baner + tees live.
- `python3 telemetry.py` — datadrevet feilkø fra ekte runder (Supabase).

## Sikkerhet (ufravikelig)

- `.env`, `data/golfbox_state.json` og nettleserprofil deles ALDRI (gitignorert).
- Ingen hemmeligheter i sporede filer. Alt følsomt i skyen via `${{ secrets }}`.
- Markør må være medspiller (`14-24068`) — ALDRI brukerens eget medlemsnr (`14-25124`).
- Følg web-restriksjoner: ikke omgå blokkerte fetch-kall med curl/python.

## Tekniske fallgruver (allerede løst — ikke gjeninnfør)

- **GolfBox async-reset:** skjemaet reverterer bane/tee til standard etter AJAX. Løst med
  vent-på-stabil + re-assert (`_pick_course`, `_ensure_tees_loaded`, re-assert før tee).
- **Garmin-ratinger er utdaterte (2019):** ikke stol på rating for tee. Eksakt tee-etikett
  («56»=«56») går FØR rating.
- **Garmin fyller tee-data med forsinkelse:** `teeBox=None` → exit 6 (vent/retry), ikke feil.
- **Norske tegn:** Garmin stripper æ/ø/å; GolfBox beholder. Fold begge til ASCII før match.
- **Tee-løse placeholder-baner** («Narvesen Tour»): hopp over i banevalg.

## Norsk

Bruker snakker norsk. Svar på norsk. Vær konkret og ærlig — flagg usikkerhet, ikke overselg.
