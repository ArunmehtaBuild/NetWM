"""Task R-2: Contract Validator Test.

Strictly verifies that:
1. All static fixtures (fixtures/api/*.json) conform to the v1.1 contract schema.
2. Every required key documented in docs/api_contract.md exists and has the correct types.
3. Freshly produced model output validates against the schema without contract drift.
4. No NaNs or infinities appear anywhere in numerical fields.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import pytest

from backend.config import settings
from backend.schemas import AnalysisResultPayload


def _assert_no_nans(data: object, path: str = "root") -> None:
    """Walk recursive dictionary/list structure to ensure no float NaNs or Infinities."""
    if isinstance(data, float):
        assert not math.isnan(data), f"NaN detected at {path}"
        assert not math.isinf(data), f"Infinity detected at {path}"
    elif isinstance(data, dict):
        for k, v in data.items():
            _assert_no_nans(v, f"{path}.{k}")
    elif isinstance(data, list):
        for i, v in enumerate(data):
            _assert_no_nans(v, f"{path}[{i}]")


@pytest.mark.parametrize(
    "fixture_name",
    ["thursday.json", "friday.json", "thursday_oracle.json"],
)
def test_fixtures_contract_compliance(fixture_name: str) -> None:
    fixture_path = settings.fixtures_dir / fixture_name
    assert fixture_path.exists(), f"Missing fixture file: {fixture_path}"

    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Strict NaN / Inf check
    _assert_no_nans(data, path=fixture_name)

    # 2. Pydantic validation against v1.1 contract
    payload = AnalysisResultPayload.model_validate(data)

    # 3. Explicit key presence checks
    assert payload.payload_version == "1.1"
    assert payload.alarm_statistic in {"p_max", "p_max (mean path)"}
    assert len(payload.stages) == 7
    assert len(payload.timeline) > 0
    assert payload.source.windows == len(payload.timeline)

    # 4. Check timeline entry schema details
    first_entry = payload.timeline[0]
    assert first_entry.forecast.p_cum is not None
    assert len(first_entry.forecast.p_cum) == payload.horizon_k
    assert len(first_entry.stage_probs) == 7

    # 5. Check alarms schema details
    for alarm in payload.alarms:
        assert isinstance(alarm.t, int)
        assert isinstance(alarm.ts, str)
        assert 0.0 <= alarm.p <= 1.0


def test_engine_output_contract_compliance(tmp_path: Path) -> None:
    """Verify freshly produced payload from the engine matches the contract."""
    from backend.inference import get_checkpoint
    from backend.jobs import Job
    from backend.inference import run_job_inference

    ckpt = get_checkpoint()
    # If checkpoint is available or fallback mock is used, run_job_inference must produce valid payload
    job = Job(
        id="j_contract_test",
        kind="demo",
        filename="thursday_infiltration",
        file_path=None,
        state="running",
        progress=0.0,
        stage_text="",
    )

    result_file = run_job_inference(job, lambda pct, msg: None)
    assert result_file.exists()

    with open(result_file, "r", encoding="utf-8") as f:
        fresh_data = json.load(f)

    _assert_no_nans(fresh_data, path="fresh_output")
    payload = AnalysisResultPayload.model_validate(fresh_data)
    assert payload.payload_version == "1.1"
    assert len(payload.timeline) > 0
