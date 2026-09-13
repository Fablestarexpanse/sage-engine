# Changelog

## Release process — record the publish date

SAGE is licensed under `FSL-1.1-ALv2` (`engine/LICENSE`). Each version converts to the Apache
License 2.0 on the **second anniversary of the date that version is made available**, so every
release entry must record that date. The date is part of the licence terms, not bookkeeping.

For every tagged release:

1. Add a section headed `## [<version>] — published YYYY-MM-DD`, using the date the version is
   first made available to anyone outside the licensor (push of a public tag, package upload,
   or delivery to a customer, whichever comes first). A private internal tag is not publication.
2. Add the line `Apache-2.0 conversion date: YYYY-MM-DD` (publish date plus two years).
3. Tag the commit `v<version>` and use the same publish date in the tag message.
4. Never edit a recorded publish date after release.

Versions built before the first publication have no conversion date.

## [Unreleased]

- Licensing: SAGE engine licensed under FSL-1.1-ALv2 (`engine/LICENSE`); Fablestar Expanse
  content declared proprietary (`NOTICE`). Replaces the undeclared MIT entry in
  `pyproject.toml`.
- SAGE decoupling Phase −1: admin World Builder saves no longer erase WorldForge floors; tick
  handler errors are logged; hot reload drops removed commands.

## [0.2.0] — not published

Pre-SAGE Fablestar MUD platform. Internal version only; never made available, so no conversion
date applies.
