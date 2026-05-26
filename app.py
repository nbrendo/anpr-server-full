import argparse
import csv
import json
import mimetypes
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import cv2
import numpy as np
import easyocr
import pandas as pd
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from ultralytics import YOLO

from owner_registry import demo_owner_for_plate
from main import (
    BLACKLIST,
    choose_vehicle_for_plate,
    draw_detection,
    draw_label,
    init_csv,
    init_database,
    model_class_name,
    pad_box,
    read_plate,
    valid_plate_size,
    yolo_detections,
    AppConfig,
)

# Initialize FastAPI
app = FastAPI(title="ANPR System", description="Vehicle License Plate Detection and Dashboard")

# Configuration
PORT = int(os.environ.get("PORT", 8090))
DB_PATH = os.environ.get("DB_PATH", "plates.db")
SNAPSHOT_DIR = os.environ.get("SNAPSHOT_DIR", "snapshots")
VEHICLE_MODEL_PATH = os.environ.get("VEHICLE_MODEL", "vehicle_best.pt")
PLATE_MODEL_PATH = os.environ.get("PLATE_MODEL", "plate_best.pt")

# Create directories
Path(SNAPSHOT_DIR).mkdir(parents=True, exist_ok=True)

# Global variables for models
vehicle_model = None
plate_model = None
reader = None
config = None

# HTML templates
MOBILE_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ANPR - Upload & Detect</title>
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: #f3f6f9;
      font-family: Arial, Helvetica, sans-serif;
    }
    main {
      width: min(720px, calc(100% - 28px));
      margin: 0 auto;
      padding: 22px 0 34px;
    }
    h1 { margin: 0 0 6px; font-size: 26px; }
    .subtle { color: #667085; font-size: 14px; }
    .panel {
      margin-top: 18px;
      background: white;
      border: 1px solid #d7dde6;
      border-radius: 8px;
      padding: 16px;
    }
    input[type="file"] {
      width: 100%;
      border: 1px dashed #98a2b3;
      border-radius: 8px;
      padding: 18px;
    }
    button {
      width: 100%;
      min-height: 46px;
      margin-top: 12px;
      border: 0;
      border-radius: 7px;
      background: #17202a;
      color: white;
      font-size: 16px;
      font-weight: 800;
      cursor: pointer;
    }
    .preview {
      width: 100%;
      max-height: 360px;
      object-fit: contain;
      margin-top: 14px;
      border: 1px solid #d7dde6;
      border-radius: 8px;
      display: none;
    }
    .result { margin-top: 16px; }
    .card {
      border: 1px solid #d7dde6;
      border-radius: 8px;
      padding: 14px;
      background: #fff;
    }
    .plate { font-size: 28px; font-weight: 900; margin-bottom: 8px; }
    .status {
      display: inline-block;
      border-radius: 999px;
      padding: 5px 10px;
      font-size: 12px;
      font-weight: 900;
    }
    .normal { color: #11845b; background: #def7ec; }
    .blacklisted { color: #b42318; background: #fee4e2; }
    dl {
      display: grid;
      grid-template-columns: 120px 1fr;
      gap: 8px 12px;
      margin: 12px 0 0;
      font-size: 14px;
    }
    dt { color: #667085; font-weight: 800; }
    dd { margin: 0; }
    .nav-links {
      display: flex;
      gap: 16px;
      margin-bottom: 20px;
      padding: 12px 0;
      border-bottom: 1px solid #d7dde6;
    }
    .nav-links a {
      color: #175cd3;
      text-decoration: none;
      font-weight: 600;
    }
    .nav-links a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <main>
    <div class="nav-links">
      <a href="/">📸 Upload & Detect</a>
      <a href="/dashboard">📊 Dashboard</a>
    </div>
    <h1>ANPR Upload & Detect</h1>
    <div class="subtle">Upload a photo of a vehicle number plate for instant detection</div>
    <section class="panel">
      <form id="form">
        <input id="image" type="file" accept="image/*" capture="environment" required>
        <button type="submit">Detect Plate</button>
      </form>
      <img id="preview" class="preview" alt="Preview">
      <div id="message" class="subtle" style="margin-top: 12px;"></div>
      <div id="result" class="result"></div>
    </section>
  </main>
  <script>
    const form = document.getElementById("form");
    const image = document.getElementById("image");
    const button = document.querySelector("button");
    const preview = document.getElementById("preview");
    const message = document.getElementById("message");
    const result = document.getElementById("result");

    image.addEventListener("change", () => {
      const file = image.files[0];
      if (!file) return;
      preview.src = URL.createObjectURL(file);
      preview.style.display = "block";
      result.innerHTML = "";
      message.textContent = "";
    });

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;"
      }[char]));
    }

    form.addEventListener("submit", async event => {
      event.preventDefault();
      if (!image.files[0]) return;

      button.disabled = true;
      button.textContent = "Detecting...";
      message.textContent = "Processing...";
      result.innerHTML = "";

      try {
        const formData = new FormData();
        formData.append("image", image.files[0]);
        const response = await fetch("/detect", { method: "POST", body: formData });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Detection failed");
        
        if (!data.detections.length) {
          message.textContent = "No valid license plate detected.";
        } else {
          message.textContent = `${data.detections.length} plate(s) detected.`;
          result.innerHTML = data.detections.map(item => {
            const statusClass = item.status === "BLACKLISTED" ? "blacklisted" : "normal";
            return `<div class="card">
              <div class="plate">${escapeHtml(item.plate)}</div>
              <span class="status ${statusClass}">${escapeHtml(item.status)}</span>
              <dl>
                <dt>Vehicle</dt><dd>${escapeHtml(item.vehicle_type || "-")}</dd>
                <dt>Owner</dt><dd>${escapeHtml(item.owner?.owner_name || "-")}</dd>
                <dt>Owner Type</dt><dd>${escapeHtml(item.owner?.owner_type || "-")}</dd>
                <dt>Registered</dt><dd>${escapeHtml(item.owner?.registered || "YES")}</dd>
                <dt>Confidence</dt><dd>${escapeHtml(item.confidence)}%</dd>
              </dl>
            </div>`;
          }).join("");
        }
      } catch (error) {
        message.textContent = error.message;
      } finally {
        button.disabled = false;
        button.textContent = "Detect Plate";
      }
    });
  </script>
</body>
</html>
"""

DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ANPR Dashboard</title>
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: #f4f6f8;
      font-family: Arial, Helvetica, sans-serif;
    }
    .shell {
      width: min(1440px, calc(100% - 32px));
      margin: 0 auto;
      padding: 24px 0 40px;
    }
    .nav-links {
      display: flex;
      gap: 16px;
      margin-bottom: 20px;
      padding: 12px 0;
      border-bottom: 1px solid #d9dee7;
    }
    .nav-links a {
      color: #175cd3;
      text-decoration: none;
      font-weight: 600;
    }
    .nav-links a:hover { text-decoration: underline; }
    h1 { margin: 0; font-size: 28px; }
    .subtle { color: #667085; font-size: 14px; margin-top: 6px; }
    .toolbar {
      display: flex;
      gap: 10px;
      margin: 18px 0;
      flex-wrap: wrap;
    }
    input, select, button {
      height: 38px;
      border: 1px solid #d9dee7;
      border-radius: 6px;
      padding: 0 12px;
      font-size: 14px;
    }
    button {
      background: #17202a;
      color: white;
      font-weight: 700;
      cursor: pointer;
    }
    .stats {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin-bottom: 18px;
    }
    .stat {
      background: white;
      border: 1px solid #d9dee7;
      border-radius: 8px;
      padding: 14px 16px;
    }
    .stat span { color: #667085; font-size: 12px; font-weight: 700; }
    .stat strong { display: block; margin-top: 8px; font-size: 26px; }
    .panel {
      background: white;
      border: 1px solid #d9dee7;
      border-radius: 8px;
      overflow-x: auto;
    }
    table {
      width: 100%;
      border-collapse: collapse;
    }
    th, td {
      padding: 12px 14px;
      border-bottom: 1px solid #d9dee7;
      text-align: left;
      font-size: 14px;
    }
    th { background: #f8fafc; font-size: 12px; }
    .plate { font-weight: 800; font-size: 18px; }
    .badge {
      display: inline-block;
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 12px;
      font-weight: 800;
    }
    .badge.normal { color: #11845b; background: #def7ec; }
    .badge.blacklisted { color: #b42318; background: #fee4e2; }
    .empty { padding: 42px 20px; text-align: center; color: #667085; }
    @media (max-width: 768px) {
      th, td { display: block; }
      thead { display: none; }
      td { padding: 8px 12px; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <div class="nav-links">
      <a href="/">📸 Upload & Detect</a>
      <a href="/dashboard">📊 Dashboard</a>
    </div>
    <h1>Detection Dashboard</h1>
    <div class="subtle" id="lastUpdated">Loading...</div>
    
    <div class="stats">
      <div class="stat"><span>Total</span><strong id="total">0</strong></div>
      <div class="stat"><span>Normal</span><strong id="normal">0</strong></div>
      <div class="stat"><span>Blacklisted</span><strong id="blacklisted">0</strong></div>
      <div class="stat"><span>Latest</span><strong id="latest">-</strong></div>
    </div>

    <div class="toolbar">
      <input id="search" type="search" placeholder="Search plate...">
      <select id="status">
        <option value="">All</option>
        <option value="NORMAL">Normal</option>
        <option value="BLACKLISTED">Blacklisted</option>
      </select>
      <button id="refresh">Refresh</button>
    </div>

    <div class="panel">
      <table>
        <thead>
          <tr><th>Plate</th><th>Status</th><th>Time</th><th>Vehicle</th><th>Confidence</th><th>Owner</th></tr>
        </thead>
        <tbody id="rows"></tbody>
       </table>
      <div class="empty" id="empty">No detections yet. Upload a photo to get started!</div>
    </div>
  </main>
  <script>
    let rows = [];
    const searchEl = document.getElementById("search");
    const statusEl = document.getElementById("status");
    const lastUpdatedEl = document.getElementById("lastUpdated");
    
    function render() {
      const query = searchEl.value.trim().toLowerCase();
      const status = statusEl.value;
      const filtered = rows.filter(row => {
        const text = `${row.plate} ${row.vehicle_type}`.toLowerCase();
        return (!query || text.includes(query)) && (!status || row.status === status);
      });
      
      const tbody = document.getElementById("rows");
      tbody.innerHTML = filtered.map(row => `
        <tr>
          <td><span class="plate">${escapeHtml(row.plate)}</span></td>
          <td><span class="badge ${row.status === "BLACKLISTED" ? "blacklisted" : "normal"}">${escapeHtml(row.status)}</span></td>
          <td>${escapeHtml(row.time)}</td>
          <td>${escapeHtml(row.vehicle_type || "-")}</td>
          <td>${escapeHtml(row.confidence)}%</td>
          <td>${escapeHtml(row.owner?.owner_name || "-")}</td>
        </tr>
      `).join("");
      
      document.getElementById("empty").style.display = filtered.length ? "none" : "block";
      document.getElementById("total").textContent = rows.length;
      document.getElementById("normal").textContent = rows.filter(r => r.status === "NORMAL").length;
      document.getElementById("blacklisted").textContent = rows.filter(r => r.status === "BLACKLISTED").length;
      document.getElementById("latest").textContent = rows[0]?.plate || "-";
    }

    function escapeHtml(v) { return String(v ?? "").replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }

    async function loadData() {
      const response = await fetch("/api/plates?limit=100");
      rows = await response.json();
      lastUpdatedEl.textContent = `Last updated ${new Date().toLocaleTimeString()}`;
      render();
    }

    searchEl.addEventListener("input", render);
    statusEl.addEventListener("change", render);
    document.getElementById("refresh").addEventListener("click", loadData);
    loadData();
    setInterval(loadData, 5000);
  </script>
</body>
</html>
"""


# Initialize models on startup
@app.on_event("startup")
async def startup_event():
    global vehicle_model, plate_model, reader, config
    print("Loading models...")
    config = AppConfig(
        vehicle_model_path=VEHICLE_MODEL_PATH,
        plate_model_path=PLATE_MODEL_PATH,
        database_path=DB_PATH,
        csv_path="detected_plates.csv",
        snapshot_dir=SNAPSHOT_DIR,
        display=False,
        save_snapshots=True,
    )
    vehicle_model = YOLO(VEHICLE_MODEL_PATH)
    plate_model = YOLO(PLATE_MODEL_PATH)
    reader = easyocr.Reader(["en"], gpu=False)
    init_database(DB_PATH)
    init_csv("detected_plates.csv")
    print(f"✅ Models loaded. Server ready on port {PORT}")


# Mobile detection endpoint
@app.post("/detect")
async def detect_plate(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None:
            raise HTTPException(400, "Invalid image")
        
        # Run detection
        vehicle_result = vehicle_model(frame, conf=0.35, verbose=False)[0]
        plate_result = plate_model(frame, conf=0.45, verbose=False)[0]
        
        vehicles = yolo_detections(vehicle_result)
        plates = [det for det in yolo_detections(plate_result) if valid_plate_size(det, config)]
        
        detections = []
        for plate in plates:
            vehicle = choose_vehicle_for_plate(plate, vehicles)
            vehicle_type = model_class_name(vehicle_model, vehicle.class_id) if vehicle else "UNKNOWN"
            
            x1, y1, x2, y2 = pad_box(plate.xyxy, 14, frame.shape)
            plate_img = frame[y1:y2, x1:x2]
            if plate_img.size == 0:
                continue
            
            plate_text = read_plate(reader, plate_img)
            if not plate_text:
                continue
            
            status = "BLACKLISTED" if plate_text in BLACKLIST else "NORMAL"
            confidence = int(plate.confidence * 100)
            
            # Save to database
            conn = sqlite3.connect(DB_PATH)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                "INSERT INTO plates (plate, vehicle_type, confidence, time, image_path, status, track_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (plate_text, vehicle_type, confidence, now, "", status, 0)
            )
            conn.commit()
            conn.close()
            
            detections.append({
                "plate": plate_text,
                "vehicle_type": vehicle_type,
                "confidence": confidence,
                "time": now,
                "status": status,
                "owner": demo_owner_for_plate(plate_text),
            })
        
        return {"detections": detections, "count": len(detections)}
    except Exception as e:
        raise HTTPException(500, str(e))


# Dashboard endpoints
@app.get("/", response_class=HTMLResponse)
async def mobile_interface():
    return HTMLResponse(MOBILE_HTML)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_interface():
    return HTMLResponse(DASHBOARD_HTML)


@app.get("/api/plates")
async def get_plates(limit: int = 100):
    if not Path(DB_PATH).exists():
        return []
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, plate, vehicle_type, confidence, time, status FROM plates ORDER BY id DESC LIMIT ?",
        (min(limit, 500),)
    ).fetchall()
    conn.close()
    
    return [{
        "id": row["id"],
        "plate": row["plate"],
        "vehicle_type": row["vehicle_type"],
        "confidence": row["confidence"],
        "time": row["time"],
        "status": row["status"],
        "owner": demo_owner_for_plate(row["plate"]),
    } for row in rows]


@app.get("/health")
async def health():
    return {"status": "healthy", "port": PORT, "models_loaded": vehicle_model is not None}


if __name__ == "__main__":
    import uvicorn
    print(f"🚀 Starting ANPR Combined Server on port {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)