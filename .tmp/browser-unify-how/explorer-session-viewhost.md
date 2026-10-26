# Explorer 1 — BrowserSession / ViewHost / QWebEngineView

See parent chat explorer [BrowserSession ViewHost](323369ff-b927-4dd0-8fd9-094d3bb712a6).

One shared BrowserPanel QWebEngineView. Mini reparents it (ViewHost=mini). Theia is a different view. Explicit browser.mini_player works. Auto-mini when leaving standalone workspace does not (is_browser_visible false after place_browser_panel). MainWindow.apply_browser_view_host("panel") in non-companion never calls IrisIdeWindow.apply_browser_view_host("panel"), so restore can leave the view in the Tool window. Search(play=True) does not flip ViewHost. Mini is Qt.Tool not inside chat. Driver id stable across reparent (_check_mini_player). No second browser Chromium.
