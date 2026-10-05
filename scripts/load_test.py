"""Measure progressive API clients, database queries, and SSE delivery without fake latency."""

import argparse
import asyncio
import time
from datetime import UTC, datetime

import httpx
import numpy as np
from atlas import db
from atlas.experiments import save


async def scenario(base, clients, requests_per_client, video_id):
    latencies = []
    errors = 0
    endpoints = ["/health", "/api/intersections", "/api/videos"]
    if video_id:
        endpoints += [f"/api/videos/{video_id}/tracks", f"/api/videos/{video_id}/metrics"]
    start = time.perf_counter()
    async with httpx.AsyncClient(base_url=base, timeout=20) as client:

        async def worker(index):
            nonlocal errors
            for i in range(requests_per_client):
                before = time.perf_counter()
                try:
                    response = await client.get(endpoints[(index + i) % len(endpoints)])
                    response.raise_for_status()
                except httpx.HTTPError:
                    errors += 1
                latencies.append((time.perf_counter() - before) * 1000)

        await asyncio.gather(*(worker(i) for i in range(clients)))
    elapsed = time.perf_counter() - start
    return {
        "clients": clients,
        "requests": len(latencies),
        "errors": errors,
        "wall_seconds": elapsed,
        "rps": len(latencies) / elapsed,
        "latency_ms": {f"p{q}": float(np.percentile(latencies, q)) for q in [50, 95, 99]},
    }


async def delivery(base):
    async with httpx.AsyncClient(base_url=base, timeout=10) as client:
        response = await client.get("/api/videos")
        videos = response.json()
        if not videos:
            return None
        video_id = videos[0]["id"]
        # Live SSE observations require a currently processing video.
        samples = []
        if videos[0]["status"] in {"queued", "processing"}:
            import json

            async with client.stream("GET", f"/api/videos/{video_id}/events-stream") as stream:
                async for line in stream.aiter_lines():
                    if line.startswith("data: "):
                        item = json.loads(line[6:])
                        if item.get("updated_at"):
                            age = (
                                datetime.now(UTC) - datetime.fromisoformat(item["updated_at"])
                            ).total_seconds() * 1000
                            if age >= 0:
                                samples.append(age)
                        if len(samples) >= 10 or item["status"] in {"complete", "failed"}:
                            break
        before = time.perf_counter()
        async with client.stream("GET", f"/api/videos/{video_id}/events-stream") as stream:
            async for line in stream.aiter_lines():
                if line.startswith("data: "):
                    snapshot_ms = (time.perf_counter() - before) * 1000
                    break
        return {
            "initial_snapshot_ms": snapshot_ms,
            "status_delivery_ms": {f"p{q}": float(np.percentile(samples, q)) for q in [50, 95, 99]}
            if samples
            else None,
            "note": "Stage-status delivery from persisted timestamp; initial snapshot is not live frame latency",
        }


async def main(args):
    async with httpx.AsyncClient(base_url=args.url) as client:
        response = await client.get("/api/videos")
        values = response.json()
    video_id = next((v["id"] for v in values if v["status"] == "complete"), None)
    scenarios = [await scenario(args.url, n, args.requests, video_id) for n in [1, 4, 16, 32]]
    queries = []
    for _ in range(100):
        before = time.perf_counter()
        db.rows("SELECT id,timestamp FROM safety_events ORDER BY timestamp DESC LIMIT 50")
        queries.append((time.perf_counter() - before) * 1000)
    result = save(
        "load",
        {
            "scope": "Loopback API + SQLite result queries, sequential requests per client; does not measure concurrent inference or GPU",
            "url": args.url,
            "scenarios": scenarios,
            "database_query_ms": {f"p{q}": float(np.percentile(queries, q)) for q in [50, 95, 99]},
            "sse": await delivery(args.url),
        },
    )
    for s in result["scenarios"]:
        print(
            f"{s['clients']:2} clients: {s['rps']:.1f} req/s, p95 {s['latency_ms']['p95']:.1f} ms, {s['errors']} errors"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=50)
    asyncio.run(main(parser.parse_args()))
