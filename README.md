# Copenhell-vagt 🤘

Tjekker [copenhell.dk/billetter](https://www.copenhell.dk/billetter) ca. hvert 14. minut (omkring 100 gange i døgnet) og sender dig en mail, så snart der dukker en-dagsbilletter / onsdagsbilletter op. Copenhell 2027 er 23.–26. juni, så onsdag er 23. juni.

Det kører gratis på GitHub Actions, så din computer behøver ikke være tændt.

## Opsætning (ca. 10 minutter)

**1. Opret et nyt repository på GitHub.** Gå til github.com/new, kald det fx `copenhell-vagt`, og vælg **Public**. (Public er vigtigt: så er Actions gratis uden minutgrænse. Dine adgangskoder ligger som hemmelige "Secrets" og kan ikke ses af andre.)

**2. Upload filerne.** Klik "uploading an existing file" og træk hele indholdet af mappen ind, inkl. mappen `.github`. Hvis `.github` ikke kommer med (skjulte mapper), så klik "Add file → Create new file", skriv navnet `.github/workflows/check.yml` og indsæt indholdet af filen.

**3. Tilføj dine mailoplysninger som Secrets.** Gå til *Settings → Secrets and variables → Actions → New repository secret* og opret:

| Navn | Eksempel | Forklaring |
|---|---|---|
| `SMTP_HOST` | `asmtp.simply.com` | Din mailudbyders udgående server |
| `SMTP_PORT` | `587` | 587 (STARTTLS) eller 465 (SSL) |
| `SMTP_USER` | `dig@domæne.dk` | Brugernavn til mailserveren |
| `SMTP_PASS` | `••••••` | Adgangskode (evt. app-adgangskode) |
| `MAIL_TO` | `shubberne@proton.me` | Hvor advarslen skal sendes hen |
| `MAIL_FROM` | `dig@domæne.dk` | Valgfri – afsenderadresse (ellers bruges SMTP_USER) |

Typiske servere: Simply `asmtp.simply.com:587`, One.com `send.one.com:465`, Gmail `smtp.gmail.com:587` (kræver app-adgangskode), Outlook `smtp-mail.outlook.com:587`.

**4. Slå skrivetilladelse til.** *Settings → Actions → General → Workflow permissions →* vælg **Read and write permissions** og gem.

**5. Send en testmail.** Gå til fanen *Actions → Copenhell-vagt → Run workflow*, skriv `ja` i feltet "Send en testmail" og kør. Efter et minut skulle du have en mail. Kør den evt. igen med `nej` for at lave et rigtigt tjek og se loggen ("Ingen en-dagsbilletter endnu.").

Så kører den af sig selv.

## Hvordan den virker

Scriptet henter billetsiden og leder efter ord som *dagsbillet*, *endagsbillet*, *1-dagsbillet*, *onsdag*, *day ticket* og *Wednesday*, men ignorerer den nuværende *4-dagsbillet*. Finder den noget, får du én mail med uddrag af teksten og link til Ticketmaster. Du får ikke den samme mail igen hver 14. minut; der kommer først en ny, hvis siden ændrer sig.

Hvis siden ikke kan hentes i ca. 6 timer i træk, får du en advarselsmail, så du ved, at vagten ikke ser noget.

## Godt at vide

GitHub kører planlagte jobs "cirka" til tiden og kan springe enkelte over ved travlhed, så nogle dage bliver det lidt færre end 100 tjek. Scriptet gemmer en lille tilstandsfil én gang i døgnet; det holder også repoet aktivt, så GitHub ikke slår planen fra efter 60 dage.

Når du har købt billetter: *Actions → Copenhell-vagt → ⋯ → Disable workflow*.
