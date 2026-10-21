# Contributing

Use Python 3.11 or newer. The server and tests use only the Python standard library. Internet link downloads additionally need yt-dlp and FFmpeg; install them using the README.

```sh
python3 setup_local.py
.venv/bin/python server.py --local-only
python3 -m unittest discover -s tests -v
```

On Windows use `.venv\Scripts\python.exe` in place of `.venv/bin/python`. Keep the frontend buildless unless a change genuinely requires additional tooling.

Before opening a pull request:

- Run the offline tests and check the affected feature in a browser.
- Check that `git status` contains no videos, database, logs, environment files, tokens, cookies, or local addresses. Never attach your real library to an issue.
- Explain what changed and how you checked it. Mention the OS and Python version for platform-specific changes.

For bug reports, include the OS, Python version, steps to reproduce, and a sanitized error message. Remove private video links, usernames, paths, network addresses, and account information. Avoid copyrighted or personal sample files; use a small generated fixture instead.

For suspected vulnerabilities, follow [SECURITY.md](SECURITY.md) rather than posting sensitive details publicly.
