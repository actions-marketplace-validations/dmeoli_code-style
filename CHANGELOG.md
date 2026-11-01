# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.3.2] - 2026-11-01

### Fixed

- `code-format` gives the formatters of `.code-format` the files relative to
  its directory, from which it runs them, rather than by their absolute
  path, which the check printed among the files out of the style

## [1.3.1] - 2026-11-01

### Added

- this changelog

## [1.3.0] - 2026-11-01

### Changed

- a file with no `.clang-format` up its tree is formatted with the one of
  this repository, which `format.py` gives clang-format by the name of the
  file it assumes, so that a project in this style needs no copy of it;
  `ci/check-style` no longer copies it into the project

### Fixed

- the template of GitLab has the stage `test`, since GitLab expands no
  variable in `stage`: a project changes it, and `STYLE_SETUP`, by defining
  the job `style` again, which GitLab merges with the one of the template

## [1.2.0] - 2026-11-01

### Added

- the variable `STYLE_SETUP` of the template of GitLab, a command run
  before the check (e.g., one that fetches the formatter of some files and
  writes the `.code-format` that names it)

## [1.1.1] - 2026-11-01

### Fixed

- the description of the action is shorter than the 125 characters that
  the Marketplace takes

## [1.1.0] - 2026-11-01

### Changed

- `code-format` takes the formatters of the first `.code-format` up the
  tree of the file, as clang-format finds its `.clang-format`, and runs
  them from its directory, so that the `.code-format` of a repository
  serves also its submodules
- the action is named Code style suggestions, a name that no account of
  GitHub has

### Fixed

- `ci/check-style` runs with the bash 3.2 of macOS, which has no
  `mapfile`: the files out of the style were not formatted, and
  `style.patch` was empty

## [1.0.0] - 2026-11-01

### Added

- `format.py` and `.clang-format`, `code-format` for the formatters of a
  project, `ide-format`, the hook of git, the check of merge requests
  (GitLab) and of pull requests (GitHub) with the suggestions on their
  lines, and their tests

[Unreleased]: https://github.com/dmeoli/code-style/compare/v1.3.2...HEAD
[1.3.2]: https://github.com/dmeoli/code-style/compare/v1.3.1...v1.3.2
[1.3.1]: https://github.com/dmeoli/code-style/compare/v1.3.0...v1.3.1
[1.3.0]: https://github.com/dmeoli/code-style/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/dmeoli/code-style/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/dmeoli/code-style/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/dmeoli/code-style/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/dmeoli/code-style/releases/tag/v1.0.0
