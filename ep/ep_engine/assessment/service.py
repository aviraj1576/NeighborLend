import hashlib
import json

from ep_engine.assessment.contracts import digest_package
from ep_engine.assessment.providers import ProviderError, configured_provider
from ep_engine.assessment.store import AssessmentStore
from ep_engine.core.exceptions import EPError
from ep_engine.cv.concurrency import worker_guard


def provider_key(provider):
    metadata = {"provider": provider.kind, "model": provider.model}
    if hasattr(provider, "settings"):
        metadata["settings"] = provider.settings.model_dump(mode="json", exclude={"api_key"})
    return hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()


class AssessmentService:
    def __init__(self, directory, cv_service, provider=None):
        self.cv = cv_service
        self.provider = provider
        self.store = AssessmentStore(directory / "assessments")
        self.store.initialize()

    def _provider(self):
        try:
            return self.provider if self.provider is not None else configured_provider()
        except (ProviderError, ValueError) as exc:
            raise EPError(
                503, "provider_configuration", "Invalid assessment provider configuration"
            ) from exc

    def _source(self, cv_run_id, grant):
        package = self.cv.result(cv_run_id, grant)
        run = self.cv.get(cv_run_id, grant)[0]
        inspection = self.cv.repository.get_inspection(str(run.inspection_id))
        self.cv._evidence(inspection, grant)
        if inspection.status != "created":
            raise EPError(409, "invalid_transition", "Parent inspection is not eligible")
        return run, package

    def create(self, cv_run_id, options, grant):
        run, package = self._source(cv_run_id, grant)
        return self.store.create(
            run, digest_package(package), grant.subject, options, provider_key(self._provider())
        )

    def get(self, key, grant):
        job, owner, report = self.store.get(key)
        grant.authorize(job.rental_id)
        return job, owner, report

    def cancel(self, key, grant):
        _, owner, _ = self.get(key, grant)
        if owner != grant.subject:
            raise EPError(403, "forbidden", "Only the requester can cancel")
        return self.store.terminate(key, "cancelled")

    def result(self, key, grant):
        job, _, report = self.get(key, grant)
        if job.status != "completed" or report is None:
            raise EPError(409, "result_unavailable", "Assessment result is not available")
        _, package = self._source(job.cv_run_id, grant)
        if (
            digest_package(package) != job.cv_digest
            or report.cv_digest != job.cv_digest
            or report.source_hashes != package.source_hashes
            or report.cv_run_id != job.cv_run_id
            or report.inspection_id != job.inspection_id
        ):
            raise EPError(409, "integrity_failure", "Assessment source changed")
        candidates = {row.id: row for row in package.candidates}
        known_artifacts = {row.id: set(row.source_ids) for row in package.artifacts}
        if (
            set(report.selected_candidates) | set(report.unassessed_candidates) != set(candidates)
            or report.status == "no_visible_change"
            and candidates
        ):
            raise EPError(409, "integrity_failure", "Assessment candidate coverage changed")
        for finding in report.findings:
            candidate = candidates.get(finding.candidate_id)
            if candidate is None:
                raise EPError(409, "integrity_failure", "Assessment cites unknown candidate")
            sources = {candidate.before_id, candidate.after_id}
            if (
                set(finding.evidence_ids) != sources
                or not set(candidate.artifact_ids).issubset(finding.artifact_ids)
                or any(
                    key not in known_artifacts or not known_artifacts[key].issubset(sources)
                    for key in finding.artifact_ids
                )
            ):
                raise EPError(409, "integrity_failure", "Assessment citations changed")
        return report

    def execute(self, key, grant):
        from ep_engine.assessment.engine import assess

        with worker_guard():
            job, owner, _ = self.get(key, grant)
            if owner != grant.subject:
                raise EPError(403, "forbidden", "Only the requester can execute")
            _, package = self._source(job.cv_run_id, grant)
            if digest_package(package) != job.cv_digest:
                raise EPError(409, "integrity_failure", "CV source changed")
            self.store.claim(key)
            try:
                provider = self._provider()
                if provider_key(provider) != job.provider_key:
                    raise EPError(
                        409, "provider_configuration_changed", "Provider configuration changed"
                    )
                report = assess(
                    job.cv_run_id,
                    package,
                    lambda artifact: self.cv.artifact(job.cv_run_id, artifact, grant),
                    job.options,
                    provider,
                )
                # Authorization, originals, derivatives and artifacts must remain valid at commit.
                _, current = self._source(job.cv_run_id, grant)
                if digest_package(current) != job.cv_digest:
                    raise EPError(409, "integrity_failure", "CV source changed during assessment")
                self.store.finish(key, report)
                return report
            except BaseException as exc:
                if self.store.get(key)[0].status == "processing":
                    self.store.terminate(
                        key,
                        "failed",
                        exc.code if isinstance(exc, EPError) else "assessment_failure",
                    )
                raise
