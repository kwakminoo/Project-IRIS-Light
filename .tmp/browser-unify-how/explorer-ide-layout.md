# Explorer 3 — IDE layout vs browser UI

See parent chat explorer [IDE browser layout](082ad9f7-cc5d-48e0-8fb2-ee5e2d363210).

Two hosts: BrowserWorkspacePage (calendar clone, 820:420, sidebar visible) and companion (BrowserPanel replaces Theia on IrisIdeWindow left 80%, chat stays right). Chat is one ChatPanel reparented. No Theia browser tab. BrowserPanel.ide_requested never emitted. Workspace ratio is not IDE 80:20. Mini is extra Qt.Tool HWND. Browser hosts missing from global QSS transparent list that email/calendar have.
