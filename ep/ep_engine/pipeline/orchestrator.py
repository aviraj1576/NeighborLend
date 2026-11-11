from ep_engine.core.exceptions import EPError
from ep_engine.pipeline.interfaces import (
    STAGE_ORDER,
    PipelineContext,
    StageImplementation,
    StageResult,
)


class Orchestrator:
    def __init__(self, stages: dict[str, StageImplementation] | None = None):
        self.stages = dict(stages or {})

    def run(self, context: PipelineContext) -> PipelineContext:
        return self._execute(context, STAGE_ORDER)

    def run_cv(self, context: PipelineContext) -> PipelineContext:
        """Explicit CV-only execution; never supplies fake verification/report stages."""
        return self._execute(context, STAGE_ORDER[:6])

    def run_assessment(self, context: PipelineContext) -> PipelineContext:
        """Execute the remaining stages over an already validated CV sub-result."""
        return self._execute(context, STAGE_ORDER[6:])

    def _execute(self, context, order):
        if set(self.stages) != set(order):
            raise EPError(503, "pipeline_unavailable", "All analysis stages must be configured")
        current = context.model_copy(update={"results": []}, deep=True)
        allowed = set(current.reference_ids + current.return_ids)
        for name in order:
            try:
                result = self.stages[name](current.model_copy(deep=True))
            except EPError:
                raise
            except Exception as exc:
                raise EPError(503, "stage_failed", f"Analysis stage failed: {name}") from exc
            if (
                not isinstance(result, StageResult)
                or result.stage != name
                or not set(result.evidence_ids).issubset(allowed)
            ):
                raise EPError(
                    503, "stage_contract", "Analysis stage violated its evidence contract"
                )
            for finding in result.findings:
                if not set(finding.reference_ids).issubset(set(context.reference_ids)) or not set(
                    finding.return_ids
                ).issubset(set(context.return_ids)):
                    raise EPError(503, "stage_contract", "Finding cited unavailable evidence")
            current.results.append(result)
            if result.abstain:
                return current
        return current
