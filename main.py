import argparse
import csv
import os
import re
import sqlite3
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Deque, Dict, Iterable, List, Optional, Tuple

import cv2
import easyocr
import numpy as np
from ultralytics import YOLO


ZIM_PLATE_RE = re.compile(r"[A-Z]{3}[0-9]{4}")


@dataclass(frozen=True)
class AppConfig:
    video_source: str = "0524.mp4"
    vehicle_model_path: str = "vehicle_best.pt"
    plate_model_path: str = "plate_best.pt"
    database_path: str = "plates.db"
    csv_path: str = "detected_plates.csv"
    snapshot_dir: str = "snapshots"
    output_video: Optional[str] = None
    vehicle_conf: float = 0.35
    plate_conf: float = 0.45
    imgsz: int = 640
    plate_padding: int = 14
    min_plate_width: int = 42
    min_plate_height: int = 14
    vote_threshold: int = 3
    vote_window: int = 8
    ocr_every_n_frames: int = 3
    duplicate_cooldown_seconds: int = 10
    display: bool = True
    save_snapshots: bool = True
    use_gpu_ocr: bool = False


@dataclass
class Detection:
    xyxy: Tuple[int, int, int, int]
    confidence: float
    class_id: int = 0
    track_id: int = -1


@dataclass
class TrackState:
    votes: Deque[str]
    best_plate: str = ""
    best_count: int = 0
    last_ocr_frame: int = -9999
    last_saved_time: float = 0.0


BLACKLIST = {
    "AGG 7148",
    "ABC 1234",
    "ADE 3450",
    "AGC 4483",
}


def parse_args() -> AppConfig:
    parser = argparse.ArgumentParser(description="Zimbabwe ANPR system using YOLO + EasyOCR")
    parser.add_argument("--video", default=AppConfig.video_source, help="Video file, camera index, or stream URL")
    parser.add_argument("--vehicle-model", default=AppConfig.vehicle_model_path)
    parser.add_argument("--plate-model", default=AppConfig.plate_model_path)
    parser.add_argument("--db", default=AppConfig.database_path)
    parser.add_argument("--csv", default=AppConfig.csv_path)
    parser.add_argument("--snapshots", default=AppConfig.snapshot_dir)
    parser.add_argument("--output-video", default=None)
    parser.add_argument("--vehicle-conf", type=float, default=AppConfig.vehicle_conf)
    parser.add_argument("--plate-conf", type=float, default=AppConfig.plate_conf)
    parser.add_argument("--imgsz", type=int, default=AppConfig.imgsz)
    parser.add_argument("--ocr-every", type=int, default=AppConfig.ocr_every_n_frames)
    parser.add_argument("--vote-threshold", type=int, default=AppConfig.vote_threshold)
    parser.add_argument("--cooldown", type=int, default=AppConfig.duplicate_cooldown_seconds)
    parser.add_argument("--gpu-ocr", action="store_true", help="Enable EasyOCR GPU mode")
    parser.add_argument("--no-display", action="store_true", help="Run without cv2.imshow")
    args = parser.parse_args()

    return AppConfig(
        video_source=args.video,
        vehicle_model_path=args.vehicle_model,
        plate_model_path=args.plate_model,
        database_path=args.db,
        csv_path=args.csv,
        snapshot_dir=args.snapshots,
        output_video=args.output_video,
        vehicle_conf=args.vehicle_conf,
        plate_conf=args.plate_conf,
        imgsz=args.imgsz,
        ocr_every_n_frames=max(1, args.ocr_every),
        vote_threshold=max(1, args.vote_threshold),
        duplicate_cooldown_seconds=max(1, args.cooldown),
        display=not args.no_display,
        use_gpu_ocr=args.gpu_ocr,
    )


def open_video(source: str) -> cv2.VideoCapture:
    if source.isdigit():
        return cv2.VideoCapture(int(source))
    return cv2.VideoCapture(source)


def init_database(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS plates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plate TEXT NOT NULL,
            vehicle_type TEXT,
            confidence INTEGER,
            time TEXT NOT NULL,
            image_path TEXT,
            status TEXT NOT NULL,
            track_id INTEGER
        )
        """
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(plates)").fetchall()}
    if "track_id" not in columns:
        conn.execute("ALTER TABLE plates ADD COLUMN track_id INTEGER")
    conn.commit()
    return conn


def init_csv(path: str) -> None:
    if os.path.exists(path):
        return
    with open(path, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["Plate", "Vehicle_Type", "Confidence", "Time", "Image_Path", "Status", "Track_ID"])


def sanitize_for_zimbabwe_plate(raw_text: str) -> Optional[str]:
    compact = re.sub(r"[^A-Z0-9]", "", raw_text.upper())
    candidates = []

    for start in range(max(1, len(compact) - 6)):
        chunk = compact[start : start + 7]
        if len(chunk) == 7:
            candidates.append(chunk)

    if len(compact) == 7:
        candidates.insert(0, compact)

    letter_map = str.maketrans({"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z"})
    digit_map = str.maketrans({"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "S": "5", "B": "8", "Z": "2"})

    for candidate in candidates:
        normalized = candidate[:3].translate(letter_map) + candidate[3:].translate(digit_map)
        match = ZIM_PLATE_RE.search(normalized)
        if match:
            value = match.group()
            return f"{value[:3]} {value[3:]}"

    match = ZIM_PLATE_RE.search(compact)
    if match:
        value = match.group()
        return f"{value[:3]} {value[3:]}"

    return None


def preprocess_plate_for_ocr(plate_img: np.ndarray) -> List[np.ndarray]:
    gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
    scale = 3 if max(gray.shape[:2]) < 180 else 2
    gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    denoised = cv2.bilateralFilter(clahe, 7, 55, 55)
    _, otsu = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    adaptive = cv2.adaptiveThreshold(
        denoised,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        7,
    )
    return [denoised, otsu, adaptive]


def read_plate(reader: easyocr.Reader, plate_img: np.ndarray) -> Optional[str]:
    best_text = ""
    best_score = -1.0

    for variant in preprocess_plate_for_ocr(plate_img):
        results = reader.readtext(
            variant,
            detail=1,
            paragraph=False,
            decoder="greedy",
            allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
            width_ths=0.7,
            contrast_ths=0.1,
            adjust_contrast=0.7,
        )
        text = "".join(item[1] for item in results)
        score = float(np.mean([item[2] for item in results])) if results else 0.0
        normalized = sanitize_for_zimbabwe_plate(text)
        if normalized and score > best_score:
            best_text = normalized
            best_score = score

    return best_text or None


def yolo_detections(result, with_tracks: bool = False) -> List[Detection]:
    if result.boxes is None or len(result.boxes) == 0:
        return []

    boxes = result.boxes.xyxy.cpu().numpy()
    confs = result.boxes.conf.cpu().numpy()
    classes = result.boxes.cls.cpu().numpy() if result.boxes.cls is not None else np.zeros(len(boxes))
    ids = result.boxes.id.cpu().numpy() if with_tracks and result.boxes.id is not None else np.full(len(boxes), -1)

    detections = []
    for box, conf, cls, track_id in zip(boxes, confs, classes, ids):
        x1, y1, x2, y2 = map(int, box)
        detections.append(Detection((x1, y1, x2, y2), float(conf), int(cls), int(track_id)))
    return detections


def center_inside(inner: Detection, outer: Detection) -> bool:
    x1, y1, x2, y2 = inner.xyxy
    ox1, oy1, ox2, oy2 = outer.xyxy
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2
    return ox1 <= cx <= ox2 and oy1 <= cy <= oy2


def pad_box(
    xyxy: Tuple[int, int, int, int],
    pad: int,
    frame_shape: Tuple[int, int, int],
) -> Tuple[int, int, int, int]:
    x1, y1, x2, y2 = xyxy
    height, width = frame_shape[:2]
    return max(0, x1 - pad), max(0, y1 - pad), min(width, x2 + pad), min(height, y2 + pad)


def valid_plate_size(det: Detection, config: AppConfig) -> bool:
    x1, y1, x2, y2 = det.xyxy
    return (x2 - x1) >= config.min_plate_width and (y2 - y1) >= config.min_plate_height


def choose_vehicle_for_plate(plate: Detection, vehicles: Iterable[Detection]) -> Optional[Detection]:
    containing = [vehicle for vehicle in vehicles if center_inside(plate, vehicle)]
    if not containing:
        return None
    return min(containing, key=lambda vehicle: box_area(vehicle.xyxy))


def box_area(xyxy: Tuple[int, int, int, int]) -> int:
    x1, y1, x2, y2 = xyxy
    return max(0, x2 - x1) * max(0, y2 - y1)


def model_class_name(model: YOLO, class_id: int) -> str:
    names = getattr(model, "names", {})
    if isinstance(names, dict):
        return names.get(class_id, str(class_id))
    if 0 <= class_id < len(names):
        return names[class_id]
    return str(class_id)


def update_votes(state: TrackState, plate_text: str, config: AppConfig) -> None:
    state.votes.append(plate_text)
    counter = Counter(state.votes)
    state.best_plate, state.best_count = counter.most_common(1)[0]


def should_save(state: TrackState, config: AppConfig) -> bool:
    enough_votes = state.best_count >= config.vote_threshold
    cooldown_ok = (time.time() - state.last_saved_time) >= config.duplicate_cooldown_seconds
    return enough_votes and cooldown_ok


def save_detection(
    conn: sqlite3.Connection,
    config: AppConfig,
    frame: np.ndarray,
    plate_text: str,
    vehicle_type: str,
    confidence: int,
    track_id: int,
) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "BLACKLISTED" if plate_text in BLACKLIST else "NORMAL"
    image_path = ""

    if config.save_snapshots:
        Path(config.snapshot_dir).mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{plate_text.replace(' ', '_')}_{track_id}_{timestamp}.jpg"
        image_path = str(Path(config.snapshot_dir) / filename)
        cv2.imwrite(image_path, frame)

    conn.execute(
        """
        INSERT INTO plates (plate, vehicle_type, confidence, time, image_path, status, track_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (plate_text, vehicle_type, confidence, now, image_path, status, track_id),
    )
    conn.commit()

    with open(config.csv_path, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([plate_text, vehicle_type, confidence, now, image_path, status, track_id])

    print(f"SAVED: {plate_text} | {vehicle_type} | {confidence}% | {status}")


def draw_label(frame: np.ndarray, text: str, origin: Tuple[int, int], color: Tuple[int, int, int]) -> None:
    x, y = origin
    y = max(24, y)
    cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2, cv2.LINE_AA)


def draw_detection(frame: np.ndarray, xyxy: Tuple[int, int, int, int], label: str, color: Tuple[int, int, int], thickness: int = 2) -> None:
    x1, y1, x2, y2 = xyxy
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
    draw_label(frame, label, (x1, y1 - 8), color)


def make_video_writer(config: AppConfig, cap: cv2.VideoCapture) -> Optional[cv2.VideoWriter]:
    if not config.output_video:
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    return cv2.VideoWriter(config.output_video, fourcc, fps, (width, height))


def main() -> None:
    config = parse_args()
    Path(config.snapshot_dir).mkdir(parents=True, exist_ok=True)
    init_csv(config.csv_path)

    vehicle_model = YOLO(config.vehicle_model_path)
    plate_model = YOLO(config.plate_model_path)
    reader = easyocr.Reader(["en"], gpu=config.use_gpu_ocr)

    conn = init_database(config.database_path)
    cap = open_video(config.video_source)

    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video source: {config.video_source}")

    writer = make_video_writer(config, cap)
    track_states: Dict[int, TrackState] = defaultdict(lambda: TrackState(deque(maxlen=config.vote_window)))
    frame_index = 0
    fps_started = time.time()

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            frame_index += 1
            annotated = frame.copy()

            vehicle_result = vehicle_model.track(
                frame,
                persist=True,
                conf=config.vehicle_conf,
                imgsz=config.imgsz,
                verbose=False,
            )[0]
            plate_result = plate_model(
                frame,
                conf=config.plate_conf,
                imgsz=config.imgsz,
                verbose=False,
            )[0]

            vehicles = yolo_detections(vehicle_result, with_tracks=True)
            plates = [det for det in yolo_detections(plate_result) if valid_plate_size(det, config)]

            for vehicle in vehicles:
                vehicle_type = model_class_name(vehicle_model, vehicle.class_id)
                vehicle_label = f"ID {vehicle.track_id} {vehicle_type} {int(vehicle.confidence * 100)}%"
                draw_detection(annotated, vehicle.xyxy, vehicle_label, (255, 0, 0), 2)

            for plate in plates:
                vehicle = choose_vehicle_for_plate(plate, vehicles)
                if vehicle is None:
                    continue

                track_id = vehicle.track_id if vehicle.track_id >= 0 else box_area(vehicle.xyxy)
                state = track_states[track_id]
                x1, y1, x2, y2 = pad_box(plate.xyxy, config.plate_padding, frame.shape)
                plate_img = frame[y1:y2, x1:x2]

                if plate_img.size and frame_index - state.last_ocr_frame >= config.ocr_every_n_frames:
                    state.last_ocr_frame = frame_index
                    plate_text = read_plate(reader, plate_img)
                    if plate_text:
                        update_votes(state, plate_text, config)
                        print(f"OCR: {plate_text} | track={track_id} | votes={state.best_count}")

                display_plate = state.best_plate or "PLATE"
                is_blacklisted = state.best_plate in BLACKLIST
                plate_color = (0, 0, 255) if is_blacklisted else (0, 255, 0)
                plate_label = f"{display_plate} {int(plate.confidence * 100)}%"
                draw_detection(annotated, (x1, y1, x2, y2), plate_label, plate_color, 2)

                if state.best_plate and should_save(state, config):
                    vehicle_type = model_class_name(vehicle_model, vehicle.class_id)
                    save_detection(
                        conn,
                        config,
                        annotated,
                        state.best_plate,
                        vehicle_type,
                        int(plate.confidence * 100),
                        track_id,
                    )
                    state.last_saved_time = time.time()

            elapsed = max(0.001, time.time() - fps_started)
            fps = frame_index / elapsed
            draw_label(annotated, f"FPS {fps:.1f}", (12, 28), (0, 255, 255))

            if writer is not None:
                writer.write(annotated)

            if config.display:
                cv2.imshow("Zimbabwe ANPR System", annotated)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

    finally:
        cap.release()
        if writer is not None:
            writer.release()
        conn.close()
        if config.display:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
