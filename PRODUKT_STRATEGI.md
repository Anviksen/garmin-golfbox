# Fra personlig verktøy til produkt: bane-matching Garmin → Golfbox

Research og strategi for å gjøre løsningen pålitelig for *mange* brukere, ikke bare deg.

---

## Mulighetsbildet

- **~171 golfbaner** i Norge (11 seks-hulls, 99 ni-hulls, resten 18/27-hulls).
- **~165 000 golfmedlemskap**, alle registrerer handicap i Golfbox.
- Alle NGF-klubber bruker samme system (Golfbox) → én felles taksonomi å matche mot.

Konklusjon: datasettet er **lite og avgrenset** (171 baner), men brukergrunnlaget er
stort. Det er en ideell «bygg én gang, tjen mange»-situasjon.

---

## Kjerneutfordringen og den skalerbare løsningen

**Problem:** Garmin bruker *banenavn* (ofte anleggs-/merkenavn), Golfbox bruker
*klubbnavn*. Disse kan være helt ulike (Aas Gård Golfpark = Hakadal Golfklubb).
Navne-matching vil derfor *aldri* fange alt, og for et produkt er «nesten» ikke godt
nok — feil bane = feil rating = feil handicap.

**Løsningen: koordinat-basert matching.**
Både Garmin og Golfbox har **GPS-koordinater** for hver bane (Garmin har 41 000+
baner med koordinater; vi henter allerede banens lat/lon i hver scorecard). Ved å
matche Garmin-banens posisjon mot nærmeste Golfbox-bane, blir navnet **irrelevant** —
Aas Gårds koordinater peker på Hakadals anlegg uansett hva det heter.

Matching-strategi (i prioritert rekkefølge):
1. **Koordinater** (primær) – nærmeste Golfbox-bane innen f.eks. 500 m.
2. **Navn** (fuzzy/kjerne) – som bekreftelse og tie-breaker.
3. **Crowdsourcet læring** – brukerkorreksjoner forbedrer den sentrale basen.

---

## Dataarkitektur for et produkt

1. **Sentral mapping-database** (produktets kjerneaktivum):
   - De 171 Golfbox-banene med: klubbnavn, GUID, baner, tee-er, **koordinater**.
   - Bygges én gang ved å enumerere Golfbox (vi har allerede hele klubblista + GUID-er).
   - Vedlikeholdes sentralt – alle brukere får den ferdig, ingen lærer opp selv.

2. **Koordinat-matcher**:
   - Tar Garmin-banens lat/lon → returnerer riktig Golfbox klubb/bane/tee.
   - Tee matches deretter på tallverdi (54, 57 …) som allerede fungerer.

3. **Crowdsourcet forbedring (nettverkseffekt)**:
   - Vår auto-læring (allerede bygget) sender korreksjoner tilbake til den sentrale
     basen. Jo flere brukere, jo bedre og mer komplett blir mappingen for alle.

4. **Kvalitetskontroll**:
   - Flagg lav-tillit-matcher (langt unna, flere kandidater) for manuell verifisering
     før innsending – aldri send inn feil score.

---

## De store forbeholdene (viktig for en ekte business)

Teknisk er dette absolutt gjennomførbart. Men å gå fra hobby til produkt har reelle
hindre som må håndteres ærlig:

- **Vilkår og lovlighet:** Å automatisere Golfbox med brukeres innlogging kan bryte
  Golfbox/NGF sine vilkår. En bærekraftig business går sannsynligvis via **samarbeid
  med NGF/Golfbox** framfor skraping.
- **Offisielle API-er er på vei:** NGF/Golfbox utvikler åpne API-er (testes nå med tre
  leverandører). Garmin har et **Golf Premium API** (scorecard-data via partner-avtale).
  Den *riktige* langsiktige plattformen er disse offisielle API-ene, ikke uoffisiell
  automatisering. Verdt å ta kontakt med NGF tidlig.
- **Håndtering av innlogging/persondata (GDPR):** Å lagre mange brukeres Garmin-/
  Golfbox-innlogging er sensitivt. Et produkt må ha sikker, GDPR-kompatibel håndtering.
- **Handicap-integritet:** Masse-automatisert score-innsending berører tilliten til
  WHS-systemet. NGF bryr seg sterkt om dette – nok en grunn til å samarbeide, ikke
  omgå.
- **Utland:** Garmin har 41 000+ baner globalt; Golfbox' utenlandsflyt er en annen.
  Utvidbart senere, men Norge først.

Kort sagt: **teknologien er den enkle delen. Veien til en business går gjennom
partnerskap og offisielle API-er** – både for lovlighet, datasikkerhet og
handicap-integritet.

---

## Anbefalt vei videre

**Spor 1 – Teknisk MVP (nå):**
1. Bygg **koordinat-matcheren** (bruker Garmin-koordinatene vi allerede henter).
2. Enumerér de 171 Golfbox-banene med tee-er + koordinater → sentral mapping-fil.
3. Bytt ut navne-matching med koordinat-først. Behold auto-læring som forbedring.

**Spor 2 – Business/partnerskap (parallelt):**
4. Kontakt **NGF** for å sondere holdning + tilgang til de kommende åpne API-ene.
5. Sondér **Garmin Golf Premium API** for offisiell scorecard-tilgang.
6. Avklar vilkår, GDPR og handicap-integritet før noe tilbys til andre.

**Konkret neste steg jeg kan gjøre:** bygge koordinat-matcheren og et script som
samler inn Golfbox-banene med koordinater, så vi har den sentrale mappingen som
kjerne-aktivum. Det gjør løsningen di robust for alle norske baner umiddelbart.

---

## Kilder
- Norges Golfforbund – Tall og fakta (171 baner, 165 000 medlemskap)
- Garmin Golf Courses (41 000+ baner med koordinater)
- NGF – Golfbox åpne API-er foreligger (under test)
- Garmin Golf Premium API (partner-tilgang til scorecard-data)
