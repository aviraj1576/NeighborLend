from uuid import uuid4

import pytest

from ep_engine.core.exceptions import EPError
from ep_engine.pipeline.interfaces import STAGE_ORDER, PipelineContext, StageResult
from ep_engine.pipeline.orchestrator import Orchestrator
from ep_engine.schemas.models import Finding


def test_adapter_wrong_output_is_a_sanitized_contract_failure():
    context = PipelineContext(inspection_id=uuid4(), reference_ids=[uuid4()], return_ids=[uuid4()])
    stages = {stage: lambda _: None for stage in STAGE_ORDER}
    with pytest.raises(EPError) as caught:
        Orchestrator(stages).run(context)
    assert caught.value.code == "stage_contract"


def test_adapter_cannot_cite_finding_from_other_inspection():
    context = PipelineContext(inspection_id=uuid4(), reference_ids=[uuid4()], return_ids=[uuid4()])
    ungrounded = Finding(
        suspected_damage="uncertain",
        severity="uncertain",
        affected_region="front",
        reference_ids=[uuid4()],
        return_ids=context.return_ids,
        supporting_observations=["Synthetic contract test only"],
    )

    def make(stage):
        return lambda _: StageResult(
            stage=stage, evidence_ids=context.reference_ids, findings=[ungrounded]
        )

    with pytest.raises(EPError) as caught:
        Orchestrator({stage: make(stage) for stage in STAGE_ORDER}).run(context)
    assert caught.value.code == "stage_contract"
