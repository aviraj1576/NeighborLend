import os
import sys

import pytest

from ep_engine.config import EP_ROOT
from ep_engine.core.data_policy import enforce_data_policy
from ep_engine.core.exceptions import EPError


@pytest.mark.parametrize(
    "relative",
    ["test_images/forbidden.jpeg", ".test-artifacts/real-image-evaluation/private/forbidden.png"],
)
def test_policy_blocks_paths_before_any_file_is_opened(relative):
    if os.environ.get("EP_SYNTHETIC_ONLY") != "1":
        pytest.skip("Strict milestone data policy is opt-in for general historical tests")
    # Emits an audit event only: no real image is accessed or enumerated.
    with pytest.raises(PermissionError, match="excluded"):
        sys.audit("open", str(EP_ROOT / relative), "r", 0)
    with pytest.raises(EPError) as caught:
        enforce_data_policy(EP_ROOT / relative)
    assert caught.value.code == "excluded_image_data"
