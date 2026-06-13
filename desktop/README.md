# Athena Desktop

A native desktop shell (Tauri 2 + the system WebView — WKWebView on macOS) for
the Athena dashboard. It opens a window over the locally-served console at
`http://127.0.0.1:8000`, starting the backend for you if it isn't already up.

## How it works

- The window first loads a small **loading shell** (`shell/index.html`) that polls
  the backend's `/api/health`.
- On startup the app best-effort runs `athena up` (via a login shell, so your
  PATH / venv is in scope). If the backend is already running, it's left alone.
- Once healthy, the shell redirects to `http://127.0.0.1:8000`, where the backend
  serves the full dashboard (UI + API + WebSocket on one origin). If it can't be
  reached, the shell shows a friendly hint and keeps polling.

So the model is the same everywhere: **Athena orchestrates; the backend serves.**
The desktop app is just a native, always-available window onto it.

## Develop / run

From the repo root (with the `athena` CLI installed — see `../install.sh`):

```sh
athena desktop            # cargo tauri dev
athena desktop --build    # cargo tauri build  → a distributable .app
```

Or directly:

```sh
cd desktop/src-tauri
cargo tauri dev           # run
cargo tauri build         # bundle (target/release/bundle/macos/Athena.app)
```

Requires the Rust toolchain and the Tauri CLI (`cargo install tauri-cli`).
`target/` and `gen/` are build artifacts and are git-ignored.
