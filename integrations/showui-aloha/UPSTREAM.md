# ShowUI-Aloha (vendored)

- Upstream: https://github.com/showlab/ShowUI-Aloha
- License: Apache-2.0 (see `LICENSE`)
- Vendored for IRIS Light Human-Taught Computer-Use integration.
- IRIS accesses Aloha only through `iris.learning` adapters — do not import Aloha from UI code.
- Aloha Act uses PySide6/Flask; IRIS runs it out-of-process via `AlohaBridge` to avoid Qt binding conflicts with PyQt6.
