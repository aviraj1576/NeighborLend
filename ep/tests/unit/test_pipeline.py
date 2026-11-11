from uuid import uuid4

import pytest

from ep_engine.core.exceptions import EPError
from ep_engine.pipeline.interfaces import STAGE_ORDER, PipelineContext, StageResult
from ep_engine.pipeline.orchestrator import Orchestrator


def test_pipeline_unavailable_never_fabricates_results():
    context = PipelineContext(inspection_id=uuid4(), reference_ids=[uuid4()], return_ids=[uuid4()])
    with pytest.raises(EPError) as caught:
        Orchestrator().run(context)
    assert caught.value.code == "pipeline_unavailable"


def test_order_and_injected_dependency_failure():
    seen = []
    context = PipelineContext(inspection_id=uuid4(), reference_ids=[uuid4()], return_ids=[uuid4()])

    def make(stage):
        def execute(current):
            assert [result.stage for result in current.results] == seen
            seen.append(stage)
            if stage == "image_alignment":
                raise OSError("private model path")
            return StageResult(stage=stage, evidence_ids=current.reference_ids + current.return_ids)

        return execute

    pipeline = Orchestrator({stage: make(stage) for stage in STAGE_ORDER})
    with pytest.raises(EPError) as caught:
        pipeline.run(context)
    assert seen == list(STAGE_ORDER[:5])
    assert caught.value.code == "stage_failed"
    assert "private" not in caught.value.message


def test_pipeline_rejects_misordered_or_uncited_output():
    context = PipelineContext(inspection_id=uuid4(), reference_ids=[uuid4()], return_ids=[uuid4()])
    for result in (
        StageResult(stage="damage_verification", evidence_ids=context.reference_ids),
        StageResult(stage="image_quality", evidence_ids=[uuid4()]),
    ):
        pipeline = Orchestrator({stage: lambda _, value=result: value for stage in STAGE_ORDER})
        with pytest.raises(EPError) as caught:
            pipeline.run(context)
        assert caught.value.code == "stage_contract"


def test_orchestration_contract_success_abstention_and_domain_failure():
    context = PipelineContext(inspection_id=uuid4(), reference_ids=[uuid4()], return_ids=[uuid4()])

    def make(stage, abstain=False):
        return lambda current: StageResult(
            stage=stage, evidence_ids=current.reference_ids, abstain=abstain
        )

    stages = {stage: make(stage) for stage in STAGE_ORDER}
    result = Orchestrator(stages).run(context)
    assert [item.stage for item in result.results] == list(STAGE_ORDER)
    assert context.results == []
    stages["viewpoint_matching"] = make("viewpoint_matching", abstain=True)
    assert len(Orchestrator(stages).run(context).results) == 4

    def unavailable(_):
        raise EPError(503, "model_unavailable", "Required model unavailable")

    stages["image_quality"] = unavailable
    with pytest.raises(EPError) as caught:
        Orchestrator(stages).run(context)
    assert caught.value.code == "model_unavailable"
