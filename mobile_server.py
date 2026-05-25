import argparse
import csv
import cgi
import json
import mimetypes
import os
import socket
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import unquote, urlparse

import cv2
import numpy as np
import easyocr
from ultralytics import YOLO

from owner_registry import demo_owner_for_plate
from main import (
    AppConfig,
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
)


HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Phone ANPR Capture</title>
  <style>
    :root {
      --bg: #f3f6f9;
      --panel: #ffffff;
      --ink: #17202a;
      --muted: #667085;
      --line: #d7dde6;
      --green: #11845b;
      --red: #b42318;
      --blue: #175cd3;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Arial, Helvetica, sans-serif;
    }

    main {
      width: min(720px, calc(100% - 28px));
      margin: 0 auto;
      padding: 22px 0 34px;
    }

    h1 {
      margin: 0 0 6px;
      font-size: 26px;
      line-height: 1.15;
    }

    .subtle {
      color: var(--muted);
      font-size: 14px;
      line-height: 1.45;
    }

    .panel {
      margin-top: 18px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      box-shadow: 0 12px 34px rgba(16, 24, 40, 0.08);
    }

    input[type="file"] {
      width: 100%;
      border: 1px dashed #98a2b3;
      border-radius: 8px;
      background: #f8fafc;
      padding: 18px;
      font-size: 15px;
    }

    button {
      width: 100%;
      min-height: 46px;
      margin-top: 12px;
      border: 0;
      border-radius: 7px;
      background: var(--ink);
      color: white;
      font-size: 16px;
      font-weight: 800;
      cursor: pointer;
    }

    button:disabled {
      opacity: 0.55;
      cursor: wait;
    }

    .preview {
      width: 100%;
      max-height: 360px;
      object-fit: contain;
      margin-top: 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #eef2f6;
      display: none;
    }

    .result {
      display: grid;
      gap: 10px;
      margin-top: 16px;
    }

    .card {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      background: #fff;
    }

    .plate {
      font-size: 28px;
      font-weight: 900;
      letter-spacing: 1px;
      margin-bottom: 8px;
    }

    .status {
      display: inline-block;
      border-radius: 999px;
      padding: 5px 10px;
      font-size: 12px;
      font-weight: 900;
      margin-bottom: 12px;
    }

    .status.normal {
      color: var(--green);
      background: #def7ec;
    }

    .status.blacklisted {
      color: var(--red);
      background: #fee4e2;
    }

    dl {
      display: grid;
      grid-template-columns: 120px 1fr;
      gap: 8px 12px;
      margin: 0;
      font-size: 14px;
    }

    dt {
      color: var(--muted);
      font-weight: 800;
    }

    dd { margin: 0; }

    .snapshot {
      width: 100%;
      margin-top: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
    }
  </style>
</head>
<body>
  <main>
    <h1>Phone ANPR Capture</h1>
    <div class="subtle">Take a photo of a vehicle number plate or choose one from your gallery. Detection runs on your laptop/server.</div>

    <section class="panel">
      <form id="form">
        <input id="token" name="token" type="password" placeholder="Access token, if required" autocomplete="current-password">
        <input id="image" name="image" type="file" accept="image/*" capture="environment" required>
        <button id="button" type="submit">Detect Plate</button>
      </form>
      <img id="preview" class="preview" alt="Selected image preview">
      <div id="message" class="subtle" style="margin-top: 12px;"></div>
      <div id="result" class="result"></div>
    </section>
  </main>

  <script>
    const form = document.getElementById("form");
    const image = document.getElementById("image");
    const token = document.getElementById("token");
    const button = document.getElementById("button");
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

    function renderDetections(data) {
      if (!data.detections.length) {
        result.innerHTML = "";
        message.textContent = "No valid Zimbabwe plate was detected. Try a sharper, closer photo with less angle.";
        return;
      }

      message.textContent = `${data.detections.length} plate result(s) found.`;
      result.innerHTML = data.detections.map(item => {
        const statusClass = item.status === "BLACKLISTED" ? "blacklisted" : "normal";
        const snapshot = item.snapshot_url ? `<img class="snapshot" src="${escapeHtml(item.snapshot_url)}" alt="Detection snapshot">` : "";
        return `<article class="card">
          <div class="plate">${escapeHtml(item.plate)}</div>
          <span class="status ${statusClass}">${escapeHtml(item.status)}</span>
          <dl>
            <dt>Vehicle</dt><dd>${escapeHtml(item.vehicle_type || "-")}</dd>
            <dt>Registered</dt><dd>${escapeHtml(item.owner?.registered || "YES")}</dd>
            <dt>Owner</dt><dd>${escapeHtml(item.owner?.owner_name || "-")}</dd>
            <dt>Owner Type</dt><dd>${escapeHtml(item.owner?.owner_type || "-")}</dd>
            <dt>Reg Number</dt><dd>${escapeHtml(item.owner?.registration_number || "-")}</dd>
            <dt>City</dt><dd>${escapeHtml(item.owner?.owner_city || "-")}</dd>
            <dt>Confidence</dt><dd>${escapeHtml(item.confidence)}%</dd>
            <dt>Time</dt><dd>${escapeHtml(item.time)}</dd>
          </dl>
          ${snapshot}
        </article>`;
      }).join("");
    }

    form.addEventListener("submit", async event => {
      event.preventDefault();
      if (!image.files[0]) return;

      button.disabled = true;
      button.textContent = "Detecting...";
      message.textContent = "Uploading image and running detection...";
      result.innerHTML = "";

      try {
        const formData = new FormData();
        formData.append("image", image.files[0]);
        if (token.value.trim()) {
          formData.append("token", token.value.trim());
        }
        const response = await fetch("/detect", { method: "POST", body: formData });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Detection failed");
        renderDetections(data);
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


class PhoneDetector:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        print(f"📦 Loading vehicle model from {config.vehicle_model_path}")
        self.vehicle_model = YOLO(config.vehicle_model_path)
        print(f"📦 Loading plate model from {config.plate_model_path}")
        self.plate_model = YOLO(config.plate_model_path)
        print("📚 Loading EasyOCR (this may take a moment)...")
        self.reader = easyocr.Reader(["en"], gpu=config.use_gpu_ocr)
        print("✅ All models loaded successfully")
        init_database(config.database_path).close()
        init_csv(config.csv_path)
        Path(config.snapshot_dir).mkdir(parents=True, exist_ok=True)

    def detect(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        annotated = frame.copy()
        vehicle_result = self.vehicle_model(
            frame,
            conf=self.config.vehicle_conf,
            imgsz=self.config.imgsz,
            verbose=False,
        )[0]
        plate_result = self.plate_model(
            frame,
            conf=self.config.plate_conf,
            imgsz=self.config.imgsz,
            verbose=False,
        )[0]

        vehicles = yolo_detections(vehicle_result)
        plates = [det for det in yolo_detections(plate_result) if valid_plate_size(det, self.config)]
        detections: List[Dict[str, Any]] = []

        for vehicle in vehicles:
            vehicle_type = model_class_name(self.vehicle_model, vehicle.class_id)
            label = f"{vehicle_type} {int(vehicle.confidence * 100)}%"
            draw_detection(annotated, vehicle.xyxy, label, (255, 0, 0), 2)

        for index, plate in enumerate(plates, start=1):
            vehicle = choose_vehicle_for_plate(plate, vehicles)
            vehicle_type = "UNKNOWN"
            if vehicle is not None:
                vehicle_type = model_class_name(self.vehicle_model, vehicle.class_id)

            x1, y1, x2, y2 = pad_box(plate.xyxy, self.config.plate_padding, frame.shape)
            plate_img = frame[y1:y2, x1:x2]
            if plate_img.size == 0:
                continue

            plate_text = read_plate(self.reader, plate_img)
            if not plate_text:
                draw_detection(annotated, (x1, y1, x2, y2), "PLATE", (0, 255, 255), 2)
                continue

            status = "BLACKLISTED" if plate_text in BLACKLIST else "NORMAL"
            color = (0, 0, 255) if status == "BLACKLISTED" else (0, 255, 0)
            confidence = int(plate.confidence * 100)
            draw_detection(annotated, (x1, y1, x2, y2), f"{plate_text} {confidence}%", color, 2)
            detections.append(
                self.save_detection(
                    annotated,
                    plate_text,
                    vehicle_type,
                    confidence,
                    index,
                    status,
                )
            )

        if not detections:
            draw_label(annotated, "No valid plate detected", (12, 30), (0, 255, 255))

        return detections

    def save_detection(
        self,
        annotated: np.ndarray,
        plate_text: str,
        vehicle_type: str,
        confidence: int,
        index: int,
        status: str,
    ) -> Dict[str, Any]:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"phone_{plate_text.replace(' ', '_')}_{index}_{timestamp}.jpg"
        image_path = str(Path(self.config.snapshot_dir) / filename)
        cv2.imwrite(image_path, annotated)

        conn = init_database(self.config.database_path)
        try:
            conn.execute(
                """
                INSERT INTO plates (plate, vehicle_type, confidence, time, image_path, status, track_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (plate_text, vehicle_type, confidence, now, image_path, status, 0),
            )
            conn.commit()
        finally:
            conn.close()

        with open(self.config.csv_path, mode="a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([plate_text, vehicle_type, confidence, now, image_path, status, 0])

        return {
            "plate": plate_text,
            "vehicle_type": vehicle_type,
            "confidence": confidence,
            "time": now,
            "status": status,
            "image_path": image_path,
            "snapshot_url": f"/snapshots/{Path(image_path).name}",
            "owner": demo_owner_for_plate(plate_text),
        }


class MobileServer(ThreadingHTTPServer):
    def __init__(self, address: Tuple[str, int], detector: PhoneDetector) -> None:
        super().__init__(address, MobileHandler)
        self.detector = detector
        self.snapshot_dir = Path(detector.config.snapshot_dir).resolve()


class MobileHandler(BaseHTTPRequestHandler):
    server: MobileServer

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_bytes(HTML.encode("utf-8"), "text/html; charset=utf-8")
            return

        if parsed.path.startswith("/snapshots/"):
            self.serve_snapshot(parsed.path.removeprefix("/snapshots/"))
            return

        self.send_error(404, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/detect":
            self.send_error(404, "Not found")
            return

        try:
            upload = self.read_upload()
            self.require_valid_token(upload.get("token", ""))
            image_bytes = upload["image"]
            frame = decode_image(image_bytes)
            started = time.time()
            detections = self.server.detector.detect(frame)
            self.send_json(
                {
                    "detections": detections,
                    "processing_seconds": round(time.time() - started, 2),
                }
            )
        except ValueError as exc:
            self.send_json({"error": str(exc)}, status=400)
        except Exception as exc:
            self.send_json({"error": f"Server error: {exc}"}, status=500)

    def read_upload(self) -> Dict[str, Any]:
        content_type = self.headers.get("Content-Type", "")
        token = ""
        # Fix for Python 3.11+ compatibility
        if content_type.startswith("multipart/form-data"):
            try:
                # Try newer method first
                import email
                import io
                # Parse multipart manually for better compatibility
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={
                        "REQUEST_METHOD": "POST",
                        "CONTENT_TYPE": content_type,
                    },
                )
                if "image" not in form:
                    raise ValueError("Upload field must be named image.")
                field = form["image"]
                data = field.file.read()
                if "token" in form:
                    token = str(form["token"].value)
            except Exception as e:
                # Fallback: read raw data
                length = int(self.headers.get("Content-Length", "0"))
                data = self.rfile.read(length)
        else:
            length = int(self.headers.get("Content-Length", "0"))
            data = self.rfile.read(length)

        if not data:
            raise ValueError("No image was uploaded.")
        return {"image": data, "token": token}

    def require_valid_token(self, token: str) -> None:
        expected = os.getenv("ANPR_TOKEN", "").strip()
        if expected and token != expected:
            raise ValueError("Invalid access token.")

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

    def send_json(self, payload: Any, status: int = 200) -> None:
        self.send_bytes(json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8", status)

    def send_bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {self.address_string()} {format % args}")


def decode_image(image_bytes: bytes) -> np.ndarray:
    array = np.frombuffer(image_bytes, dtype=np.uint8)
    frame = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Uploaded file is not a valid image.")
    return frame


def local_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        address = sock.getsockname()[0]
        sock.close()
        return address
    except OSError:
        return "127.0.0.1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phone upload server for Zimbabwe ANPR")
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8090")))
    parser.add_argument("--vehicle-model", default=os.getenv("VEHICLE_MODEL", "vehicle_best.pt"))
    parser.add_argument("--plate-model", default=os.getenv("PLATE_MODEL", "plate_best.pt"))
    parser.add_argument("--db", default=os.getenv("DB_PATH", "plates.db"))
    parser.add_argument("--csv", default=os.getenv("CSV_PATH", "detected_plates.csv"))
    parser.add_argument("--snapshots", default=os.getenv("SNAPSHOT_DIR", "snapshots"))
    parser.add_argument("--vehicle-conf", type=float, default=float(os.getenv("VEHICLE_CONF", "0.35")))
    parser.add_argument("--plate-conf", type=float, default=float(os.getenv("PLATE_CONF", "0.45")))
    parser.add_argument("--imgsz", type=int, default=int(os.getenv("IMGSZ", "640")))
    parser.add_argument("--gpu-ocr", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    
    # Create AppConfig with proper settings for mobile server
    config = AppConfig(
        vehicle_model_path=args.vehicle_model,
        plate_model_path=args.plate_model,
        database_path=args.db,
        csv_path=args.csv,
        snapshot_dir=args.snapshots,
        vehicle_conf=args.vehicle_conf,
        plate_conf=args.plate_conf,
        imgsz=args.imgsz,
        display=False,  # No display needed for mobile server
        save_snapshots=True,
        use_gpu_ocr=args.gpu_ocr,
        video_source="",  # Not used in mobile server
        output_video=None,
        min_plate_width=42,
        min_plate_height=14,
        plate_padding=14,
        vote_threshold=3,
        vote_window=8,
        ocr_every_n_frames=3,
        duplicate_cooldown_seconds=10,
    )
    
    detector = PhoneDetector(config)
    server = MobileServer((args.host, args.port), detector)

    phone_url = f"http://{local_ip()}:{args.port}"
    public_url = os.getenv("PUBLIC_URL", "")
    
    print(f"\n{'='*60}")
    print(f"🚗 ANPR Mobile Server Started")
    print(f"{'='*60}")
    print(f"📍 Local access: {phone_url}")
    if public_url:
        print(f"🌍 Public URL: {public_url}")
    print(f"🔌 Port: {args.port}")
    print(f"📁 Snapshots dir: {config.snapshot_dir}")
    print(f"💾 Database: {config.database_path}")
    print(f"{'='*60}")
    print("Connect your phone to the same network, then open the URL above.")
    print("Press Ctrl+C to stop the server\n")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Shutting down server...")
        server.shutdown()


if __name__ == "__main__":
    main()