---
name: kalshi
description: Use when the user asks about their Kalshi account (cash, positions, portfolio value), wants to search Kalshi prediction markets by topic, or wants to view current prices on a Kalshi event or market. Read-only — no order placement or streaming.
---

# Kalshi (read-only)

A read-only CLI for the Kalshi prediction-market API. Three things you
can do: see what's in the user's account, find markets by keyword, and
look at current prices.

## Running the CLI

If the host refuses to execute `kalshi_cli.py` from its installed path
(e.g. sandboxes that only permit executables under `/mnt/user-data/`),
copy the script into the writable workspace once and run from the
copy. Do not ask the user — it's a path workaround, not a state
change:

```sh
cp ~/.claude/skills/kalshi/kalshi_cli.py /mnt/user-data/workspace/kalshi_cli.py
python3 /mnt/user-data/workspace/kalshi_cli.py account
```

Reuse the copy for the rest of the session. If the source path is also
missing, find `kalshi_cli.py` under the active skill mount and copy
from there; it's a single self-contained file.

## Commands

All commands accept `--json` for structured output. Default output is
concise text. The CLI is prod-only; there is no environment flag.

### `account` — what's in the account

```sh
python3 ~/.claude/skills/kalshi/kalshi_cli.py account [--json]
```

Use when the user asks about cash, positions, exposure, or portfolio
value. The JSON shape is:

```json
{"cash_cents": 12254, "positions_cents": 1047, "total_cents": 13301,
 "positions": [{"ticker": "KXCODINGMODEL-26DEC-ANTH",
                "event_title": "Best coding model by Dec 26th?",
                "yes_outcome": "Anthropic",
                "side": "YES",
                "position": 6, "exposure_cents": 480}]}
```

Each position carries both the technical `ticker` and a human-readable
description (`event_title` + `side` + `yes_outcome`) — surface the
friendly form when reporting positions to the user. `yes_outcome` is
the answer the YES side resolves to; `side` is `"YES"` for net long
YES (positive `position`) and `"NO"` for net long NO (negative
`position`). For multiple-choice events (e.g. picking among Anthropic /
OpenAI / Gemini / xAI), each candidate is its own binary market — so
`side: "NO"` on `KXCODINGMODEL-26DEC-ANTH` means "betting Anthropic
does NOT win", which is meaningfully different from `side: "YES"` and
must be relayed to the user as such. Default text output prints
`<event_title> — <side> <yes_outcome>` on an indented line under the
ticker.

**Important:** `total_cents` is `cash + positions`. Never report
`positions_cents` alone as "portfolio value" — that's Kalshi's
historically misleading field name. Always report `total_cents` as the
portfolio total.

### `search` — find markets by keyword

```sh
python3 ~/.claude/skills/kalshi/kalshi_cli.py search "<keywords>" [--limit N] [--all-events] [--json]
```

Use when the user mentions a topic ("ethereum", "bitcoin range",
"election") and you need a concrete event ticker. Multi-word queries
**AND-match** every token (case-insensitive substring) against series
title, ticker, tags, and category. The result lists each matching
series with its **open** events inlined. Pass `--all-events` to include
non-open events; `--limit` defaults to 10.

### `prices` — current prices for an event or market

```sh
python3 ~/.claude/skills/kalshi/kalshi_cli.py prices <ticker> [--kind event|market] [--json]
```

Pass either an event ticker (e.g. `KXETH-26APR2823`, prints the full
ladder) or a market ticker (e.g. `KXETH-26APR2823-B2310`, prints one
contract). The CLI auto-detects by probing `/markets/<ticker>` first
and falling back to `/events/<ticker>`. Pass `--kind` if you already
know the shape (saves one round trip on the event branch).

## Reading the output

- `yes_bid` / `yes_ask`: the probability that the YES side resolves
  true, expressed as a price in `[0.00, 1.00]`. `bid` is the best price
  someone will buy at; `ask` is the best price someone will sell at.
- An **event** is a single occurrence (e.g. one hourly window) that
  contains a *ladder* of binary contracts (one per price bucket). The
  event-view table is that ladder.
- A **market** is one binary contract inside an event.
- `volume_24h` is contracts traded in the last 24 hours; `volume` is
  cumulative.

## Failure modes

| Message | Meaning |
|---|---|
| `error: no Kalshi credentials found …` | Credentials are missing on this machine. Tell the user — do not attempt to provision them yourself. |
| `error: kalshi API 401 — credentials rejected …` | Wrong key/PEM, or the system clock is significantly off. |
| `error: config file at … has unsafe permissions …` | Run the suggested `chmod 600` command. |
| `error: no event or market matching ticker <T>` | Both `/markets/<T>` and `/events/<T>` returned 404. The ticker is wrong, settled, or never existed. |
| `error: empty ticker` | `prices` was called without a ticker. |
| `error: network — …` | DNS/connection failure. |

## Hard rules

- **Never** print the user's API key ID or the contents of the PEM.
  The CLI never logs them; you should never repeat them either.
- **Never** invent ticker shapes. Derive them from `search` output or
  from what the user typed.
- This skill is **read-only**. If the user asks to place, cancel, or
  amend an order through this skill, refuse and explain that this CLI
  has no order-entry path.
