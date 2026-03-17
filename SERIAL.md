# Serial Port Output Reference

This document describes **automated** messages the firmware sends on the serial port. It does not cover CLI commands or command responses (see [CLI.md](CLI.md)).

- **Baud rate:** 115200  
- **Format:** One JSON object per line (newline-terminated). In AP/setup mode (no WiFi credentials), log lines may be plain text with an emoji prefix instead of JSON.  
- **Thread safety:** Messages are written atomically (single write + flush) so lines are not interleaved.

---

## Common fields (across message types)

| Tag | Meaning |
|-----|--------|
| **tm** | Time, local (HH:MM:SS from timezone). First field in most messages. |
| **ty** | Message **type**. Determines the kind of payload (see below). |
| **mc** | Device ID (MAC address, 12 hex chars, no colons). |
| **si** | Session ID (8-digit number for this boot session). The Boondock app uses **si** to determine sessions: when **si** changes for a device, the previous session is closed and saved to Sessions history, and a new session is started. |

---

## Message types (`ty`)

### `ty: "log"` — Log / diagnostic line

Emitted by the logging system (and once at boot before the logger is ready). Filter by level with **lv**.

| Tag | Meaning |
|-----|--------|
| **tm** | Local time. |
| **ty** | `"log"` |
| **lv** | Log level: `"fatal"`, `"error"`, `"warning"`, `"info"`, `"debug"`, `"event"`. |
| **ms** | Message text (may include emoji prefix in normal mode). |
| **mc** | Device ID. |
| **si** | Session ID. |
| **rr** | *(Only in INIT message)* Reset reason string (e.g. `"Power On"`, `"Software Reset"`). |

**When:** Continuously, as code calls `logFatalf`, `logErrorf`, `logWarnf`, `logInfof`, `logDebugf`, `logEventf`. One extra **log** at boot: INIT with reset reason (`rr`). In AP/setup mode, the same messages may appear as **plain text** (emoji + text) instead of JSON.

---

### `ty: "ready"` — Device setup complete

Sent once after all startup tasks are created and the device is ready.

| Tag | Meaning |
|-----|--------|
| **ty** | `"ready"` |
| **tm** | Local time. |
| **ms** | `"Device setup complete"`. |
| **mc** | Device ID. |
| **si** | Session ID. |
| **dv** | Device “valid” / ready: `true`. |
| **nw** | WiFi connected: `true` / `false`. |
| **ip** | WiFi IP (or `""` if not connected). |
| **ba** | Backend/API verified: `false` until first successful request. |
| **ti** | Time valid (RTC/NTP): `true` / `false`. |
| **re** | Record task running: `true` / `false`. |
| **sd** | SD card in use (storage): `true` / `false`. |

**When:** Once at end of `setup()`.

---

### `ty: "config"` — Configuration snapshot

Two separate JSON objects are sent: first **recorder** config, then **general** config. Sent at startup (when WiFi credentials exist), after settings changes (debounced), and periodically (e.g. every minute).

**Recorder config object:**

| Tag | Meaning |
|-----|--------|
| **tm** | Local time. |
| **ty** | `"config"` |
| **ath** | Audio threshold (sensitivity). |
| **mrm** | Min recording duration (ms). |
| **xrm** | Max recording duration (ms). |
| **stm** | Silence threshold (ms). |
| **prm** | Pre-record (preroll) ms. |
| **cg** | Codec gain (dB). |
| **is** | Input sample rate (Hz). |
| **rsc** | Record to SD card: `true` / `false`. |
| **mc** | Device ID. |
| **si** | Session ID. |

**General config object:**

| Tag | Meaning |
|-----|--------|
| **tm** | Local time. |
| **ty** | `"config"` |
| **fw** | Firmware version string. |
| **ho** | *(EDGE only)* API host. |
| **po** | *(EDGE only)* API port. |
| **ss** | WiFi SSID (primary). |
| **sie** | Static IP enabled: `true` / `false`. |
| **rte** | RTC enabled: `true` / `false`. |
| **usc** | Use SD card: `true` / `false`. |
| **oh** | Timezone offset (hours). |
| **wtp** | WiFi TX power level (1–10). |
| **mc** | Device ID. |
| **si** | Session ID. |

**When:** On startup (if WiFi configured), after settings change (with debounce), and on a periodic interval (e.g. 1 minute) from the serial task.

---

### `ty: "short"` — Short status (recording / upload / audio levels)

Compact status every ~30 seconds when WiFi credentials are configured.

| Tag | Meaning |
|-----|--------|
| **tm** | Local time. |
| **ty** | `"short"` |
| **rg** | Recording in progress: `true` / `false`. |
| **ug** | Upload in progress: `true` / `false`. |
| **qe** | Pending upload queue size. |
| **ut** | Uptime (seconds). |
| **cd** | Current audio level (dB). |
| **mi** | Min audio level this session (dB). |
| **mx** | Max audio level this session (dB). |
| **dr** | *(Optional)* Dynamic range (dB). |
| **wi** | *(Optional)* WiFi connected: `true` / `false`. |
| **ip** | *(Optional)* WiFi IP (or `""`). |
| **ri** | *(Optional)* RSSI (signal strength). |
| **mc** | Device ID. |
| **si** | Session ID. |

**When:** Periodically from the serial task (e.g. every 30 s when WiFi is configured).

---

### `ty: "health"` — Health / stats

Two JSON objects per health emission: **system** health then **recording** health. Sent when the maintenance task or CLI triggers a health report (e.g. HEALTH command).

**System health object:**

| Tag | Meaning |
|-----|--------|
| **tm** | Local time. |
| **ty** | `"health"` |
| **st** | Storage type label: `"SD"`. |
| **sd** | SD card in use: `true` / `false`. |
| **ht** | Heap total (e.g. `"123.45K"`, `"2.50M"`). |
| **hf** | Heap free. |
| **tv** | Time valid: `true` / `false`. |
| **wi** | WiFi connected: `true` / `false`. |
| **ip** | WiFi IP (or `""`). |
| **ri** | RSSI (signal strength). |
| **ut** | Uptime (seconds). |
| **mc** | Device ID. |
| **si** | Session ID. |

**Recording health object:**

| Tag | Meaning |
|-----|--------|
| **tm** | Local time. |
| **ty** | `"health"` |
| **rc** | Recording count this session. |
| **uc** | Uploaded count this session. |
| **pq** | Pending upload queue size. |
| **td** | Total recording duration this session (seconds). |
| **lr** | Last recording timestamp or count. |
| **tu** | Total uploads (lifetime or session). |
| **ta** | Total upload attempts. |
| **ur** | Upload rate. |
| **lu** | Last upload timestamp or count. |
| **ev** | Event count. |
| **le** | Last event timestamp or count. |
| **wc** | Warning count. |
| **fc** | Fatal count. |
| **ec** | Error count. |
| **ht** | Heap total. |
| **hf** | Heap free. |
| **pt** | *(Optional)* PSRAM total. |
| **pu** | *(Optional)* PSRAM used. |
| **su** | *(Optional)* Storage utilization. |
| **am** | API min response time (ms). |
| **ax** | API max response time (ms). |
| **aa** | API average response time (ms). |
| **st** | Array of task stack info: `n` (name), `a` (allocated bytes), `f` (min free), `u` (utilization %). |
| **yr**, **yf**, **ys**, **yh**, **ym**, **yd** | *(If SD yearly summary loaded)* Year, total files, total size string, duration hours, months with recordings, days with recordings. |
| **mc** | Device ID. |
| **si** | Session ID. |

**When:** On demand (e.g. HEALTH command) or when maintenance/health logic requests it; not on a fixed timer like `short`.

---

### `ty: "event"` — Lifecycle / upload events

Used for recording start/stop and upload success. **ev** identifies the event kind.

**Recording start (`ev: "record_begin"`):**

| Tag | Meaning |
|-----|--------|
| **tm** | Local time. |
| **ty** | `"event"` |
| **ms** | Human-readable line (e.g. `"[Record] 🟢 Recording started"`). |
| **ev** | `"record_begin"` |
| **path** | Recording path (file or PSRAM). |
| **ts** | Recording start timestamp (ISO 8601). |
| **sr** | Sample rate (Hz). |
| **mc** | Device ID. |
| **si** | Session ID. |

**Recording stop (`ev: "record_end"`):**

| Tag | Meaning |
|-----|--------|
| **tm** | Local time. |
| **ty** | `"event"` |
| **ms** | Human-readable line (e.g. `"[Record] 🔴 Recording stopped"`). |
| **ev** | `"record_end"` |
| **path** | Recording path. |
| **ts** | Start timestamp (ISO 8601). |
| **dur** | Duration (ms). |
| **sr** | Sample rate (Hz). |
| **db** | *(Optional)* Max level (dB). |
| **reason** | *(Optional)* Stop reason string. |
| **mc** | Device ID. |
| **si** | Session ID. |

**Upload success (`ev: "audio_upload_success"`):**

| Tag | Meaning |
|-----|--------|
| **tm** | Local time. |
| **ty** | `"event"` |
| **ms** | Human-readable line (e.g. `"[Upload] ✅ Audio file successfully uploaded"`). |
| **ev** | `"audio_upload_success"` |
| **file** | Uploaded filename. |
| **size** | File size (bytes). |
| **dur** | Duration (ms). |
| **db** | *(Optional)* Peak level (dB). |
| **speed** | Upload speed multiplier (e.g. realtime = 1.0). |
| **elapsed** | Upload elapsed time (ms). |
| **mc** | Device ID. |
| **si** | Session ID. |

**When:** Automatically when a recording starts, when it stops, and when an audio file is successfully uploaded.

---

### `ty: "info"` — Informational (e.g. endpoint recovery)

Plain JSON with **ty**, **ms**, **mc**, **si**. Example: endpoint recovered after successful upload (`ms` describes which endpoint).

**When:** When an upload endpoint is marked dead and a later upload to that endpoint succeeds (recovery).

---

### `ty: "error"` — Error (upload / API)

Plain JSON with **ty**, **ms**, **mc**, **si**. Used for upload/API failure or notify messages (e.g. endpoint marked dead, last attempt error).

**When:** On upload or API-related errors (e.g. endpoint unreachable, mutex timeout escalation).

---

## AP / setup mode

When the device has **no WiFi credentials**, it runs in AP/setup mode. In that mode, **log** output may be **plain text** instead of JSON: a single line per log with an emoji prefix (e.g. 🔴 for error, 🟡 for warning) and the message text. All other automated messages (e.g. **ready**, **config** if sent, **event**) remain JSON when they are emitted.

---

## Early boot (before logger)

If the task watchdog fails to initialize, one **log**-style JSON is printed with **Serial.println** (no mutex): **ty** `"log"`, **lv** `"fatal"`, **ms** describing the error. No **tm**, **mc**, or **si** are guaranteed at that point.

---

## Summary: `ty` values

| `ty`     | Description |
|----------|-------------|
| `log`    | Log line (use **lv** for level). |
| `ready`  | Boot complete. |
| `config` | Recorder and general config (two objects). |
| `short`  | 30 s status (recording, upload, audio levels). |
| `health` | System and recording health (two objects). |
| `event`  | Recording or upload event (use **ev** for kind). |
| `info`   | Informational (e.g. endpoint recovery). |
| `error`  | Error (e.g. upload/API). |
