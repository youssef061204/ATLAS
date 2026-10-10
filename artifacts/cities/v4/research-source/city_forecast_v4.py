"""Causal forecasts of official historical city counts; no current-camera fusion."""

from collections import defaultdict
from datetime import datetime, timedelta

import numpy as np
import torch
from torch import nn


def samples(document, radius_m=1500):
    """Keep native cadence, whole-date splits, and observed geographic neighbors only."""
    groups = defaultdict(dict)
    for record in document["records"]:
        key = (record["site_id"], record.get("direction", "all"), record["interval_seconds"])
        stamp = datetime.fromisoformat(record["observed_at"].replace("Z", "+00:00"))
        if stamp in groups[key]:
            raise ValueError(
                "Duplicate source interval; aggregate components explicitly before forecasting"
            )
        if record["count"] < 0 or not np.isfinite(record["count"]) or key[2] <= 0:
            raise ValueError("Invalid count or native interval")
        groups[key][stamp] = record
    dates = sorted({t.date().isoformat() for rows in groups.values() for t in rows})
    if len(dates) < 3:
        return [], {
            "reason": "Fewer than three independently ordered observation dates",
            "dates": dates,
        }
    train_end = min(len(dates) - 2, max(1, int(len(dates) * 0.7)))
    val_end = min(len(dates) - 1, max(train_end + 1, int(len(dates) * 0.85)))
    split = {
        d: "train" if i < train_end else "validation" if i < val_end else "test"
        for i, d in enumerate(dates)
    }
    sites = document["sites"]

    def distance(a, b):
        if any(a.get(k) is None or b.get(k) is None for k in ("lat", "lon")):
            return float("inf")
        lat = np.radians((a["lat"] + b["lat"]) / 2)
        return float(
            np.hypot((a["lat"] - b["lat"]) * 111_195, (a["lon"] - b["lon"]) * 111_195 * np.cos(lat))
        )

    rows = []
    for (site, direction, interval), records in sorted(groups.items()):
        for target_time, target in sorted(records.items()):
            history_times = [target_time - timedelta(seconds=interval * i) for i in (3, 2, 1)]
            partition = split[target_time.date().isoformat()]
            if any(
                t not in records or split[t.date().isoformat()] != partition for t in history_times
            ):
                continue
            history = [records[t]["count"] * 3600 / interval for t in history_times]
            neighbors = []
            for (other, other_direction, other_interval), other_records in groups.items():
                if other == site or other_direction != direction or other_interval != interval:
                    continue
                if distance(sites[site], sites[other]) > radius_m:
                    continue
                if all(t in other_records for t in history_times):
                    neighbors.append(
                        [other_records[t]["count"] * 3600 / interval for t in history_times]
                    )
            neighborhood = np.mean(neighbors, axis=0).tolist() if neighbors else [0.0] * 3
            hour = target_time.hour + target_time.minute / 60
            rows.append(
                {
                    "city": document["city"],
                    "site_id": site,
                    "direction": direction,
                    "time": target_time.isoformat(),
                    "date": target_time.date().isoformat(),
                    "split": partition,
                    "interval_seconds": interval,
                    "actual": float(target["count"]),
                    "history_flow_vph": history,
                    "neighbor_flow_vph": neighborhood,
                    "neighbor_sites": len(neighbors),
                    "calendar": [
                        float(np.sin(2 * np.pi * hour / 24)),
                        float(np.cos(2 * np.pi * hour / 24)),
                        float(np.sin(2 * np.pi * target_time.weekday() / 7)),
                        float(np.cos(2 * np.pi * target_time.weekday() / 7)),
                        float(np.log1p(interval) / 10),
                    ],
                }
            )
    return rows, {
        "dates": dates,
        "split_dates": {
            name: [d for d in dates if split[d] == name] for name in ("train", "validation", "test")
        },
        "graph": "Undirected 1500m geographic proximity; only identical actual causal bins, not a surveyed directed flow graph",
        "neighbor_coverage_fraction": sum(r["neighbor_sites"] > 0 for r in rows)
        / max(1, len(rows)),
    }


class TrainingScale:
    def __init__(self, train):
        values = np.log1p(np.asarray([r["history_flow_vph"] for r in train]))
        self.mean = float(values.mean())
        self.std = max(0.1, float(values.std()))

    def features(self, rows):
        local = (np.log1p(np.asarray([r["history_flow_vph"] for r in rows])) - self.mean) / self.std
        neighbor = (
            np.log1p(np.asarray([r["neighbor_flow_vph"] for r in rows])) - self.mean
        ) / self.std
        mask = np.asarray([r["neighbor_sites"] > 0 for r in rows], dtype=float)[:, None]
        return np.c_[local, [r["calendar"] for r in rows], neighbor * mask, mask].astype(np.float32)

    def targets(self, rows):
        return (
            (np.log1p([r["actual"] * 3600 / r["interval_seconds"] for r in rows]) - self.mean)
            / self.std
        ).astype(np.float32)

    def counts(self, predictions, rows):
        flow = np.expm1(np.clip(np.asarray(predictions) * self.std + self.mean, 0, 15))
        return flow * np.asarray([r["interval_seconds"] for r in rows]) / 3600


class CityMessageNetwork(nn.Module):
    """Shared one-hop learned messages from genuinely concurrent neighboring series."""

    def __init__(self, graph=True, hidden=24):
        super().__init__()
        self.graph = graph
        self.encoder = nn.Linear(8, hidden)
        self.message = nn.Linear(3, hidden, bias=False) if graph else None
        self.local = nn.Linear(hidden, hidden)
        self.output = nn.Linear(hidden, 1)

    def forward(self, x):
        hidden = self.encoder(x[:, :8])
        if self.graph:
            hidden = hidden + self.message(x[:, 8:11]) * x[:, 11:12]
        # Predict a learned correction to the last actually observed flow.
        return x[:, 2] + self.output(torch.relu(self.local(torch.relu(hidden)))).squeeze(-1)


def fit_neural(train, validation, graph, settings):
    torch.manual_seed(settings["seed"])
    torch.set_num_threads(settings["threads"])
    scale = TrainingScale(train)
    model = CityMessageNetwork(graph, settings["hidden"])
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=settings["learning_rate"], weight_decay=0.001
    )
    x = torch.tensor(scale.features(train))
    y = torch.tensor(scale.targets(train))
    vx = torch.tensor(scale.features(validation))
    actual = np.asarray([r["actual"] for r in validation])
    best, best_state, best_epoch, curve = float("inf"), None, 0, []
    generator = torch.Generator().manual_seed(settings["seed"])
    for epoch in range(settings["maximum_epochs"]):
        model.train()
        order = torch.randperm(len(x), generator=generator)
        for batch in order.split(settings["batch_size"]):
            optimizer.zero_grad()
            loss = torch.nn.functional.smooth_l1_loss(model(x[batch]), y[batch])
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5)
            optimizer.step()
        model.eval()
        with torch.inference_mode():
            predictions = scale.counts(model(vx).numpy(), validation)
        error = float(np.abs(actual - predictions).mean())
        curve.append(error)
        if error < best:
            best, best_epoch = error, epoch + 1
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state)
    model.eval()
    return (
        model,
        scale,
        {
            "selected_epoch": best_epoch,
            "validation_mae": best,
            "validation_curve": curve,
            "parameters": sum(p.numel() for p in model.parameters()),
        },
    )


def neural_predictions(model, scale, rows):
    with torch.inference_mode():
        return scale.counts(model(torch.tensor(scale.features(rows))).numpy(), rows)


def conformal_radius(actual, predictions, coverage=0.9):
    residual = np.abs(np.asarray(actual) - predictions)
    if len(residual) == 0:
        raise ValueError("Independent validation residuals required")
    rank = int(np.ceil((len(residual) + 1) * coverage))
    if rank > len(residual):
        return None  # finite data cannot support this finite-sample coverage level
    return float(np.sort(residual)[rank - 1])


def paired_date_interval(rows, baseline, candidate, draws=2000):
    groups = defaultdict(list)
    for i, r in enumerate(rows):
        groups[r["date"]].append(i)
    true = np.asarray([r["actual"] for r in rows])
    rng = np.random.default_rng(44)
    dates = list(groups)
    differences = []
    for _ in range(draws):
        indices = [i for d in rng.choice(dates, len(dates), replace=True) for i in groups[d]]
        b = np.abs(true[indices] - baseline[indices]).mean()
        c = np.abs(true[indices] - candidate[indices]).mean()
        differences.append(float(b - c))
    return {
        "test_dates": len(dates),
        "draws": draws,
        "mae_difference_count_95ci": np.percentile(differences, [2.5, 97.5]).tolist(),
        "limitation": "One test date yields a degenerate interval and cannot establish across-day significance"
        if len(dates) == 1
        else "Chronological observational study, single training seed; dependence can remain across dates",
    }
