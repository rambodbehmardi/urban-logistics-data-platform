# Contributing

Contributions should preserve the repository's reproducibility and public-safety
contract.

1. Open a focused issue describing the proposed change and its generated-data use.
2. Keep every example fictional and created inside this repository.
3. Add or update a deterministic test for behavioural changes.
4. Run `make check` before submitting a pull request.
5. Document grain, time semantics, replay behaviour and analytical limits.

Never include production data, copied queries, private schemas, credentials,
contact details, internal identifiers, screenshots or proprietary decision rules.
