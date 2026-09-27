"""G-9 / D-034: the dashboard alarms on exactly the causal rule E18 measured.

``netwm.metrics.causal_threshold`` is the one implementation; ``scripts/threshold_eval.py`` (E18) and
``engine/predict.py`` (the dashboard) both call it. These tests pin it to E18's published alarms and
check it never looks ahead.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from netwm.metrics import CAUSAL_WARMUP, causal_threshold

ROOT = Path(__file__).resolve().parents[1]
E18 = ROOT / "results" / "tables" / "e18_window_scores_e4e7-worldmodel-r2_{day}.csv"


@pytest.mark.parametrize("day", ["thursday", "friday"])
def test_reproduces_e18_published_alarms(day):
    table = pd.read_csv(str(E18).format(day=day))
    thr = causal_threshold(table["score"].to_numpy(), 0.90)
    assert ((table["score"].to_numpy() >= thr).astype(int) == table["alarm_expanding-10pct"].to_numpy()).all()
    published = table["thr_expanding-10pct"].to_numpy()
    assert np.allclose(np.where(np.isinf(thr), np.nan, thr), published, equal_nan=True)


def test_never_uses_windows_after_t():
    rng = np.random.default_rng(0)
    score = rng.random(200)
    base = causal_threshold(score)
    for t in (CAUSAL_WARMUP, 57, 150):
        changed = score.copy()
        changed[t:] = rng.random(200 - t) * 100  # rewrite the present and the future
        assert np.array_equal(causal_threshold(changed)[: t + 1], base[: t + 1])


def test_warm_up_cannot_alarm():
    score = np.ones(50)
    thr = causal_threshold(score)
    assert np.isinf(thr[:CAUSAL_WARMUP]).all() and not (score[:CAUSAL_WARMUP] >= thr[:CAUSAL_WARMUP]).any()
    assert np.isfinite(thr[CAUSAL_WARMUP:]).all()


def test_trailing_window_only_sees_its_span():
    score = np.r_[np.full(100, 10.0), np.zeros(100)]
    thr = causal_threshold(score, trailing=60)
    assert thr[99] == 10.0 and thr[199] == 0.0  # by t=199 the last 60 windows are all zero


CKPT = ROOT / "models" / "e4e7-worldmodel-r2" / "thursday.pt"
RAW = ROOT / "data" / "raw" / "cicids2017_improved" / "thursday.csv"


@pytest.mark.skipif(not (CKPT.exists() and RAW.exists()), reason="checkpoint or raw Thursday CSV missing")
def test_dashboard_payload_alarms_on_the_causal_series():
    from netwm.data.cicids2017 import CICIDS2017Adapter
    from netwm.engine.predict import analyze_flows, load_checkpoint

    flows = CICIDS2017Adapter(RAW.parent).load("thursday")
    flows = flows[(flows["ts"] >= "2017-07-06 16:40") & (flows["ts"] < "2017-07-06 17:40")]
    payload = analyze_flows(flows, load_checkpoint(CKPT), n_samples=2, explain_limit=0, explain_every=10_000)

    assert payload["threshold_policy"] == "expanding-10pct"
    tl = payload["timeline"]
    score = np.array([w["p_max"] for w in tl])
    # p_max is rounded to 4 dp in the payload; recompute the series from the served scores' order
    expected = causal_threshold(score, 0.90)
    assert all(w["threshold"] is None for w in tl[:CAUSAL_WARMUP])
    served = np.array([np.inf if w["threshold"] is None else w["threshold"] for w in tl])
    assert np.allclose(served[CAUSAL_WARMUP:], expected[CAUSAL_WARMUP:], atol=1e-4)
    assert all(w["alarm"] == (w["threshold"] is not None and w["p_max"] >= w["threshold"] - 1e-4) for w in tl)
    for run in payload["alarms"]:
        assert run["threshold"] == pytest.approx(tl[run["t"]]["threshold"], abs=1e-6)
