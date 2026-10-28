# Private TV configuration

`device.json` is consumed by the engine. The matching control token is embedded
in the signed controller as `window.COMMERCIAL_BLOCK_TOKEN`. Keep both private.
The [example](device.example.json) contains placeholders and cannot authenticate
or identify a real TV.

| Field | Meaning |
| --- | --- |
| `identity.psid` | The owning TV's Samsung pseudonymous device identifier used by its recognition client |
| `identity.vdvendorcode` | Vendor code used by that TV's native ACR requests |
| `identity.modelID` | Native ACR model identifier; do not assume it is the retail model name |
| `identity.sourceInfo` | Numeric source value represented as a string |
| `parameters.api` | Parameter negotiation request type: `2` |
| `parameters.zipcode` | Region/postal value used by the TV's parameter request |
| `parameters.firmware` | Firmware identifier used by its recognition client |
| `parameters.modelID` | Model identifier used by its parameter request |
| `controlToken` | 32 random bytes encoded as 64 lowercase hexadecimal characters |

Obtain identity and parameter values from the native recognition configuration
or authorized inspection of requests made by **your own TV**. They must describe
the same device. This repository does not currently automate that discovery or
provide a universal PSID/credential. The builder checks structure, not whether
Samsung will accept a device or region. The engine validates the server's
fingerprint version and enabled query capability before recognition.

The source uses `wss://acr-us-prd.samsungcloud.tv/getacrinfo`, fingerprint version
1.2 and normal recognition query type 1. The image fingerprint is computed on
the TV; its result and device/source metadata are sent to Samsung. Local pill
checks do not contact an AI model. Metadata does not establish a show title or
channel when the TV has not exposed one.

The build tool generates `controlToken` when it is absent. For updates, use the
exact installed file with its current token; otherwise the controller and engine
can disagree. A copy is retained in the private deployment bundle. Recovery uses
a separate generated token saved as `recovery-token` and embedded only in its
own widget.

## Public issue reports

Include model, firmware, source revision, whether the main app is enabled,
whether root recovery connected, and whether query counts increase. Describe
ad misses, false covers and delays. Omit PSID, region/postal data, DUID,
certificates, passwords, tokens, signed packages, raw Samsung replies and
screenshots unless deliberately reviewed for public disclosure.
