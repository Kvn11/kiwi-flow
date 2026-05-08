# Obsidian Organize Commands

Reference for file management commands. All commands follow the syntax:

`obsidian vault=<name> <command> [params] [flags]`

---

## `move`

Relocate or rename a file with automatic link updates.

### Parameters

| Parameter | Required | Description |
|---|---|---|
| `file=<name>` | One of these | Identify the file by name (without path) |
| `path=<path>` | One of these | Identify the file by full vault-relative path |
| `to=<path>` | Yes | Destination path (folder or full path including filename) |

### Flags

None.

### Notes

Handles both folder moves and full path renames. Internal links throughout the vault are automatically updated.

### Examples

Move to a folder:

```
obsidian vault=kiwiv2 move file=Design to=archive/
```

Rename via move:

```
obsidian vault=kiwiv2 move file=Draft to="Design Decision.md"
```

---

## `rename`

Change the filename only, preserving the file extension and location.

### Parameters

| Parameter | Required | Description |
|---|---|---|
| `file=<name>` | One of these | Identify the file by name (without path) |
| `path=<path>` | One of these | Identify the file by full vault-relative path |
| `name=<name>` | Yes | New filename without extension |

### Flags

None.

### Notes

Convenience command for in-place renames. Use `move` when you also need to change the file's location.

### Example

```
obsidian vault=kiwiv2 rename file=Draft name=Final
```

---

## `delete`

Remove a file. Moves to trash by default.

### Parameters

| Parameter | Required | Description |
|---|---|---|
| `file=<name>` | One of these | Identify the file by name (without path) |
| `path=<path>` | One of these | Identify the file by full vault-relative path |

### Flags

| Flag | Description |
|---|---|
| `permanent` | Skip trash and delete the file permanently |

### Example

```
obsidian vault=kiwiv2 delete file=OldNotes
```

---

## `property:remove`

Delete a property from a file's frontmatter.

### Parameters

| Parameter | Required | Description |
|---|---|---|
| `name=<name>` | Yes | Name of the property to remove |
| `file=<name>` | One of these | Identify the file by name (without path) |
| `path=<path>` | One of these | Identify the file by full vault-relative path |

### Flags

None.

### Example

```
obsidian vault=kiwiv2 property:remove name=deprecated file=Architecture
```

---

## Tips

- Prefer `move` over `rename` when you also need to change location — both update internal links automatically.
- Use `delete` without `permanent` to keep trash recovery available.
