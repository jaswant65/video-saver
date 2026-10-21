# Security model

Video Saver is intended for a trusted home/local IPv4 network. Version 1.0.x is the currently maintained release series.

Anyone who can reach the app shares one library and can request downloads, upload video files, view transfer history, and retrieve completed videos. There is no authentication, user isolation, TLS, or per-user disk quota. The built-in Python HTTP server is not an internet-facing production server.

Do not expose it through router port forwarding, a public tunnel, or a public reverse proxy. Use `--local-only` when you only need access on the host. The app rejects non-private client addresses and unexpected Host headers, and requires a per-process request token for mutations; these are defense-in-depth measures, not replacements for authentication or a trusted network.

Downloading a supplied link makes requests from the host, including to resources reachable by the host. A trusted LAN user can consume disk, CPU, and bandwidth or request URLs on that network. Do not let untrusted users access the app. File extensions are checked for uploads; the app does not scan files or verify their media contents. Use a maintained browser/video player and keep yt-dlp, FFmpeg, Python, and JavaScript runtimes updated.

## Reporting an issue

Use this repository's **Security → Report a vulnerability** option if the maintainer has enabled private reporting. If it is unavailable, open an issue asking for a private reporting channel without including exploit steps, personal information, or secrets. Do not post private videos, browser cookies, access tokens, or database files.
