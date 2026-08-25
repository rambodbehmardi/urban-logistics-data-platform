# Public Safety Policy

This repository is a clean-room implementation. Its source material is a set
of general data-engineering patterns, not operational code.

## Included

- Deterministically generated delivery events and monetary entries.
- Fictional service cells on a unitless planar grid.
- Generic event names, metric definitions, and validation rules.
- Fresh Python and SQLite code written specifically for this repository.
- Tests that prove reproducibility, idempotency, and contract enforcement.

## Excluded

- Production data, extracts, logs, screenshots, and dashboard exports.
- Real people, businesses, places, addresses, coordinates, or contact data.
- Proprietary table or column names and copied query text.
- Internal identifiers, policy values, workflow exports, and business rules.
- Credentials, endpoints, browser state, message history, and private files.

## Automated guard

`scripts/public_safety_scan.py` scans public text for restricted context terms,
contact patterns, private-key headers, likely secret assignments, cloud-key
shapes, and private network addresses. It reports only a rule name and file
location, never the matching line.

The scan complements review; it does not prove that arbitrary text is safe.
Every future data sample and screenshot still requires a human provenance
check before release.
