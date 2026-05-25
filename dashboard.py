import argparse
import json
import mimetypes
import os
import sqlite3
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import parse_qs, unquote, urlparse

from owner_registry import demo_owner_for_plate


DEFAULT_DB_PATH = "plates.db"
DEFAULT_SNAPSHOT_DIR = "snapshots"


HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Zimbabwe ANPR Dashboard</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f6f8;
      --panel: #ffffff;
      --ink: #17202a;
      --muted: #667085;
      --line: #d9dee7;
      --green: #11845b;
      --green-bg: #def7ec;
      --red: #b42318;
      --red-bg: #fee4e2;
      --blue: #175cd3;
      --blue-bg: #dbeafe;
      --shadow: 0 12px 34px rgba(16, 24, 40, 0.08);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Arial, Helvetica, sans-serif;
    }

    .shell {
      width: min(1440px, calc(100% - 32px));
      margin: 0 auto;
      padding: 24px 0 40px;
    }

    header {
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 20px;
    }

    h1 {
      margin: 0;
      font-size: 28px;
      line-height: 1.15;
      letter-spacing: 0;
    }

    .subtle {
      color: var(--muted);
      font-size: 14px;
      margin-top: 6px;
    }

    .toolbar {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }

    input, select, button {
      height: 38px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      font-size: 14px;
      padding: 0 12px;
    }

    button {
      cursor: pointer;
      font-weight: 700;
      background: var(--ink);
      color: #fff;
      border-color: var(--ink);
    }

    .stats {
      display: grid;
      grid-template-columns: repeat(4, minmax(160px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }

    .stat {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px 16px;
      box-shadow: var(--shadow);
    }

    .stat span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      font-weight: 700;
    }

    .stat strong {
      display: block;
      margin-top: 8px;
      font-size: 26px;
    }

    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      box-shadow: var(--shadow);
    }

    table {
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
    }

    th, td {
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: middle;
      font-size: 14px;
    }

    th {
      color: #475467;
      font-size: 12px;
      text-transform: uppercase;
      background: #f8fafc;
    }

    tbody tr:hover { background: #f9fbfd; }

    .plate {
      font-weight: 800;
      font-size: 18px;
      letter-spacing: 1px;
      white-space: nowrap;
    }

    .badge {
      display: inline-flex;
      align-items: center;
      min-height: 26px;
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 12px;
      font-weight: 800;
    }

    .badge.normal {
      color: var(--green);
      background: var(--green-bg);
    }

    .badge.blacklisted {
      color: var(--red);
      background: var(--red-bg);
    }

    .badge.other {
      color: var(--blue);
      background: var(--blue-bg);
    }

    .snapshot {
      width: 124px;
      aspect-ratio: 16 / 9;
      object-fit: cover;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #eef2f6;
      cursor: pointer;
      display: block;
    }

    .owner {
      display: grid;
      gap: 4px;
      min-width: 180px;
    }

    .owner strong {
      font-size: 14px;
    }

    .owner small {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }

    .empty {
      padding: 42px 20px;
      text-align: center;
      color: var(--muted);
    }

    .modal {
      position: fixed;
      inset: 0;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 24px;
      background: rgba(15, 23, 42, 0.74);
      z-index: 10;
    }

    .modal.open { display: flex; }

    .modal img {
      max-width: min(1100px, 96vw);
      max-height: 90vh;
      border-radius: 8px;
      background: #fff;
      box-shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
    }

    @media (max-width: 920px) {
      header { align-items: stretch; flex-direction: column; }
      .toolbar { justify-content: flex-start; }
      .stats { grid-template-columns: repeat(2, 1fr); }
      table, thead, tbody, tr, th, td { display: block; }
      thead { display: none; }
      tbody tr { padding: 12px; border-bottom: 1px solid var(--line); }
      td { border: 0; padding: 6px 0; }
      td::before {
        content: attr(data-label);
        display: block;
        color: var(--muted);
        font-size: 11px;
        font-weight: 800;
        text-transform: uppercase;
        margin-bottom: 4px;
      }
      .snapshot { width: 100%; max-width: 360px; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <header>
      <div>
        <h1>Zimbabwe ANPR Dashboard</h1>
        <div class="subtle" id="lastUpdated">Waiting for detections...</div>
      </div>
      <div class="toolbar">
        <input id="search" type="search" placeholder="Search plate or vehicle">
        <select id="status">
          <option value="">All statuses</option>
          <option value="NORMAL">Normal</option>
          <option value="BLACKLISTED">Blacklisted</option>
        </select>
        <button id="refresh">Refresh</button>
      </div>
    </header>

    <section class="stats">
      <div class="stat"><span>Total detections</span><strong id="total">0</strong></div>
      <div class="stat"><span>Normal</span><strong id="normal">0</strong></div>
      <div class="stat"><span>Blacklisted</span><strong id="blacklisted">0</strong></div>
      <div class="stat"><span>Latest plate</span><strong id="latest">-</strong></div>
    </section>

    <section class="panel">
      <table>
        <thead>
          <tr>
            <th style="width: 15%">Plate</th>
            <th style="width: 13%">Status</th>
            <th style="width: 18%">Time</th>
            <th style="width: 13%">Vehicle Type</th>
            <th style="width: 19%">Registration</th>
            <th style="width: 8%">Confidence</th>
            <th style="width: 14%">Snapshot</th>
          </tr>
        </thead>
        <tbody id="rows"></tbody>
      </table>
      <div class="empty" id="empty">No detections found yet. Run main.py and this table will fill automatically.</div>
    </section>
  </main>

  <div class="modal" id="modal" title="Click to close">
    <img id="modalImage" alt="Detection snapshot">
  </div>

  <script>
    const rowsEl = document.getElementById("rows");
    const emptyEl = document.getElementById("empty");
    const searchEl = document.getElementById("search");
    const statusEl = document.getElementById("status");
    const lastUpdatedEl = document.getElementById("lastUpdated");
    const modal = document.getElementById("modal");
    const modalImage = document.getElementById("modalImage");

    let rows = [];

    function badgeClass(status) {
      if (status === "NORMAL") return "normal";
      if (status === "BLACKLISTED") return "blacklisted";
      return "other";
    }

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;"
      }[char]));
    }

    function render() {
      const query = searchEl.value.trim().toLowerCase();
      const status = statusEl.value;
      const filtered = rows.filter(row => {
        const text = `${row.plate} ${row.vehicle_type}`.toLowerCase();
        return (!query || text.includes(query)) && (!status || row.status === status);
      });

      rowsEl.innerHTML = filtered.map(row => {
        const snapshot = row.snapshot_url
          ? `<img class="snapshot" src="${escapeHtml(row.snapshot_url)}" alt="${escapeHtml(row.plate)} snapshot" data-full="${escapeHtml(row.snapshot_url)}">`
          : `<span class="subtle">No snapshot</span>`;
        const owner = row.owner || {};

        return `<tr>
          <td data-label="Plate"><span class="plate">${escapeHtml(row.plate)}</span></td>
          <td data-label="Status"><span class="badge ${badgeClass(row.status)}">${escapeHtml(row.status)}</span></td>
          <td data-label="Time">${escapeHtml(row.time)}</td>
          <td data-label="Vehicle Type">${escapeHtml(row.vehicle_type || "-")}</td>
          <td data-label="Registration">
            <div class="owner">
              <strong>Registered: ${escapeHtml(owner.registered || "YES")}</strong>
              <small>${escapeHtml(owner.owner_name || "-")} | ${escapeHtml(owner.owner_type || "-")}</small>
              <small>${escapeHtml(owner.registration_number || "-")} | ${escapeHtml(owner.owner_city || "-")}</small>
              <small>${escapeHtml(owner.data_source || "Demo registry")}</small>
            </div>
          </td>
          <td data-label="Confidence">${escapeHtml(row.confidence ?? "-")}%</td>
          <td data-label="Snapshot">${snapshot}</td>
        </tr>`;
      }).join("");

      emptyEl.style.display = filtered.length ? "none" : "block";

      document.getElementById("total").textContent = rows.length;
      document.getElementById("normal").textContent = rows.filter(row => row.status === "NORMAL").length;
      document.getElementById("blacklisted").textContent = rows.filter(row => row.status === "BLACKLISTED").length;
      document.getElementById("latest").textContent = rows[0]?.plate || "-";
    }

    async function loadRows() {
      const response = await fetch("/api/plates?limit=200", { cache: "no-store" });
      rows = await response.json();
      lastUpdatedEl.textContent = `Last updated ${new Date().toLocaleTimeString()}`;
      render();
    }

    rowsEl.addEventListener("click", event => {
      const target = event.target;
      if (target.classList.contains("snapshot")) {
        modalImage.src = target.dataset.full;
        modal.classList.add("open");
      }
    });

    modal.addEventListener("click", () => modal.classList.remove("open"));
    searchEl.addEventListener("input", render);
    statusEl.addEventListener("change", render);
    document.getElementById("refresh").addEventListener("click", loadRows);

    loadRows();
    setInterval(loadRows, 3000);
  </script>
</body>
</html>
"""


class DashboardServer(ThreadingHTTPServer):
    def __init__(self, address: Tuple[str, int], db_path: Path, snapshot_dir: Path) -> None:
        super().__init__(address, DashboardHandler)
        self.db_path = db_path
        self.snapshot_dir = snapshot_dir.resolve()


class DashboardHandler(BaseHTTPRequestHandler):
    server: DashboardServer

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_bytes(HTML.encode("utf-8"), "text/html; charset=utf-8")
            return

        if parsed.path == "/api/plates":
            params = parse_qs(parsed.query)
            limit = safe_int(params.get("limit", ["200"])[0], 200)
            self.send_json(self.get_plates(max(1, min(limit, 1000))))
            return

        if parsed.path.startswith("/snapshots/"):
            self.serve_snapshot(parsed.path.removeprefix("/snapshots/"))
            return

        self.send_error(404, "Not found")

    def log_message(self, format: str, *args: Any) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {self.address_string()} {format % args}")

    def get_plates(self, limit: int) -> List[Dict[str, Any]]:
        if not self.server.db_path.exists():
            return []

        conn = sqlite3.connect(self.server.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT id, plate, vehicle_type, confidence, time, image_path, status, track_id
                FROM plates
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = conn.execute(
                """
                SELECT id, plate, vehicle_type, confidence, time, image_path, status
                FROM plates
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        finally:
            conn.close()

        return [self.row_to_payload(row) for row in rows]

    def row_to_payload(self, row: sqlite3.Row) -> Dict[str, Any]:
        image_path = row["image_path"] or ""
        snapshot_url = self.snapshot_url(image_path)
        payload = {
            "id": row["id"],
            "plate": row["plate"],
            "vehicle_type": row["vehicle_type"],
            "confidence": row["confidence"],
            "time": row["time"],
            "image_path": image_path,
            "snapshot_url": snapshot_url,
            "status": row["status"],
            "owner": demo_owner_for_plate(row["plate"]),
        }
        if "track_id" in row.keys():
            payload["track_id"] = row["track_id"]
        return payload

    def snapshot_url(self, image_path: str) -> str:
        if not image_path:
            return ""
        name = Path(image_path).name
        candidate = self.server.snapshot_dir / name
        if not candidate.exists():
            return ""
        return f"/snapshots/{name}"

    def serve_snapshot(self, raw_name: str) -> None:
        name = Path(unquote(raw_name)).name
        path = (self.server.snapshot_dir / name).resolve()

        if self.server.snapshot_dir not in path.parents and path != self.server.snapshot_dir:
            self.send_error(403, "Forbidden")
            return

        if not path.exists() or not path.is_file():
            self.send_error(404, "Snapshot not found")
            return

        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_bytes(path.read_bytes(), content_type)

    def send_json(self, payload: Any) -> None:
        self.send_bytes(json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

    def send_bytes(self, body: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def safe_int(value: str, fallback: int) -> int:
    try:
        return int(value)
    except ValueError:
        return fallback


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dashboard for the Zimbabwe ANPR detector")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--db", default=DEFAULT_DB_PATH)
    parser.add_argument("--snapshots", default=DEFAULT_SNAPSHOT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db)
    snapshot_dir = Path(args.snapshots)
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    server = DashboardServer((args.host, args.port), db_path, snapshot_dir)
    print(f"Dashboard running at http://{args.host}:{args.port}")
    print(f"Reading database: {db_path.resolve()}")
    print(f"Serving snapshots: {snapshot_dir.resolve()}")
    server.serve_forever()


if __name__ == "__main__":
    main()
