# Obsidian Write Commands

Reference for vault writing and creation commands. All commands follow the syntax:

`obsidian vault=<name> <command> [params] [flags]`

---

## `create`

Create a new note in the vault.

### Parameters

| Parameter | Required | Description |
|---|---|---|
| `name=<name>` | One of these | Create the note with this name (without path) |
| `path=<path>` | One of these | Create the note at this vault-relative path |
| `content=<text>` | No | Initial content for the note |
| `template=<name>` | No | Populate the note from a named template |

### Flags

| Flag | Description |
|---|---|
| `overwrite` | Replace the file if it already exists |
| `open` | Open the note in Obsidian after creating it |
| `newtab` | Open the note in a new tab after creating it |

### Examples

```
obsidian vault=kiwiv2 create name="Meeting Notes" content="# Meeting\n\nAttendees:\n"
```

```
obsidian vault=kiwiv2 create name=Sprint-Review template=Meeting
```

---

## `append`

Add content to the end of an existing file.

### Parameters

| Parameter | Required | Description |
|---|---|---|
| `file=<name>` | One of these | Identify the file by name (without path) |
| `path=<path>` | One of these | Identify the file by full vault-relative path |
| `content=<text>` | Yes | Content to append to the file |

### Flags

| Flag | Description |
|---|---|
| `inline` | Append to the last line instead of starting a new line |

### Example

```
obsidian vault=kiwiv2 append file=Log content="\n## 2026-03-30\n\nUpdated design spec."
```

---

## `prepend`

Insert content at the start of a file, after any frontmatter.

### Parameters

| Parameter | Required | Description |
|---|---|---|
| `file=<name>` | One of these | Identify the file by name (without path) |
| `path=<path>` | One of these | Identify the file by full vault-relative path |
| `content=<text>` | Yes | Content to insert at the start of the file |

### Flags

| Flag | Description |
|---|---|
| `inline` | Insert on the first line instead of starting a new line |

### Example

```
obsidian vault=kiwiv2 prepend file=Architecture content="> Status: Draft\n"
```

---

## `daily:append`

Append content to today's daily note.

### Parameters

| Parameter | Required | Description |
|---|---|---|
| `content=<text>` | Yes | Content to append to the daily note |
| `paneType=tab\|split\|window` | No | How to display the daily note if opened |

### Flags

| Flag | Description |
|---|---|
| `inline` | Append to the last line instead of starting a new line |
| `open` | Open the daily note in Obsidian after appending |

### Example

```
obsidian vault=kiwiv2 daily:append content="- [ ] Review PR #42"
```

---

## `daily:prepend`

Insert content at the start of today's daily note.

### Parameters

| Parameter | Required | Description |
|---|---|---|
| `content=<text>` | Yes | Content to insert at the start of the daily note |
| `paneType=tab\|split\|window` | No | How to display the daily note if opened |

### Flags

| Flag | Description |
|---|---|
| `inline` | Insert on the first line instead of starting a new line |
| `open` | Open the daily note in Obsidian after prepending |

### Example

```
obsidian vault=kiwiv2 daily:prepend content="## Morning Standup\n"
```

---

## `property:set`

Set a frontmatter property on a file.

### Parameters

| Parameter | Required | Description |
|---|---|---|
| `name=<name>` | Yes | Name of the property to set |
| `value=<value>` | Yes | Value to assign to the property |
| `type=text\|list\|number\|checkbox\|date\|datetime` | No | Data type for the property value |
| `file=<name>` | No | Identify the target file by name (without path) |
| `path=<path>` | No | Identify the target file by full vault-relative path |

### Flags

None.

### Example

```
obsidian vault=kiwiv2 property:set name=status value=active file=Architecture
```

---

## Tips

- Use `\n` in `content` values to insert newlines, and `\t` for tabs.
- The `inline` flag appends or prepends to the existing last/first line rather than adding a new line.
