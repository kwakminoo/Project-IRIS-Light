# IRIS IDE (Eclipse Theia)

Built-in IDE runtime for Project-IRIS-Light.

## Versions (pinned)

- Eclipse Theia **1.74.0**
- Node.js **>= 22**
- Yarn Classic **1.22.x**

## Source vs runtime

| Location | Purpose |
|----------|---------|
| `integrations/iris-ide/` (repo) | Source manifest + extensions |
| `~/.iris-light/runtimes/iris-ide/` | Installed runtime (`yarn install`, `yarn build`) |

## Bridge

Theia backend starts an HTTP bridge on `127.0.0.1` (dynamic port). IRIS Python uses `iris.infrastructure.iris_ide_client`.

State file: `~/.iris-light/runtime/iris_ide_state.json` (session token — do not log).

## Extensions marketplace

IRIS IDE uses **Open VSX** (same catalog as VS Code-compatible Theia apps):

- Left sidebar **Extensions** (`Ctrl+Shift+X`) or **View → Extensions Marketplace**
- Search/install extensions from [open-vsx.org](https://open-vsx.org/)
- User-installed extensions persist under `~/.iris-light/iris-ide/user-data/plugins`
- Built-in VS Code language packs ship in `plugins/` (downloaded at `yarn build` via `theia download:plugins`)

Manual install: **Extensions** view toolbar → **Install from VSIX…**

## Manual dev

```powershell
cd integrations/iris-ide
yarn install
yarn build
set PORT=3000
yarn start -- C:\path\to\workspace
```
