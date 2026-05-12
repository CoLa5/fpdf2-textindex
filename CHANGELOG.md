# Changelog

All notable changes to this project will be documented in this file.

The changelog is created using
[Conventional Commits v1.0.0](https://www.conventionalcommits.org/en/v1.0.0/)
and
[Commitizen](https://commitizen-tools.github.io/commitizen/commands/changelog/),
the format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [PEP 440](https://peps.python.org/pep-0440/).

## [0.1.0] - 2026-05-12

### Added

- Remove dependency on own fixed fpdf fork and instead monkeypatch the bugs here
- Parse link locations in pdf and hand them to the entries before rendering
- Add example
- Add renderer
- Add FPDF support
- Add concordance list
- Add parser
- Add interface
- Add md emphasis enum class

### Removed

- Remove color from pre-commit md report
- Change license to GPL-3.0-only

### Fixed

- Fix diverging ids under windows bof zlib
- Fix specific incompatibilities of 3.10 to python3.12
- Loading of concordance file if not set before initialization
- Remove typing from slice
- Make `collect_index_links` public
