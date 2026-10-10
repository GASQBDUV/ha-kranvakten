# Lerum VA (EDP Future) för Home Assistant

Hämtar mätarställning och förbrukning från Lerums kommuns VA-portal
(`vatjanst.lerum.se`, EDP Future Webb). Fungerar troligen även för andra
kommuner som kör samma portal – ändra bara portalens adress vid inställningen.

## Sensorer (per abonnemang/mätare)

| Sensor | Enhet | Kommentar |
|---|---|---|
| Mätarställning | m³ | `total_increasing` – kan läggas in som vattenkälla i Energipanelen |
| Senaste avläsning | datum | När mätaren senast lästes av |
| Årsförbrukning | m³ | Portalens "Aktuell årsförbrukning" |
| Beräknad årskostnad | SEK | |

Data hämtas en gång i månaden (var 30:e dag) och dessutom när Home Assistant startar.
Vill du hämta direkt kan du köra åtgärden `homeassistant.update_entity` på en av sensorerna. Värdena ändras bara när mätaren läses av
(egenavläsning eller kommunens avläsning), så det blir inga timvärden.

## Installation

**Manuellt:** kopiera mappen `custom_components/lerum_va` till
`/config/custom_components/` i Home Assistant och starta om.

**HACS:** lägg upp mappen i ett eget GitHub-repo och lägg till det som
*Custom repository* (typ *Integration*) i HACS.

## Inställning

Inställningar → Enheter och tjänster → Lägg till integration → **Lerum VA**.

- **Kundnummer** – står på fakturan
- **Personnummer** – ÅÅÅÅMMDDXXXX
- **Portalens adress** – standard `https://vatjanst.lerum.se/FutureWebBasic`

Personnumret sparas i Home Assistants konfiguration (`.storage/core.config_entries`)
eftersom portalen kräver det vid varje inloggning.

## Så fungerar det

1. `POST /EDPLogin/Authenticate` med `CustomerId` och `Identitynumber`
2. `GET /MyServices/SelectBuilding` – listar anläggningar
3. `POST /MyServices/ShowMyServices` med `SelectedBuildingID` (och `SelectedServiceID` för fler abonnemang)
4. Läser ut värdena ur HTML-sidan "Mina abonnemang" och loggar ut

Integrationen läser bara; den registrerar aldrig mätarställningar.
