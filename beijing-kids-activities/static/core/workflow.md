# Beijing Kids Activities — Workflow

## Purpose

Query parent-child activities at Beijing kindergartens from the 3ren.cn baby-map-center
POI (Point of Interest) service.

## How to invoke

Run the Python script with the required parameters:

```bash
python scripts/query_activities.py --keywords "中华女子" --start-time 1783180800000
```

### Parameters

| Parameter     | Type   | Required | Default | Description |
|---------------|--------|----------|---------|-------------|
| `--keywords`  | string | Yes      | —       | Search keywords (e.g. "中华女子", "亲子", "幼儿园活动") |
| `--start-time` | int   | Yes      | —       | Epoch timestamp in milliseconds (e.g. 1783180800000) |
| `--page-index` | int  | No       | 1       | Page number for pagination |
| `--page-size`  | int  | No       | 50      | Results per page (max 50) |
| `--no-verify-ssl` | flag | No    | false   | Disable SSL certificate verification (macOS workaround) |
| `--proxy`   | string | No       | —       | HTTP/HTTPS proxy URL, e.g. `http://127.0.0.1:7890` (国内代理) |
| `--debug`      | flag | No       | false   | Print debug info (request/response) to stderr |

### Raw JSON output

The script prints the raw JSON response. See `SKILL.md` → **Output schema** for the
complete list of fields to present to the user and the display format.

### Error handling

- Non-200 HTTP status codes cause the script to exit with code 1 and print the error.
- Network errors print the exception message and exit with code 1.
