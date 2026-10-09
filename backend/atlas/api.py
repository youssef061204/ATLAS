import asyncio
import json
import logging
import os
import time
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

import cv2
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from prometheus_client import REGISTRY, Counter, Gauge, Histogram, generate_latest

from . import config, db, operations
from .geometry import Projection
from .observability import PipelineCollector
from .operations import router as operations_router
from .pipeline import probe, process_video
from .schemas import CameraConfig, IntersectionIn, SimulationConfig, StreamIn
from .simulation import optimize

log = logging.getLogger("atlas")
REQUESTS = Counter("atlas_requests_total", "HTTP requests", ["method", "route", "status"])
REQUEST_TIME = Histogram("atlas_request_seconds", "HTTP request latency", ["route"])
QUEUE = Gauge("atlas_jobs_active", "Queued and running jobs")
pool = None
jobs = {}


@asynccontextmanager
async def lifespan(app):
    global pool
    db.init(recover=True)
    operations.recover_jobs()
    collector = PipelineCollector()
    REGISTRY.register(collector)
    pool = ProcessPoolExecutor(max_workers=config.WORKERS)
    operations.worker_pool = pool
    yield
    REGISTRY.unregister(collector)
    operations.worker_pool = None
    pool.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title="ATLAS Traffic Intelligence", version="1.0.0", lifespan=lifespan)
app.include_router(operations_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ATLAS_CORS", "http://localhost:3000,http://127.0.0.1:3000").split(","),
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["*"],
)


@app.middleware("http")
async def instrument(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    route = request.scope.get("route")
    name = getattr(route, "path", "unmatched")
    REQUESTS.labels(request.method, name, response.status_code).inc()
    REQUEST_TIME.labels(name).observe(time.perf_counter() - start)
    return response


def require_video(video_id):
    value = db.video(video_id)
    if value is None:
        raise HTTPException(404, "Video not found")
    return value


def result(video_id):
    require_video(video_id)
    path = config.DATA / "results" / f"{video_id}.json"
    if not path.exists():
        raise HTTPException(409, "Results are not ready")
    return json.loads(path.read_text(encoding="utf-8"))


async def run_job(video_id):
    QUEUE.inc()
    try:
        await asyncio.get_running_loop().run_in_executor(pool, process_video, video_id)
    except Exception:
        log.exception("processing_job_failed", extra={"video_id": video_id})
        db.status(
            video_id,
            "failed",
            "failed",
            0,
            error="Processing worker failed. Inspect API logs, then reprocess.",
        )
    finally:
        QUEUE.dec()
        jobs.pop(video_id, None)


def enqueue(video_id):
    if video_id not in jobs:
        jobs[video_id] = asyncio.create_task(run_job(video_id))


def register_video(path, filename, intersection_id, video_id=None):
    if not db.rows("SELECT id FROM intersections WHERE id=?", (intersection_id,)):
        raise HTTPException(404, "Intersection not found")
    metadata = probe(path)
    video_id = video_id or db.uid()
    camera_id = db.uid()
    with db.connection() as conn:
        conn.execute("INSERT INTO cameras VALUES (?,?,?)", (camera_id, intersection_id, "{}"))
        conn.execute(
            "INSERT INTO videos (id,intersection_id,camera_id,filename,storage_path,status,progress,stage,error,metadata,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                video_id,
                intersection_id,
                camera_id,
                filename,
                str(path),
                "queued",
                0,
                "queued",
                None,
                json.dumps(metadata),
                db.now(),
            ),
        )
    return video_id


@app.get("/health")
def health():
    try:
        db.rows("SELECT 1")
    except Exception as exc:
        raise HTTPException(503, "Database unavailable") from exc
    return {
        "status": "ok",
        "database": "sqlite-wal",
        "device": config.DEVICE,
        "model": config.MODEL,
        "workers": config.WORKERS,
    }


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type="text/plain; version=0.0.4")


@app.get("/api/intersections")
def intersections():
    return db.rows(
        "SELECT i.*,count(v.id) AS video_count FROM intersections i LEFT JOIN videos v ON v.intersection_id=i.id GROUP BY i.id"
    )


@app.post("/api/intersections", status_code=201)
def create_intersection(body: IntersectionIn):
    value = {"id": db.uid(), **body.model_dump(), "created_at": db.now()}
    with db.connection() as conn:
        conn.execute("INSERT INTO intersections VALUES (?,?,?,?)", tuple(value.values()))
    return value


@app.get("/api/videos")
def videos(intersection_id: str | None = None):
    values = db.rows(
        "SELECT id FROM videos WHERE (? IS NULL OR intersection_id=?) ORDER BY created_at DESC LIMIT 100",
        (intersection_id, intersection_id),
    )
    return [db.video(v["id"]) for v in values]


@app.post("/api/videos", status_code=202)
async def upload(intersection_id: str = "demo", file: UploadFile = File(...)):
    if len(jobs) >= 8:
        raise HTTPException(429, "Processing queue is full; retry after current jobs finish")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".mp4", ".webm", ".avi", ".mov", ".mkv"}:
        raise HTTPException(415, "Upload MP4, WebM, AVI, MOV or MKV video")
    video_id = db.uid()
    path = config.DATA / "uploads" / f"{video_id}{suffix}"
    total = 0
    try:
        with path.open("wb") as target:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > config.MAX_UPLOAD:
                    raise HTTPException(413, "Video exceeds upload size limit")
                target.write(chunk)
        safe_name = Path((file.filename or "video").replace("\\", "/")).name[:180]
        await asyncio.to_thread(register_video, path, safe_name, intersection_id, video_id)
    except ValueError as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(422, str(exc)) from exc
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    enqueue(video_id)
    return db.video(video_id)


@app.post("/api/demo", status_code=202)
async def demo():
    previous = db.rows(
        "SELECT id FROM videos WHERE filename='demo.mp4' ORDER BY created_at DESC LIMIT 1"
    )
    if previous and db.video(previous[0]["id"])["status"] in {"complete", "processing", "queued"}:
        return db.video(previous[0]["id"])
    path = config.DATA / "demo.mp4"
    if not path.exists():
        raise HTTPException(
            409,
            "Run 'atlas demo --download-only' to download the attributed sample, or upload your own footage",
        )
    video_id = register_video(path, "demo.mp4", "demo")
    camera_settings = CameraConfig.model_validate_json(
        (config.ROOT / "docs" / "demo-camera.json").read_text()
    )
    with db.connection() as conn:
        conn.execute(
            "UPDATE cameras SET config=? WHERE id=(SELECT camera_id FROM videos WHERE id=?)",
            (camera_settings.model_dump_json(), video_id),
        )
    enqueue(video_id)
    return db.video(video_id)


@app.get("/api/videos/{video_id}")
def video_status(video_id: str):
    return require_video(video_id)


@app.get("/api/videos/{video_id}/events-stream")
async def events_stream(video_id: str, request: Request):
    require_video(video_id)

    async def stream():
        last = None
        while not await request.is_disconnected():
            value = db.video(video_id)
            encoded = json.dumps(value)
            if encoded != last:
                yield f"data: {encoded}\n\n"
                last = encoded
            else:
                yield ": heartbeat\n\n"
            if value["status"] in {"complete", "failed"}:
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/videos/{video_id}/source")
def video_source(video_id: str):
    require_video(video_id)
    path = db.rows("SELECT storage_path FROM videos WHERE id=?", (video_id,))[0]["storage_path"]
    return FileResponse(path)


@app.get("/api/videos/{video_id}/result")
def video_result(video_id: str):
    require_video(video_id)
    path = config.DATA / "results" / f"{video_id}.json"
    if not path.exists():
        raise HTTPException(409, "Results are not ready")
    return FileResponse(path, media_type="application/json")


@app.get("/api/videos/{video_id}/tracks")
def tracks(video_id: str):
    require_video(video_id)
    return [
        json.loads(r["summary"])
        for r in db.rows(
            "SELECT summary FROM tracks WHERE video_id=? ORDER BY track_id", (video_id,)
        )
    ]


@app.get("/api/videos/{video_id}/metrics")
def video_metrics(video_id: str):
    require_video(video_id)
    return [
        json.loads(r["payload"])
        for r in db.rows(
            "SELECT payload FROM traffic_metrics WHERE video_id=? ORDER BY timestamp", (video_id,)
        )
    ]


@app.get("/api/videos/{video_id}/safety")
def safety(video_id: str):
    require_video(video_id)
    return [
        json.loads(r["payload"])
        for r in db.rows(
            "SELECT payload FROM safety_events WHERE video_id=? ORDER BY timestamp", (video_id,)
        )
    ]


@app.get("/api/videos/{video_id}/forecast")
def forecast(video_id: str):
    return result(video_id)["forecast"]


@app.get("/api/videos/{video_id}/camera")
def camera(video_id: str):
    require_video(video_id)
    return json.loads(
        db.rows(
            "SELECT c.config FROM cameras c JOIN videos v ON v.camera_id=c.id WHERE v.id=?",
            (video_id,),
        )[0]["config"]
    )


@app.put("/api/videos/{video_id}/camera")
def update_camera(video_id: str, body: CameraConfig):
    value = require_video(video_id)
    if value["status"] in {"processing", "queued"}:
        raise HTTPException(409, "Wait for processing to finish before editing calibration")
    try:
        Projection(body.calibration)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    with db.connection() as conn:
        conn.execute(
            "UPDATE cameras SET config=? WHERE id=?", (body.model_dump_json(), value["camera_id"])
        )
    return {"saved": True, "reprocess_required": True}


@app.post("/api/videos/{video_id}/reprocess", status_code=202)
async def reprocess(video_id: str):
    value = require_video(video_id)
    if value["status"] in {"queued", "processing"}:
        return value
    if len(jobs) >= 8:
        raise HTTPException(429, "Processing queue is full")
    db.status(video_id, "queued", "queued", 0)
    enqueue(video_id)
    return db.video(video_id)


@app.post("/api/simulations")
async def simulations(body: SimulationConfig):
    if body.video_id:
        observations = result(body.video_id)
        duration = observations["metadata"]["duration"]
        if duration < 30:
            raise HTTPException(422, "At least 30 seconds of footage required to estimate demand")
        counts = [0, 0, 0, 0]
        for track in observations["tracks"]:
            if track["class"] in {"car", "truck", "bus", "motorcycle"}:
                direction = track["points"][-1]["direction"]
                counts[["N", "E", "S", "W"].index(direction)] += 1
        body = body.model_copy(update={"demand": [min(1.5, c / duration) for c in counts]})
    payload = await asyncio.to_thread(optimize, body)
    payload["id"] = db.save_run("optimization", payload)
    return payload


@app.get("/api/simulations/{run_id}")
def simulation_run(run_id: str):
    values = db.rows("SELECT payload FROM runs WHERE id=? AND kind='optimization'", (run_id,))
    if not values:
        raise HTTPException(404, "Simulation not found")
    return json.loads(values[0]["payload"])


@app.get("/api/benchmarks")
def benchmarks():
    files = sorted(config.ARTIFACTS.glob("*.json"))
    payload = {f.stem: json.loads(f.read_text(encoding="utf-8-sig")) for f in files}
    directory = config.ARTIFACTS / "benchmarks"
    payload["real_world"] = {
        f.stem: json.loads(f.read_text(encoding="utf-8")) for f in sorted(directory.glob("*.json"))
    }
    return payload


@app.get("/api/benchmarks/{name}")
def benchmark_artifact(name: str):
    if not name.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(422, "Invalid benchmark artifact name")
    path = config.ARTIFACTS / "benchmarks" / f"{name}.json"
    if not path.is_file():
        raise HTTPException(404, "Benchmark artifact not found")
    return FileResponse(path, media_type="application/json")


def capture_stream(url, duration, target):
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    writer = None
    start = time.monotonic()
    try:
        if not cap.isOpened():
            raise ValueError("Could not open the stream")
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)
        fps = cap.get(cv2.CAP_PROP_FPS)
        fps = fps if 1 <= fps <= 60 else 25
        while time.monotonic() - start < duration:
            ok, frame = cap.read()
            if not ok:
                break
            if writer is None:
                writer = cv2.VideoWriter(
                    str(target),
                    cv2.VideoWriter_fourcc(*"VP80"),
                    fps,
                    (frame.shape[1], frame.shape[0]),
                )
            writer.write(frame)
        if writer is None:
            raise ValueError("Stream delivered no frames")
    finally:
        cap.release()
        if writer:
            writer.release()


@app.post("/api/streams", status_code=202)
async def import_stream(body: StreamIn):
    if os.getenv("ATLAS_ALLOW_STREAMS", "false").lower() != "true":
        raise HTTPException(
            403, "Stream capture disabled. Enable explicitly for a trusted local deployment."
        )
    parsed = urlparse(body.url)
    hosts = os.getenv("ATLAS_STREAM_HOSTS", "").split(",")
    if (
        parsed.scheme not in {"rtsp", "http", "https"}
        or parsed.hostname not in hosts
        or parsed.username
    ):
        raise HTTPException(422, "Use a credential-free stream on an explicitly allowed host")
    video_id = db.uid()
    path = config.DATA / "uploads" / f"{video_id}.webm"
    try:
        await asyncio.to_thread(capture_stream, body.url, body.duration_seconds, path)
        register_video(path, "stream-capture.webm", body.intersection_id, video_id)
    except ValueError as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(422, str(exc)) from exc
    enqueue(video_id)
    return db.video(video_id)
