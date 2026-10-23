# tape/ licensing notice

`tape/vendor/` is an unmodified clone of
[Hattorius/Tradingview-ticker](https://github.com/Hattorius/Tradingview-ticker),
licensed under the **GNU General Public License v3.0** (see `tape/vendor/LICENSE`).

It is kept isolated on purpose:

- Only `tape/server.py` imports it. Nothing under `backend/`, `web/` or `data/` does.
- `tape/server.py` runs as a separate process (the "tape sidecar") and talks to the
  rest of The Desk only over a WebSocket (`ws://localhost:8765/tape`) carrying JSON
  `{"symbol","price","change_pct","ts"}` messages.
- Treat `tape/` as a GPL-3 component. The rest of the repository does not link to it
  and is not derived from it.

The ticker library reverse-engineers TradingView's public quote socket; it is used
here for the live header tape only, as a demo convenience. The backtest and agents
use the committed snapshots under `data/`.
