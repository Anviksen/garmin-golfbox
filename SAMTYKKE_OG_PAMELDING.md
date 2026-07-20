# Samtykketekst + påmeldingsskjema til venner

Dette er innholdet du trenger for å invitere en venn inn i multi-bruker-testen.
Skjemaet er bygget i Google Forms og publisert (18. juli 2026):

**Skjema-lenke (del denne med venner):**
https://docs.google.com/forms/d/e/1FAIpQLSfvWAstOt-xULO9NKcFQZtyr3B5eAqlU1Vm8gf3t6XdFgapYQ/viewform

Delingsinnstilling: «Alle som har lenken» (ikke offentlig søkbar/indeksert) –
matcher anbefalingen i driftsnotatet under. Sjekk selv i Innstillinger-fanen om
«Samle inn e-postadresser» er på (krever Google-innlogging for å svare) – det
sto som «Ikke delt» ved publisering, verdt å dobbeltsjekke om du vil ha det slik.

Innholdet under er tekstene som faktisk ligger i skjemaet nå, til referanse og
for å redigere direkte i Google Forms ved behov. Se `MULTIUSER_PLAN.md` for
hvor dette passer inn i helheten.

---

## 1. Intro-tekst (øverst i skjemaet)

> **Garmin → GolfBox, automatisk**
>
> Hei! Dette er et lite hobbyprosjekt jeg har bygget: spiller du en runde med
> Garmin-klokka, havner den automatisk i GolfBox til godkjenning – uten at du
> løfter en finger. Jeg tester det nå med noen få venner før jeg evt. åpner
> for flere.
>
> Dette er IKKE et firma eller en kommersiell tjeneste. Det er kode jeg har
> skrevet selv, på fritiden, og jeg drifter det selv. Les gjennom info under
> før du fyller ut – spesielt sikkerhets-delen og samtykket. Ta gjerne kontakt
> med meg direkte hvis noe er uklart før du sender inn.

---

## 2. Sikkerhetsinfo (rett FØR feltene med passord)

> **Om sikkerheten – les dette før du skriver inn passord**
>
> - GolfBox-passordet ditt lagres **kryptert** i en database jeg har satt opp,
>   ikke i klartekst. Krypteringsnøkkelen ligger et helt annet sted enn selve
>   databasen – å få tak i databasen alene er ikke nok til å lese noe.
> - Databasen er låst med en egen nøkkel som KUN kjøringen som poster rundene
>   dine har tilgang til – ikke den åpne, delte delen av systemet (bane-basen).
> - **Garmin-passordet ditt spør jeg om under, men lagrer det ALDRI.** Det
>   brukes kun i selve innloggings-øyeblikket for å hente en innloggings-nøkkel
>   (token) – passordet skrives aldri til disk og forkastes rett etter. Det er
>   tokenet (ikke passordet) som lagres kryptert, på samme måte som GolfBox-
>   passordet.
> - Koden er åpen og du kan se nøyaktig hva den gjør:
>   github.com/Anviksen/garmin-golfbox
> - **Ærlig forbehold:** dette er et hobbyprosjekt mellom venner, ikke et
>   selskap med sikkerhetsgarantier eller forsikring. Jeg gjør det jeg kan for
>   å beskytte informasjonen din, men kan ikke love at ingenting noensinne går
>   galt. Du kan når som helst be meg om å slette alt jeg har lagret om deg –
>   se avmeldings-info nederst.

---

## 3. Samtykke-avkrysning (påkrevd felt, avkrysningsboks)

> Jeg har lest info over. Jeg forstår at:
> - Tjenesten er **best-effort**, ikke garantert – noen ganger må jeg
>   fullføre en runde manuelt selv i GolfBox.
> - Løsningen bruker en **ikke-offisiell tilkobling** mot Garmin (ikke deres
>   offisielle API). Det verste realistiske utfallet hvis Garmin skulle
>   reagere på dette er at synkroniseringen min slutter å virke – jeg har
>   ikke sett tegn til at Garmin sperrer kontoer for denne typen personlig
>   bruk, men det kan ikke garanteres 100 %.
> - GolfBox-passordet mitt lagres kryptert. Garmin-passordet mitt brukes KUN
>   momentant til å hente en innloggings-nøkkel og lagres aldri (se
>   sikkerhetsinfo over) – alt håndteres av personen som drifter tjenesten.
> - Jeg kan når som helst be om å bli fjernet fra tjenesten, og få dataene
>   mine faktisk slettet – ikke bare skjult.
>
> ☐ Ja, jeg samtykker og vil bli med

*(Sett dette som et påkrevd avkrysningsfelt – ikke la noen sende inn skjemaet
uten å ha krysset av. `provision_user.py` spør deg om dette igjen manuelt før
den oppretter brukeren, som en ekstra sikring.)*

---

## 4. Skjema-felter (bygg disse i Google Forms)

Rekkefølge og feltyper anbefalt:

1. **Navn** – kort svar, påkrevd (visningsnavn til logger/varsler)
2. **E-post** – kort svar, påkrevd (varsling + kontakt ved problemer)
3. *(sett inn sikkerhetsinfo-tekst fra del 2 her, som en «avsnitt»-blokk)*
4. *(sett inn samtykke-avkrysning fra del 3 her)*
5. **Garmin-epost** – kort svar, påkrevd
6. **Garmin-passord** – kort svar, påkrevd *(se driftsnotat i del 5 – dette
   skal ALDRI bli liggende lenge i selve skjema-svarene, akkurat som GolfBox-
   passordet)*
7. **GolfBox-brukernavn** – kort svar, påkrevd
8. **GolfBox-passord** – kort svar, påkrevd
9. **Markørens medlemsnummer** (personen du fører score sammen med, IKKE deg
   selv) – kort svar, format «XX-XXXXX»
10. **Markørens navn** – kort svar, valgfritt (kun hvis medlemsnr er ukjent)
11. **Varslingspreferanse** – flervalg: «E-post», «Push-varsel (app)», «Begge»
12. **Noe annet du vil si?** – avsnitt, valgfritt

**Garmin-innlogging er nå MED i skjemaet** (endret 18. juli 2026 – tidligere
krevde dette en egen i-person-økt). `provision_user.py` logger inn og fanger
tokenet automatisk når du kjører scriptet med svarene fra skjemaet – ingen
synkron økt med vennen lenger nødvendig. Har kontoen deres MFA (engangskode)
på, spør scriptet om koden der og da – ha dem tilgjengelig (telefon/SMS) hvis
du er usikker på om de har det. Fortsatt ett menneskelig sjekkpunkt: du ser et
sammendrag og bekrefter før kontoen faktisk opprettes.

---

## 5. Driftsnotat til deg selv – gjør dette hver gang

- **Begrens tilgang til selve Google-skjemaet/arket** – ikke del det offentlig
  utover lenken du sender direkte til vennen. Vurder å kreve innlogging
  («Begrens til brukere i [domene/organisasjon]» finnes ikke for private
  Google-kontoer, men «krev innlogging for å se» reduserer tilfeldig tilgang).
- Så snart du har kjørt `provision_user.py` for en person og bekreftet at
  raden ligger i Supabase (`python3 user_store.py`): **slett svaret deres fra
  Google Forms-arket** – BEGGE passord (Garmin og GolfBox) skal ikke ligge i
  et regneark lenger enn nødvendig. Databasen (kryptert) er der de skal bo
  videre.
- Kjør `provision_user.py` for én person om gangen, aldri i loop/skript mot
  flere Garmin-kontoer etter hverandre – se advarselen om Garmin-
  ratelimiting i MULTIUSER_PLAN.md. Én innlogging her og nå er trygt; mange
  etter hverandre er det som trigger Garmins bot-deteksjon.
- Slett også eventuelle midlertidige `.b64`-filer du eventuelt lager selv
  (kun relevant for den manuelle fil-fallbacken – normalflyten via
  Garmin-epost/passord genererer ingen slike filer).

---

## 6. Push-varsel (ntfy) – slik kobler du på

Skjemaet spør kun om personen VIL ha push («Varslingspreferanse»). Selve
emne-strengen (som fungerer litt som et passord – se under) genereres nå
automatisk av `provision_user.py` når du svarer «ja» på «Vil personen ha
push-varsel på mobil?» under provisjonering – du trenger ikke lage den selv.

**Din jobb (eier):** når provisjoneringen er ferdig, skriver scriptet ut en
linje som `📱 Push-emne generert: golfbox-xxxxxxxxxxxxxxxx`. Send DENNE
strengen videre til personen (SMS/melding er fint – den er ikke like sensitiv
som et passord, men bør heller ikke postes offentlig, se hvorfor under).

**Personens jobb (mottakeren):**
1. Installer **ntfy**-appen (gratis, iOS/Android – ingen konto nødvendig).
2. Legg til/abonner på emne-strengen du fikk tilsendt, nøyaktig som den er.
3. Ferdig – varsler dukker opp som vanlige push-varsler fra da av.

**Hvorfor emnet må være tilfeldig:** ntfy.sh har ingen brukerkontoer eller
passord – hvem som helst som kjenner emnenavnet kan både sende til og lese fra
det. Det er derfor `provision_user.py` genererer en lang, tilfeldig streng
(`golfbox-` + 16 tilfeldige tegn) i stedet for noe forutsigbart som et navn.

---

## 7. Hvis noen vil melde seg av

Ha en enkel rutine klar (kan være «send meg en melding»): sett `active =
false` på raden deres i Supabase, og slett faktisk alt fra `users`- og
`user_round_state`-tabellen for dem – ikke bare skjul den. Dette er ikke
bygget som et script ennå; gjøres manuelt i Supabase Table Editor inntil
videre (grei oppgave for en senere økt om det blir behov).
