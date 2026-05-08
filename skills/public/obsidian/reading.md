# Obsidian Read Commands

Reference for reading file content commands. All commands follow the syntax:

`obsidian vault=<name> <command> [params]`

---

## `read`

Display the full contents of a file.

### Parameters

| Parameter | Required | Description |
|---|---|---|
| `file=<name>` | One of these | Identify the file by name using wikilink resolution |
| `path=<path>` | One of these | Identify the file by exact vault-relative path |

If neither `file=` nor `path=` is given, defaults to the active file.

### Example

```
obsidian vault=kiwiv2 read file=Architecture
```

```
obsidian vault=kiwiv2 read path="design/decisions.md"
```

---

## `daily:read`

Read today's daily note.

### Parameters

None. Always returns the content of today's daily note.

### Example

```
obsidian vault=kiwiv2 daily:read
```

---

## `property:read`

Get the value of a specific frontmatter property from a file.

### Parameters

| Parameter | Required | Description |
|---|---|---|
| `name=<name>` | Yes | Name of the property to retrieve |
| `file=<name>` | One of these | Identify the file by name using wikilink resolution |
| `path=<path>` | One of these | Identify the file by exact vault-relative path |

If neither `file=` nor `path=` is given, defaults to the active file.

### Example

```
obsidian vault=kiwiv2 property:read name=status file=Architecture
```

---

## Tips

- Use `file=` for wikilink-style name resolution — this matches how Obsidian links work and does not require knowing the full path.
- Use `path=` when you need to target a file by its exact location within the vault (e.g. a file in a specific subfolder).
