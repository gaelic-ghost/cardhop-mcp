# Cardhop Surface Evidence Map

Generated for macOS Cardhop audit on 2026-03-01.

## Public Documentation Sources

- Cardhop Mac integration docs: <https://flexibits.com/cardhop-mac/help/integration>
- Cardhop iOS integration docs: <https://flexibits.com/cardhop-ios/help/integration>
- Cardhop integrations overview: <https://flexibits.com/cardhop/integrations>
- Flexibits account integrations (Zapier API key management): <https://flexibits.com/account/help/integrations>
- Cardhop product page (Shortcuts mention): <https://flexibits.com/cardhop>

## Local macOS App Evidence

- Cardhop app bundle path: `/Applications/Cardhop.app`
- AppleScript dictionary: `/Applications/Cardhop.app/Contents/Resources/Cardhop.sdef`
  - Includes `parse sentence`
  - Includes optional `add immediately` parameter
- App plist: `/Applications/Cardhop.app/Contents/Info.plist`
  - URL scheme registration includes `x-cardhop`
  - `NSServices` contains `sendToCardhop`

## Observed Accessible Surfaces

- Documented macOS
  - AppleScript `parse sentence`
  - URL scheme `x-cardhop://parse?s=...`
- iOS-documented candidates pending macOS verification
  - URL actions: `show`, `preferences`, `x-callback-url`
  - URL params: `list`, `add`
- Accessible undocumented (local app metadata)
  - macOS Service `Send to Cardhop`

## Cloud/API Notes

- No public Cardhop REST/GraphQL API documentation was identified in official Flexibits public docs during this audit.
- Public integration/account surfaces do exist (for example Zapier account integration management), but these are not direct local Cardhop transport routes.

## Live-Safe Verification Result (2026-03-01)

- `scripts.verify_cardhop_surfaces --mode live-safe` completed.
- Sentinel lifecycle result:
  - Create: success
  - Read: success
  - Update: success
  - Delete: success
- Cleanup result:
  - Residual sentinel contacts: `0`
  - Pending cleanup entries: none
