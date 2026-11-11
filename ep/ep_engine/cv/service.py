from uuid import UUID

from ep_engine.core.exceptions import EPError
from ep_engine.cv.concurrency import worker_guard
from ep_engine.cv.contracts import CVPackage
from ep_engine.cv.store import CVStore, cleanup


class CVService:
    def __init__(self, data_dir, repository, storage):
        self.repository, self.storage = repository, storage
        self.store = CVStore(data_dir / "cv")
        self.store.initialize()

    def _evidence(self, inspection, grant):
        grant.authorize(inspection.rental_id)
        rows = []
        for stage, keys in (("before", inspection.reference_ids), ("after", inspection.return_ids)):
            for key in keys:
                record = self.repository.get_evidence(str(key))
                if (
                    record.rental_id != inspection.rental_id
                    or record.stage != stage
                    or record.validation_status != "validated"
                ):
                    raise EPError(409, "invalid_evidence", "Invalid inspection evidence")
                self.storage.verified_read(str(key), "original", record.sha256)
                self.storage.verified_read(str(key), "png", record.normalized_sha256)
                rows.append(record)
        return rows

    def create(self, inspection_id, request, grant):
        inspection = self.repository.get_inspection(str(inspection_id))
        rows = self._evidence(inspection, grant)
        if inspection.status != "created":
            raise EPError(
                409, "invalid_transition", "CV may only start from an unprocessed inspection"
            )
        if len(rows) > request.config.max_images:
            raise EPError(413, "processing_limit", "Too many images for the configured CV budget")
        if not set(request.targets).issubset({row.id for row in rows}):
            raise EPError(422, "invalid_target", "Target selection cites unknown evidence")
        return self.store.create(inspection, request, grant.subject)

    def get(self, run_id, grant):
        run, subject, result = self.store.get(str(run_id))
        grant.authorize(run.rental_id)
        return run, subject, result

    def cancel(self, run_id, grant):
        _, subject, _ = self.get(run_id, grant)
        if subject != grant.subject:
            raise EPError(403, "forbidden", "Only the requesting participant can cancel this run")
        return self.store.terminate(str(run_id), "cancelled")

    def result(self, run_id, grant):
        run, _, package = self.get(run_id, grant)
        if run.status != "completed" or package is None:
            raise EPError(409, "result_unavailable", "CV result is not available")
        inspection = self.repository.get_inspection(str(run.inspection_id))
        self._validate_manifest(run, inspection, self._evidence(inspection, grant), package)
        self.store.verify_package_files(str(run_id), package)
        return package

    def _validate_manifest(self, run, inspection, rows, package):
        if (
            package.inspection_id != inspection.id
            or set(package.source_ids) != {row.id for row in rows}
            or package.source_hashes != {row.id: row.sha256 for row in rows}
            or package.source_dimensions != {row.id: (row.width, row.height) for row in rows}
            or package.thresholds != run.request.config
        ):
            raise EPError(
                409, "stage_contract", "Worker changed the approved source/config manifest"
            )
        for pair in package.pairs + package.candidates + package.boundary_changes:
            if (
                pair.before_id not in inspection.reference_ids
                or pair.after_id not in inspection.return_ids
            ):
                raise EPError(409, "stage_contract", "Worker reversed evidence stages")

    def artifact(self, run_id, artifact_id, grant):
        package = self.result(run_id, grant)
        artifact_id = UUID(str(artifact_id))
        if artifact_id not in {row.id for row in package.artifacts}:
            raise EPError(404, "not_found", "Artifact not found")
        path = self.store.artifacts / str(UUID(str(run_id))) / f"{artifact_id}.png"
        return path.read_bytes()

    def execute(self, run_id, grant, executor=None):
        with worker_guard():
            return self._execute(run_id, grant, executor)

    def _execute(self, run_id, grant, executor=None):
        run, subject, _ = self.get(run_id, grant)
        if subject != grant.subject:
            raise EPError(403, "forbidden", "Worker identity must match the requesting participant")
        inspection = self.repository.get_inspection(str(run.inspection_id))
        rows = self._evidence(inspection, grant)
        if inspection.status != "created":
            raise EPError(409, "invalid_transition", "Inspection state changed before CV execution")
        self.store.claim(str(run.id))
        directory = self.store.work / str(run.id)
        output = directory / "output"
        payload = {
            "inspection_id": str(inspection.id),
            "config": run.request.config.model_dump(),
            "evidence": [
                {
                    "id": str(row.id),
                    "stage": row.stage,
                    "path": str(self.storage.path(str(row.id), "png")),
                    "sha256": row.sha256,
                    "normalized_sha256": row.normalized_sha256,
                    "target": run.request.targets[row.id].model_dump()
                    if row.id in run.request.targets
                    else None,
                    "view": row.viewpoint,
                }
                for row in rows
            ],
        }
        try:
            directory.mkdir(exist_ok=False)
            if executor is None:
                from ep_engine.cv.worker import ProcessRunner

                executor = ProcessRunner()
            package = executor(
                payload, output, lambda: self.store.get(str(run.id))[0].status == "cancelled"
            )
            package = CVPackage.model_validate(package.model_dump())
            # Revalidate current evidence and identity after the external worker completes.
            self._evidence(inspection, grant)
            self._validate_manifest(run, inspection, rows, package)
            self.store.finish(str(run.id), package, output)
            return package
        except BaseException as exc:
            diagnostic = directory / "diagnostics.json"
            if diagnostic.is_file():
                failures = self.store.root / "failures"
                failures.mkdir(exist_ok=True)
                (failures / f"{run.id}.json").write_text(
                    diagnostic.read_text("utf-8"), encoding="utf-8"
                )
            if self.store.get(str(run.id))[0].status == "processing":
                self.store.terminate(
                    str(run.id),
                    "failed",
                    exc.code if isinstance(exc, EPError) else "worker_failure",
                )
            raise
        finally:
            cleanup(self.store.work, directory)
