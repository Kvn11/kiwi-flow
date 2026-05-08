# Obsidian Search Commands

Reference for vault search, query, and link analysis commands. All commands follow the syntax:

`obsidian vault=<name> <command> [params] [flags]`

---

## `search`

Text search across the vault. Returns matched lines by default.

### Parameters

| Parameter | Required | Description |
|---|---|---|
| `query=<text>` | Yes | Search text |
| `path=<folder>` | No | Restrict search to this folder |
| `limit=<n>` | No | Maximum number of results to return |
| `format=text\|json` | No | Output format (default: text). Use `json` for structured output with file paths. |

### Flags

| Flag | Description |
|---|---|
| `total` | Show a count of matching results |
| `case` | Enable case-sensitive matching |

### Example

```
obsidian vault=kiwiv2 search query="authentication" format=json
```

---

## `search:context`

Search with surrounding line context. Use this over `search` when you need to understand the context around each match.

### Parameters

| Parameter | Required | Description |
|---|---|---|
| `query=<text>` | Yes | Search text |
| `path=<folder>` | No | Restrict search to this folder |
| `limit=<n>` | No | Maximum number of results to return |
| `format=text\|json` | No | Output format |

### Flags

| Flag | Description |
|---|---|
| `case` | Enable case-sensitive matching |

### Example

```
obsidian vault=kiwiv2 search:context query="TODO" limit=10
```

---

## `tags`

List all tags used across the vault.

### Parameters

| Parameter | Required | Description |
|---|---|---|
| `file=<name>` | No | Scope results to this file (by name) |
| `path=<path>` | No | Scope results to this file (by path) |
| `sort=count` | No | Sort by usage count (default: name) |
| `format=json\|tsv\|csv` | No | Output format |

### Flags

| Flag | Description |
|---|---|
| `total` | Show a count of tags |
| `counts` | Show usage count for each tag |
| `active` | Show only tags currently in use |

### Example

```
obsidian vault=kiwiv2 tags counts format=json
```

---

## `tag`

Get detailed information about a specific tag.

### Parameters

| Parameter | Required | Description |
|---|---|---|
| `name=<tag>` | Yes | The tag to look up |

### Flags

| Flag | Description |
|---|---|
| `total` | Show a count of files using this tag |
| `verbose` | Show additional detail about each file using the tag |

### Example

```
obsidian vault=kiwiv2 tag name=architecture verbose
```

---

## `properties`

List frontmatter properties used across the vault.

### Parameters

| Parameter | Required | Description |
|---|---|---|
| `file=<name>` | No | Scope results to this file (by name) |
| `path=<path>` | No | Scope results to this file (by path) |
| `name=<name>` | No | Filter to a specific property name |
| `sort=count` | No | Sort by usage count (default: name) |
| `format=yaml\|json\|tsv` | No | Output format |

### Flags

| Flag | Description |
|---|---|
| `total` | Show a count of properties |
| `counts` | Show usage count for each property |
| `active` | Show only properties currently in use |

### Example

```
obsidian vault=kiwiv2 properties counts format=json
```

---

## `aliases`

List all aliases defined in file frontmatter across the vault.

### Parameters

| Parameter | Required | Description |
|---|---|---|
| `file=<name>` | No | Scope results to this file (by name) |
| `path=<path>` | No | Scope results to this file (by path) |

### Flags

| Flag | Description |
|---|---|
| `total` | Show a count of aliases |
| `verbose` | Show the source file for each alias |
| `active` | Show only aliases currently in use |

### Example

```
obsidian vault=kiwiv2 aliases
```

---

## `backlinks`

List incoming links to a file (files that link to the target).

### Parameters

| Parameter | Required | Description |
|---|---|---|
| `file=<name>` | No | Target file by name (defaults to active file) |
| `path=<path>` | No | Target file by vault-relative path |
| `format=json\|tsv\|csv` | No | Output format |

### Flags

| Flag | Description |
|---|---|
| `counts` | Show link count per source file |
| `total` | Show total number of incoming links |

### Example

```
obsidian vault=kiwiv2 backlinks file=Architecture format=json
```

---

## `links`

List outgoing links from a file (files that the target links to).

### Parameters

| Parameter | Required | Description |
|---|---|---|
| `file=<name>` | No | Source file by name (defaults to active file) |
| `path=<path>` | No | Source file by vault-relative path |

### Flags

| Flag | Description |
|---|---|
| `total` | Show a count of outgoing links |

### Example

```
obsidian vault=kiwiv2 links file=Architecture
```

---

## `unresolved`

List all broken or unresolved links in the vault — links that point to files that do not exist.

### Parameters

None.

### Flags

| Flag | Description |
|---|---|
| `total` | Show a count of unresolved links |
| `counts` | Show how many times each unresolved target is referenced |
| `verbose` | Show the source file for each broken link |
| `format=json\|tsv\|csv` | Output format |

### Example

```
obsidian vault=kiwiv2 unresolved format=json
```

---

## `orphans`

List files that have no incoming links — notes that nothing else links to.

### Parameters

None.

### Flags

| Flag | Description |
|---|---|
| `total` | Show a count of orphaned files |

### Example

```
obsidian vault=kiwiv2 orphans
```

---

## `deadends`

List files that have no outgoing links — notes that link to nothing else.

### Parameters

None.

### Flags

| Flag | Description |
|---|---|
| `total` | Show a count of dead-end files |

### Example

```
obsidian vault=kiwiv2 deadends
```

---

## Tips

- Prefer `format=json` for all search and query commands when parsing results programmatically.
- Use `search:context` over `search` when you need to understand the surrounding context of matches.
- Combine `backlinks` and `links` to trace the full link neighborhood around a note.
- Use `unresolved`, `orphans`, and `deadends` together to audit vault health and find disconnected or broken content.
