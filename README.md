# Classroom To-Do

A small local script that pulls my Google Classroom coursework and publishes it as a
single static page on GitHub Pages.

- `classroom_todo.py` — fetches courses, coursework and submission states, then writes
  `TODO.md`, `TODO-semester.md` and `index.html`.
- `run.bat` — one-click runner (creates a virtualenv and installs dependencies on first run).
- `refresh.bat` — scheduled entry point: regenerates the files and pushes `index.html`.
- `SETUP.md` — how the Google Cloud / OAuth side was configured.

Only `index.html` is published. Credentials (`client_secret.json`, `token.json`) stay
local and are git-ignored.

See the live page via GitHub Pages.
