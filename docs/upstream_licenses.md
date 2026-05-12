# Upstream license audit

Tracks the licenses of the four reference repos. Update before vendoring any
code or data from them.

| Repo | License | Vendored into Circex? | Notes |
|------|---------|-----------------------|-------|
| [sjhend03/GCNMCP](https://github.com/sjhend03/GCNMCP) | TBD — check `LICENSE` | Yes: `circex/{db, search, fetch}/`, `circex/extract/regex/regex_events.py` | Attributed in README + CLAUDE.md. |
| [nasa-gcn/gcn-schema](https://github.com/nasa-gcn/gcn-schema) | NASA-1.3 / Apache-2.0 (verify) | Schemas mirrored as Pydantic; planned PR back upstream | No raw code copied. |
| [nasa-gcn/circulars-nlp-paper](https://github.com/nasa-gcn/circulars-nlp-paper) | TBD — check `LICENSE` | Reads tarball + CSVs at runtime via `references/` | Data only, no code. |
| [skyportal/timedomain-taxonomy](https://github.com/skyportal/timedomain-taxonomy) | BSD-3-Clause (verify) | YAML files read at runtime | tdtax PyPI wheel can't install on Py 3.14. |

**TODO Sprint 1 close-out:** open each repo's LICENSE file, fill in the table,
and confirm vendoring is compatible with MIT (Circex's license).
