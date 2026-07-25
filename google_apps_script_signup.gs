/**
 * Google Apps Script for påmeldingsskjemaet – kjøres AUTOMATISK av Google
 * hver gang noen sender inn skjemaet (onFormSubmit-trigger).
 *
 * Sender svarene DIREKTE til Supabase-tabellen `pending_signups` (via REST
 * API, samme mønster som resten av prosjektets central_registry.py/
 * user_store.py). En egen skyjobb (process_pending_signups.py, kjørt av
 * .github/workflows/process-signups.yml) plukker dem opp derfra og gjør
 * selve Garmin-innloggingen/opprettelsen.
 *
 * VIKTIG (sikkerhet): denne koden kjører i DITT Google-miljø, ikke i det
 * offentlige GitHub-repoet – logger herfra (Apps Script sin "Kjøringer"-fane)
 * er KUN synlige for deg, i motsetning til GitHub Actions-logger (som ville
 * vært offentlige siden repoet er offentlig). Derfor går klartekst-passord
 * gjennom AKKURAT HER (Apps Script -> Supabase), aldri gjennom GitHub.
 *
 * OPPSETT (se WEBHOOK_ONBOARDING.md for full oppskrift):
 *   1. Åpne skjemaet -> de tre prikkene øverst til høyre -> Skript-redigering.
 *   2. Lim inn HELE denne fila, erstatt evt. eksisterende innhold.
 *   3. Prosjektinnstillinger (tannhjul) -> Skriptegenskaper -> legg til:
 *        SUPABASE_URL = https://xxxx.supabase.co   (samme som i .env, uten avsluttende /)
 *        SUPABASE_SERVICE_ROLE_KEY = ...            (Supabase -> Project Settings -> API
 *                                                     -> service_role, IKKE anon-nøkkelen)
 *   4. Klokke-ikonet til venstre (Utløsere) -> Legg til utløser:
 *        Funksjon: onFormSubmit
 *        Hendelseskilde: Fra skjema
 *        Hendelsestype: Ved innsending av skjema
 *   5. Send inn en test-rad i skjemaet selv, sjekk at en rad dukker opp i
 *      Supabase Table Editor -> pending_signups.
 */

function onFormSubmit(e) {
  var props = PropertiesService.getScriptProperties();
  var supabaseUrl = props.getProperty('SUPABASE_URL');
  var serviceKey = props.getProperty('SUPABASE_SERVICE_ROLE_KEY');
  if (!supabaseUrl || !serviceKey) {
    throw new Error(
      'SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY mangler i Skriptegenskaper ' +
      '(Prosjektinnstillinger -> Skriptegenskaper). Se oppsett-kommentaren øverst.'
    );
  }

  // e.namedValues er ikke alltid pålitelig fylt ut (viste seg tomt i praksis
  // 25. juli 2026) - byggger derfor svar-oppslaget direkte fra selve
  // FormResponse-objektet (e.response), som ALLTID er tilgjengelig for en
  // ekte "Ved innsending av skjema"-utløser.
  var values = {};
  e.response.getItemResponses().forEach(function (ir) {
    values[ir.getItem().getTitle()] = ir.getResponse();
  });
  Logger.log(JSON.stringify(Object.keys(values)));  // kun spørsmåls-TITLENE, ikke svarene

  // Matcher på et NØKKELORD i spørsmålsteksten (ikke eksakt streng) – tåler
  // små formuleringsforskjeller i selve skjemaet uten at scriptet ryker.
  function find(keyword) {
    var kw = keyword.toLowerCase();
    for (var question in values) {
      if (question.toLowerCase().indexOf(kw) !== -1) {
        var v = values[question];
        // Avkrysningsbokser/flervalg kan gi en ARRAY (flere avkryssede valg).
        if (Array.isArray(v)) return v.join(', ');
        return v || '';
      }
    }
    return '';
  }

  var consent = find('samtykke').toLowerCase();
  if (consent.indexOf('ja') === -1) {
    // Skal normalt ikke skje siden avkrysningen er et påkrevd felt i
    // skjemaet – men ikke send videre uten samtykke uansett.
    Logger.log('Avbrutt: fant ikke samtykke-bekreftelse i svaret.');
    return;
  }

  var varslingspref = find('varslingspreferanse').toLowerCase();
  var wantsPush = varslingspref.indexOf('push') !== -1 || varslingspref.indexOf('begge') !== -1;

  var payload = {
    label: find('navn'),
    consent_version: 'v2-garmin-passord-i-skjema', // MÅ matche CONSENT_VERSION i provision_user.py
    garmin_email: find('garmin-epost') || find('garmin epost'),
    garmin_password: find('garmin-passord') || find('garmin passord'),
    golfbox_username: find('golfbox-brukernavn') || find('golfbox brukernavn'),
    golfbox_password: find('golfbox-passord') || find('golfbox passord'),
    golfbox_marker_memberno: find('medlemsnummer'),
    golfbox_marker_name: find('markørens navn'),
    notify_email: find('e-post'),
    wants_push: wantsPush,
    status: 'pending'
  };

  var options = {
    method: 'post',
    contentType: 'application/json',
    headers: {
      apikey: serviceKey,
      Authorization: 'Bearer ' + serviceKey,
      Prefer: 'return=minimal'
    },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  };

  var response = UrlFetchApp.fetch(supabaseUrl + '/rest/v1/pending_signups', options);
  var code = response.getResponseCode();
  if (code >= 200 && code < 300) {
    Logger.log('OK – påmelding for «' + payload.label + '» sendt til Supabase.');
  } else {
    // Aldri logg selve payloaden her (kan inneholde passord) – kun
    // Supabase sin feilrespons, som normalt bare beskriver hva som gikk
    // galt (f.eks. manglende felt), ikke ekko av verdiene.
    Logger.log('FEIL (' + code + '): ' + response.getContentText());
    throw new Error(
      'Kunne ikke sende påmelding til Supabase (HTTP ' + code + ') – se Kjøringer-fanen for detaljer.'
    );
  }
}
