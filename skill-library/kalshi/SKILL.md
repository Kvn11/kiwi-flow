---
name: kalshi
description: Use when the user asks about their Kalshi account (cash, positions, portfolio value), wants to search Kalshi prediction markets by topic, or wants to view current prices on a Kalshi event or market. Read-only — no order placement or streaming.
credentials:
  fields:
    - { name: api_key_id,      label: "Kalshi API Key ID (UUID)", type: text }
    - { name: api_private_key, label: "Kalshi RSA Private Key (PEM contents)", type: textarea }
---

# Kalshi (read-only)

Three in-process skill tools for the Kalshi prediction-market API: see what's
in the user's account, find markets by keyword, and look at current prices.

## Credentials

Kalshi credentials live in the Kiwi credential broker. The user manages them in
**Settings → Credentials → kalshi** (two fields: API Key ID, and PEM contents).
The handlers read them directly via the broker — credentials never enter the
sandbox environment, never become env vars, never reach a subprocess.

If credentials are missing or rejected, tell the user to open Settings →
Credentials → kalshi and fill in (or correct) the fields. **Do not** attempt
to provision credentials yourself — there is no `setup` flow inside the skill.

## Skill tools

Invoke each tool via the dispatcher:

```
invoke_skill_tool(skill="kalshi", tool=<one of: account | search | prices>, args={...})
```

All return values are JSON strings. Parse with `json.loads` if you need
structured access; otherwise relay relevant fields to the user.

### `account` — what's in the account

```
invoke_skill_tool(skill="kalshi", tool="account", args={})
```

Returns:

```json
{"cash_cents": 12254, "positions_cents": 1047, "total_cents": 13301,
 "positions": [{"ticker": "KXCODINGMODEL-26DEC-ANTH",
                "event_title": "Best coding model by Dec 26th?",
                "yes_outcome": "Anthropic",
                "side": "YES",
                "position": 6, "exposure_cents": 480}]}
```

Each position carries both the technical `ticker` and a human-readable
description (`event_title` + `side` + `yes_outcome`) — surface the friendly
form when reporting positions to the user. `yes_outcome` is the answer the YES
side resolves to; `side` is `"YES"` for net long YES (positive `position`) and
`"NO"` for net long NO (negative `position`). For multiple-choice events
(e.g. picking among Anthropic / OpenAI / Gemini / xAI), each candidate is its
own binary market — so `side: "NO"` on `KXCODINGMODEL-26DEC-ANTH` means
"betting Anthropic does NOT win", which is meaningfully different from
`side: "YES"` and must be relayed to the user as such.

**Important:** `total_cents` is `cash + positions`. Never report
`positions_cents` alone as "portfolio value" — that's Kalshi's historically
misleading field name. Always report `total_cents` as the portfolio total.

### `search` — find markets by keyword

```
invoke_skill_tool(skill="kalshi", tool="search", args={"query": "<keywords>", "limit": 10, "all_events": false})
```

Args:
- `query` (str, required): one or more whitespace-separated keywords.
- `limit` (int, optional, default 10): cap the number of series returned. 0 = no cap.
- `all_events` (bool, optional, default false): include non-open events when true.

Use when the user mentions a topic ("ethereum", "bitcoin range", "election")
and you need a concrete event ticker. Multi-word queries **AND-match** every
token (case-insensitive substring) against series title, ticker, tags, and
category. The result lists each matching series with its **open** events
inlined.

### `prices` — current prices for an event or market

```
invoke_skill_tool(skill="kalshi", tool="prices", args={"ticker": "<TICKER>", "kind": "event"|"market"})
```

Args:
- `ticker` (str, required): event ticker (e.g. `KXETH-26APR2823`, returns the full ladder) or a market ticker (e.g. `KXETH-26APR2823-B2310`, returns one contract).
- `kind` (str, optional): pass `"event"` or `"market"` if you already know the shape (saves one round trip on the event branch). Omit to auto-detect by probing `/markets/<ticker>` first and falling back to `/events/<ticker>`.

## Reading the output

- `yes_bid` / `yes_ask`: the probability that the YES side resolves true,
  expressed as a price in `[0.00, 1.00]`. `bid` is the best price someone will
  buy at; `ask` is the best price someone will sell at.
- An **event** is a single occurrence (e.g. one hourly window) that contains a
  *ladder* of binary contracts (one per price bucket). The event-view JSON's
  `markets` field is that ladder.
- A **market** is one binary contract inside an event.
- `volume_24h` is contracts traded in the last 24 hours; `volume` is cumulative.

## Failure modes

When a skill tool fails, the dispatcher returns a string describing the
failure. The agent should react based on the wording:

| Result string contains… | Meaning |
|---|---|
| `are not configured` | User hasn't filled in Kalshi credentials. Direct them to Settings → Credentials → kalshi. |
| `rejected by the upstream service` | Stored credentials were rejected (wrong key/PEM, or system clock significantly off). Ask the user to verify their values in Settings → Credentials → kalshi. |
| `no event or market matching ticker <T>` | Both `/markets/<T>` and `/events/<T>` returned 404. Ticker is wrong, settled, or never existed. |
| `rejected arguments` | Tool args were malformed (e.g. missing `query` for search, empty `ticker` for prices). |

## Hard rules

- **Never** print the user's API key ID or PEM contents. The skill tools never
  return them; you should never repeat them either.
- **Never** invent ticker shapes. Derive them from `search` output or from
  what the user typed.
- This skill is **read-only**. If the user asks to place, cancel, or amend an
  order through this skill, refuse and explain that there is no order-entry
  path here.
