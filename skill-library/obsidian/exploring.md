# Obsidian Explore Commands

Reference for vault exploration commands. All commands follow the syntax:

`obsidian vault=<name> <command> [params] [flags]`

---

## `files`

List all files in the vault, with optional filtering by folder or extension.

### Parameters

| Parameter | Required | Description |
|---|---|---|
| `folder=<path>` | No | Filter results to files within this folder |
| `ext=<extension>` | No | Filter results to files with this extension (e.g. `md`, `png`) |

### Flags

| Flag | Description |
|---|---|
| `total` | Show a count of matching files |

### Example

```
obsidian vault=kiwiv2 files ext=md
```

---

## `folders`

List the folder structure of the vault.

### Parameters

| Parameter | Required | Description |
|---|---|---|
| `folder=<path>` | No | Start listing from this subfolder instead of vault root |

### Flags

| Flag | Description |
|---|---|
| `total` | Show a count of folders |

### Example

```
obsidian vault=kiwiv2 folders
```

---

## `outline`

Show the heading structure of a file. Useful for assessing note size and layout before reading.

### Parameters

| Parameter | Required | Description |
|---|---|---|
| `file=<name>` | One of these | Identify the file by name (without path) |
| `path=<path>` | One of these | Identify the file by full vault-relative path |
| `format=tree\|md\|json` | No | Output format for the heading tree |

### Flags

| Flag | Description |
|---|---|
| `total` | Show a count of headings |

### Example

```
obsidian vault=kiwiv2 outline file=Architecture format=json
```

---

## `wordcount`

Get the word and character count for a file.

### Parameters

| Parameter | Required | Description |
|---|---|---|
| `file=<name>` | One of these | Identify the file by name (without path) |
| `path=<path>` | One of these | Identify the file by full vault-relative path |

### Flags

| Flag | Description |
|---|---|
| `words` | Show word count only |
| `characters` | Show character count only |

### Example

```
obsidian vault=kiwiv2 wordcount file=Design
```

---

## `templates`

List all available templates in the vault's templates folder.

### Parameters

None.

### Flags

| Flag | Description |
|---|---|
| `total` | Show a count of available templates |

### Example

```
obsidian vault=kiwiv2 templates
```

---

## `template:read`

Read the content of a specific template, optionally with variable substitution applied.

### Parameters

| Parameter | Required | Description |
|---|---|---|
| `name=<template>` | Yes | Name of the template to read |
| `title=<title>` | No | Title value to substitute into the template |

### Flags

| Flag | Description |
|---|---|
| `resolve` | Resolve template variables before returning content |

### Example

```
obsidian vault=kiwiv2 template:read name=Meeting
```

---

## Tips

- Run `outline` before `read` to assess a note's size and structure. Large notes with many headings may need section-targeted reading rather than reading the full file.
- Use `files ext=md` to discover all notes in the vault before searching or navigating by path.
