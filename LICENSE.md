# Licence

scitadel-hub is dual-licensed:

```
SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-scitadel-Commercial
```

- **AGPL-3.0-only.** See [`LICENSE-AGPL-3.0`](LICENSE-AGPL-3.0). If you run a modified hub as a network service, you must offer its users the corresponding source (AGPL §13).
- **Commercial licence (`LicenseRef-scitadel-Commercial`).** For organisations that can't or won't accept the AGPL's terms, e.g. on-prem deployments with proprietary modifications or bundling into closed products. It is available on request. Supported deployment packaging (NixOS module, OCI image, Helm chart) comes with it.

Additional permissions under AGPL §7 (for interoperability with the MIT/Apache-licensed scitadel client and the client/hub protocol) will be written into this file before the first release; see vig-os/scitadel#333.

The client/hub protocol crate (`scitadel-hub-proto`) is **not** part of this repo. It lives in [vig-os/scitadel](https://github.com/vig-os/scitadel) under `MIT OR Apache-2.0`, so clients and integrators never take on the AGPL.

This file is not legal advice.
