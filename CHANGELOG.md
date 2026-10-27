# Changelog

All notable changes to this project are documented here. This file is
maintained by [release-please](https://github.com/googleapis/release-please)
from [Conventional Commits](https://www.conventionalcommits.org/) — please don't
edit release sections by hand.

## [0.2.0](https://github.com/cyber-emreclskn/portpilot/compare/v0.1.3...v0.2.0) (2026-10-27)


### ⚠ BREAKING CHANGES

* CLI commands now exit 1 when nothing is listening or a kill fails, and 2 when the confirmation is declined (previously always 0). Python 3.10+ is now required (3.8 could not import the package).

### Bug Fixes

* repair TUI kill crash, macOS permission error and version reporting ([02b6994](https://github.com/cyber-emreclskn/portpilot/commit/02b6994f9ee6a4d1d460aa52f9abfaf528fe9e41))


### Documentation

* refresh README and add contributing guide, security policy and templates ([7903df0](https://github.com/cyber-emreclskn/portpilot/commit/7903df0a123c9abd5cbc87145ef08dee5bde7df5))

## 0.1.3

* Initial public release.
