# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.2] - 2026-06-24

### Added

- Added repository scaffolding for release notes, documentation indexing, example scripts,
  and integration-test environment templates.
- Added project URLs to package metadata.

### Changed

- Updated package metadata and documentation to use the Unlicense.
- Expanded quality checks to include examples and Google-style docstring linting.
- Included documentation and examples in source distributions while preserving schema cache
  exclusions.
- Kept mypy focused on project code by skipping NumPy stub traversal, including stub-file
  imports, to avoid conflicts between current NumPy stubs and the package's Python 3.10
  type-check target.
- Switched the PyPI release workflow to Trusted Publishing and made GitHub release asset
  uploads rerun-safe.
