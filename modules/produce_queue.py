"""Hàng đợi xử lý ảnh — Patch / DXF / Spot W1."""

from __future__ import annotations

import os
import queue
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class QueueJob:
    tool: str
    path: str
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


@dataclass
class JobRecord:
    job_id: str
    tool: str
    path: str
    state: str = "pending"
    detail: str = ""
    match_pct: float | None = None


class ProduceQueue:
    TOOL_LABELS = {"patch": "Patch", "dxf": "DXF", "spot": "Spot"}

    def __init__(self, app) -> None:
        self.app = app
        self._q: queue.Queue[QueueJob | None] = queue.Queue()
        self._pending = 0
        self._worker: threading.Thread | None = None
        self._records: list[JobRecord] = []
        self._lock = threading.Lock()
        self._batch_active = False
        self._handlers = {
            "patch": lambda p: app.process_patch_crop(p, silent=True),
            "dxf": lambda p: app.process_image_to_dxf(p, silent=True),
            "spot": lambda p: app.process_spot_color_tif(p, silent=True),
        }

    @property
    def pending(self) -> int:
        return self._pending

    def get_records(self) -> list[JobRecord]:
        with self._lock:
            return list(self._records)

    def clear_finished(self) -> int:
        with self._lock:
            before = len(self._records)
            self._records = [r for r in self._records if r.state in ("pending", "running")]
            return before - len(self._records)

    def enqueue_many(self, tool: str, paths: list[str]) -> int:
        added = 0
        for path in paths:
            if not path:
                continue
            job = QueueJob(tool, path)
            with self._lock:
                self._records.append(JobRecord(job.job_id, tool, path))
            self._q.put(job)
            self._pending += 1
            added += 1
        if added:
            self._batch_active = True
            self._ensure_worker()
            self._update_status()
            self.app.log(f"Hàng đợi +{added} · {self.TOOL_LABELS.get(tool, tool)}", "accent")
        return added

    def _find_record(self, job_id: str) -> JobRecord | None:
        with self._lock:
            for rec in self._records:
                if rec.job_id == job_id:
                    return rec
        return None

    def _set_record(
        self,
        job_id: str,
        state: str,
        detail: str = "",
        match_pct: float | None = None,
    ) -> None:
        with self._lock:
            for rec in self._records:
                if rec.job_id == job_id:
                    rec.state = state
                    if detail:
                        rec.detail = detail
                    if match_pct is not None:
                        rec.match_pct = match_pct
                    break
        self._update_status()

    def _ensure_worker(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def _apply_result(self, job: QueueJob, result: Any) -> None:
        if not isinstance(result, dict):
            self._set_record(job.job_id, "done")
            return

        match_pct = result.get("match_pct")
        if job.tool == "patch":
            dxf = result.get("dxf")
            if isinstance(dxf, dict) and dxf.get("match_pct") is not None:
                match_pct = dxf["match_pct"]

        if result.get("skipped"):
            self._set_record(
                job.job_id, "skipped",
                result.get("message", "Bỏ qua"),
                match_pct,
            )
        elif result.get("cancelled"):
            self._set_record(job.job_id, "skipped", "Đã hủy preview", match_pct)
        elif result.get("ok"):
            self._set_record(
                job.job_id, "done",
                result.get("message", "OK"),
                match_pct,
            )
        else:
            self._set_record(
                job.job_id, "error",
                result.get("error", result.get("message", "Lỗi")),
                match_pct,
            )

    def _run(self) -> None:
        while True:
            job = self._q.get()
            if job is None:
                self._q.task_done()
                break

            label = self.TOOL_LABELS.get(job.tool, job.tool)
            name = os.path.basename(job.path)
            self._set_record(job.job_id, "running", "Đang xử lý…")
            self.app.root.after(
                0, lambda lb=label, n=name: self.app.log(f"[Hàng đợi] {lb}: {n}…"),
            )
            try:
                handler = self._handlers.get(job.tool)
                result = handler(job.path) if handler else None
                self._apply_result(job, result)
            except Exception as exc:
                self._set_record(job.job_id, "error", str(exc))
                self.app.root.after(0, lambda e=exc: self.app.log(f"Hàng đợi lỗi: {e}", "danger"))
            finally:
                self._pending = max(0, self._pending - 1)
                self._update_status()
                if self._pending == 0 and self._batch_active:
                    self._batch_active = False
                    self.app.root.after(0, self._emit_batch_summary)
                self._q.task_done()

    def _emit_batch_summary(self) -> None:
        records = self.get_records()
        done = [r for r in records if r.state == "done"]
        skipped = [r for r in records if r.state == "skipped"]
        errors = [r for r in records if r.state == "error"]
        low_match = [
            r for r in records
            if r.match_pct is not None and r.match_pct < 95.0
            and r.state in ("done", "skipped")
        ]

        parts = [f"Xong: {len(done)} OK"]
        if skipped:
            parts.append(f"{len(skipped)} bỏ qua")
        if errors:
            parts.append(f"{len(errors)} lỗi")
        summary = " · ".join(parts)
        self.app.log(f"Hàng đợi — {summary}", "success" if not errors else "danger")

        if low_match:
            lines = [f"  · {os.path.basename(r.path)}: {r.match_pct:.1f}% ({r.state})" for r in low_match[:12]]
            self.app.log("DXF khớp thấp (<95%):\n" + "\n".join(lines), "danger")

        if hasattr(self.app, "show_queue_summary"):
            self.app.show_queue_summary(done, skipped, errors, low_match)

    def _update_status(self) -> None:
        if hasattr(self.app, "update_queue_status"):
            self.app.root.after(0, self.app.update_queue_status)
        if hasattr(self.app, "refresh_queue_panel"):
            self.app.root.after(0, self.app.refresh_queue_panel)