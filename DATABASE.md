# Database

This project stores runtime information in a single SQLite database. By default, the file is created at `stats/history.db`.

## Tables

### `stats`
Records device memory and uptime statistics. Old entries (older than 24 hours) are pruned automatically.

| Column | Type | Description |
| --- | --- | --- |
| `timestamp` | TEXT PRIMARY KEY | UTC timestamp for the stat entry |
| `heap_size` | INTEGER | Total heap size |
| `free_heap` | INTEGER | Available heap memory |
| `min_free_heap` | INTEGER | Minimum free heap observed |
| `max_alloc_heap` | INTEGER | Largest allocatable heap block |
| `psram_size` | INTEGER | Total PSRAM size |
| `free_psram` | INTEGER | Available PSRAM |
| `min_free_psram` | INTEGER | Minimum free PSRAM observed |
| `max_alloc_psram` | INTEGER | Largest allocatable PSRAM block |
| `uptime_s` | INTEGER | Device uptime in seconds |

### `serial_logs`
Stores all serial output lines and an optional tag.

| Column | Type | Description |
| --- | --- | --- |
| `timestamp` | TEXT | Timestamp of the log line |
| `line` | TEXT | Raw text from the serial connection |
| `tag` | TEXT | Optional tag associated with the line |

### `session_logs`
Persists summaries of completed recording sessions.

| Column | Type | Description |
| --- | --- | --- |
| `start` | TEXT | Session start time |
| `end` | TEXT | Session end time |
| `duration_ms` | INTEGER | Length of session in milliseconds |
| `recordings` | INTEGER | Number of recordings in the session |
| `reason` | TEXT | Reason the session ended |

### `session_active`
Tracks the currently running session (if any).

| Column | Type | Description |
| --- | --- | --- |
| `start` | TEXT PRIMARY KEY | Session start time |
| `end` | TEXT | Current end time (updated periodically) |
| `duration_ms` | INTEGER | Elapsed time in milliseconds |
| `recordings` | INTEGER | Number of recordings so far |

