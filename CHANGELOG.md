# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

## [2022.3.0]

### Added
- ms wait property to wait prior to starting aqcuisition

## [2022.2.0]

### Added
- nshots property

## [2021.10.0]

### Changed
- toml dependency now explicity specified
- rerender avpr with proper support for null default in types

## [2021.3.2]

### Changed
- Provide new method in avpr defined in core

## [2021.3.1]

### Fixed
- Fixed bug where chopper correspondence was off by one.

## [2021.3.0]

### Fixed
- Removed a bug that limited shots processing scripts to only modify existing daq channels.
- avpr composed with yaq-traits 2021.2.1
- Allow for channels with no baseline

### Changed
- shots processing script now in config only
- shots processing script can create arbitrary channels

## [2020.12.1]

### Fixed
- ni-daqmx-tmux set_nshot message was broken, now works

## [2020.12.0]

## Added
- installation source

## [2020.11.1]

### Fixed
- make invert setting on channel actually invert values

## [2020.11.0]

### Fixed
- removed bad update-state that amost completely broke ni-daqmx-tmux

### Changed
- regenerated avpr based on recent traits update

## [2020.10.0]

### Added
- initial release

[Unreleased]: https://gitlab.com/yaq/yaqd-ni/-/compare/v2022.3.0...main
[2022.3.0]: https://gitlab.com/yaq/yaqd-ni/-/compare/v2022.2.0....v2022.3.0
[2022.2.0]: https://gitlab.com/yaq/yaqd-ni/-/compare/v2021.10.0....v2022.2.0
[2021.10.0]: https://gitlab.com/yaq/yaqd-ni/-/compare/v2021.3.2....v2021.10.0
[2021.3.2]: https://gitlab.com/yaq/yaqd-ni/-/compare/v2021.3.1....v2021.3.2
[2021.3.1]: https://gitlab.com/yaq/yaqd-ni/-/compare/v2021.3.0....v2021.3.1
[2021.3.0]: https://gitlab.com/yaq/yaqd-ni/-/compare/v2020.12.1....v2021.3.0
[2020.12.1]: https://gitlab.com/yaq/yaqd-ni/-/compare/v2020.12.0...v2020.12.1
[2020.12.0]: https://gitlab.com/yaq/yaqd-ni/-/compare/v2020.11.1...v2020.12.0
[2020.11.1]: https://gitlab.com/yaq/yaqd-ni/-/compare/v2020.11.0...v2020.11.1
[2020.11.0]: https://gitlab.com/yaq/yaqd-ni/-/compare/v2020.10.0...v2020.11.0
[2020.10.0]: https://gitlab.com/yaq/yaqd-ni/-/tags/v2020.10.0
