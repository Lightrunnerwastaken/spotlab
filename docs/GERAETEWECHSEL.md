# Spot zwischen Laptops übergeben

Lease und E-Stop sind getrennt. Die Lease gibt das Recht zum Kommandieren;
ein erwarteter E-Stop-Endpunkt kann den Roboter auch ohne Lease weiter sperren.

Vor dem Geräte-/WLAN-Wechsel den Lauf in Spotlab mit **Stopp** beenden und den
Abbau abwarten. Spotlab versucht anzuhalten, setzt Spot über `power_off` ab,
gibt die Lease zurück und baut seinen E-Stop ab. Erst danach die Verbindung
trennen. Ein harter Prozessabbruch oder WLAN-Verlust kann nichts mehr am
Roboter abmelden; der verbleibende Not-Aus ist dann kein Lease-Problem.

## Automatische Abgabe

Wenn die aktive E-Stop-Konfiguration ausschließlich den eindeutig eigenen
Endpunkt enthält, leert Spotlab diese mit ihrer aktuellen Konfigurations-ID.
Der Roboter verweigert das bei eingeschalteten Motoren; leere Konfigurationen
werden ab Robotersoftware 3.3 unterstützt. Fremde oder inzwischen ersetzte
Konfigurationen werden nicht umgeschrieben.

Bei zusätzlichen Endpunkten (Tablet/andere Steuerung) meldet Spotlab nur seine
Registrierung ab. Es setzt keine fremden Registrierungen zurück. **Damit ist
keine vollständig automatische Übergabe für jede gemischte Konfiguration
zugesichert:** ein Konfigurationsplatz kann weiterhin erwartet werden.
In diesem Fall am Tablet prüfen. Auch das bisherige Hinzufügen per `set_config`
setzt Registrierungen zurück; Kopieren der Endpunktliste garantiert keine
unterbrechungsfreie Koexistenz. Diese Einschränkung muss am Gerät geprüft werden.

Fehlschläge und das Ergebnis stehen im jeweiligen Lauf unter `diagnose.log`.
Auch eine übersprungene Abgabe steht dort (`E-Stop-Abgabe uebersprungen: …`), mit der
Bedingung und den beteiligten IDs. Stand 16.09.2026: am Gerät kam die Abgabe bisher nie zu
Ende (Abnahmepunkt A3); der zurückgelassene Endpunkt wird beim nächsten Verbinden über die
Frischeprüfung ersetzt, sobald die Motoren aus sind.
`spotlab doctor` zeigt Konfiguration/Lease/E-Stop für die Fehlersuche. Bei
„Motoren an“, unbekanntem Eigentümer oder Netzwerkfehler erfolgt keine erzwungene
Konfigurationsbereinigung und keine automatische Lease-Übernahme.

Offline geprüft: eigene Konfiguration, Tablet erhalten, inzwischen übernommene
Sitzung, Netzwerkfehler, Motoren-an-Ablehnung, Strg+C, Keepalive-Fehler und
abgebrochene Registrierung. Am echten Gerät noch zu prüfen: normaler Gerätewechsel,
gemischte Tablet-Konfiguration, WLAN-Abbruch und Softwareversion.

SDK-Grundlage: https://dev.bostondynamics.com/docs/concepts/estop_service.html
