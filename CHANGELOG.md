# Changelog

## 1.0.1 — 2026-10-30

- Fix completed downloads being labelled as failed when filenames contain Unicode punctuation or the downloader reports a download-limit stop code.
- Force UTF-8 downloader output, restrict playlists to one item without relying on a failure-style stop code, and validate the finished media file before marking it complete.
- Support a host-local Node/Deno path or environment override for reliable JavaScript challenge handling.
- Show clear sign-in/bot-check errors and group earlier failed attempts after a later successful save.
- Add runtime and completion regression tests. Personal host settings remain ignored and are never served by the app.

## 1.0.0

- Initial public source release for running Video Saver on a trusted local network.
- Video link saving, file uploads, a searchable shared library, browser playback, and downloads.
- Windows setup/start/stop/firewall helpers and a macOS/Linux foreground launcher.
- Project-local dependency installation, configurable port, local-only mode, and a custom data directory.
- Offline HTTP integration tests, privacy-focused ignore rules, and open-source documentation.
