"""D-038 / D-041: CSV input is served by a flow-only model (r2w seed 42), PCAP input by the mean of the
three E20rw seeds - both retrained with window positions (the N-8 fix).

The routing tests build tiny synthetic checkpoints with E20r's feature layout (flow + CSV packet
block + the 18 ``pcap_`` features, no ``has_pcap``) and the served models' ``pos_mode``, so they run
on any clone. The last group loads the real served checkpoints and skips when they are absent
(``models/`` is not tracked).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch

scapy = pytest.importorskip("scapy.all")
from scapy.all import IP, TCP, Ether, wrpcap  # noqa: E402

import backend.inference as inference  # noqa: E402
from backend.errors import APIError  # noqa: E402
from backend.jobs import Job  # noqa: E402
from backend.schemas import AnalysisResultPayload  # noqa: E402
from netwm.data.cicids2017 import COLUMN_MAP  # noqa: E402
from netwm.engine import predict  # noqa: E402
from netwm.features.flow_aggregator import pcap_to_flows  # noqa: E402
from netwm.features.flow_features import PACKET_CSV_FEATURES  # noqa: E402
from netwm.features.packet_windows import HAS_PCAP, PCAP_WINDOW_FEATURES  # noqa: E402
from netwm.features.scaler import StateScaler  # noqa: E402
from netwm.features.windowing import WindowSpec  # noqa: E402
from netwm.metrics import causal_threshold  # noqa: E402
from netwm.models.world_model import WorldModelConfig, build_model  # noqa: E402

T0 = 1_499_353_200.0  # 2017-07-06 15:00:00 UTC
SPEC = WindowSpec(60.0, 30.0)
SEEDS = (42, 43, 44)
MODELS = Path(__file__).resolve().parents[2] / "models"
REAL = [MODELS / run / "thursday.pt" for run in inference.PCAP_ENSEMBLE_RUNS]
REAL_CSV = MODELS / inference.CSV_ROUTE_RUN / "thursday.pt"


def _capture(path: Path, minutes: int = 30, seed: int = 7) -> Path:
    """~30 minutes of TCP handshakes with varied hosts, ports, TTLs and windows (60 windows, past the
    causal threshold's 20-window warm-up)."""
    rng = np.random.default_rng(seed)
    pkts = []
    for i in range(minutes * 20):
        t = T0 + i * 3.0
        src, dst = f"192.168.10.{rng.integers(2, 40)}", f"205.174.165.{rng.integers(2, 60)}"
        sport, dport = int(rng.integers(40000, 60000)), int(rng.choice([80, 443, 22, 445, 8080]))
        ttl, win = int(rng.choice([54, 64, 128])), int(rng.choice([0, 512, 8192, 29200]))
        steps = (("S", 0, False), ("SA", 0, True), ("A", 0, False), ("PA", int(rng.integers(1, 900)), False))
        for j, (flags, size, back) in enumerate(steps):
            a, b, sp, dp = (dst, src, dport, sport) if back else (src, dst, sport, dport)
            p = Ether() / IP(src=a, dst=b, ttl=ttl) / TCP(sport=sp, dport=dp, flags=flags, window=win) / (b"x" * size)
            p.time = t + 0.05 * j
            pkts.append(p)
    wrpcap(str(path), pkts)
    return path


def _flow_csv(path: Path, minutes: int = 30, seed: int = 42) -> Path:
    rng = np.random.default_rng(seed)
    n = minutes * 40
    df = pd.DataFrame({col: rng.integers(0, 1000, n) for col in COLUMN_MAP})
    df["Timestamp"] = (pd.Timestamp("2017-07-06 15:00:00") + pd.to_timedelta(np.sort(rng.uniform(0, minutes * 60, n)), unit="s")
                       ).strftime("%Y-%m-%d %H:%M:%S.%f")
    df["Src IP"] = [f"192.168.10.{i}" for i in rng.integers(2, 60, n)]
    df["Dst IP"] = [f"205.174.165.{i}" for i in rng.integers(2, 90, n)]
    df["Protocol"] = 6
    df["Label"] = "BENIGN"
    df.to_csv(path, index=False)
    return path


def _e20r_names(pcap: Path) -> list[str]:
    """E20r's layout, as the live builder produces it: v1 + CSV packet block + pcap_, no has_pcap."""
    probe = [*PACKET_CSV_FEATURES, *PCAP_WINDOW_FEATURES]
    feats, *_ = predict.state_matrix(pcap_to_flows(pcap), probe, SPEC, pcap)
    return [c for c in feats.columns if c != HAS_PCAP]


def _save_ckpt(path: Path, names: list[str], frame: pd.DataFrame, seed: int) -> Path:
    torch.manual_seed(seed)
    cfg = WorldModelConfig(n_features=len(names), embed_dim=16, hidden_dim=16, latent_dim=4, context_len=4,
                           n_heads=2, n_layers=1, horizon_k=3, pos_mode="window")   # as served (D-041)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "model_state": build_model(cfg).state_dict(),
        "model_config": cfg.as_dict(),
        "feature_names": names,
        "scaler": StateScaler().fit(frame[names]),
        "train_days": ["monday", "tuesday", "wednesday", "friday"],
        "test_day": "thursday",
        "horizon_k": 3,
        "stride_s": 30.0,
        "threshold": 0.9,  # a stored train-tuned scalar: the PCAP route must never serve it
        "git_sha": f"synthetic-{seed}",
    }, path)
    return path


@pytest.fixture()
def pcap(tmp_path: Path) -> Path:
    return _capture(tmp_path / "capture.pcap")


@pytest.fixture()
def e20r_like(tmp_path: Path, pcap: Path) -> list[Path]:
    names = _e20r_names(pcap)
    frame, *_ = predict.state_matrix(pcap_to_flows(pcap), names, SPEC, pcap)
    return [_save_ckpt(tmp_path / "models" / f"m1v2-e20r-s{s}" / "thursday.pt", names, frame, s) for s in SEEDS]


@pytest.fixture()
def r2_like(tmp_path: Path) -> Path:
    csv = _flow_csv(tmp_path / "flows.csv")
    feats, *_ = predict.state_matrix(predict.read_flow_csv(csv), ["n_flows"], SPEC, None)
    return _save_ckpt(tmp_path / "models" / "r2" / "thursday.pt", list(feats.columns), feats, 1)


@pytest.fixture()
def route_to(monkeypatch, e20r_like, r2_like):
    """Point the backend at the synthetic checkpoints and fail loudly on any cross-route load."""
    inference._ensemble_cache.clear()
    monkeypatch.setattr(inference, "pcap_ensemble_paths", lambda day=None: list(e20r_like))
    monkeypatch.setattr(inference, "get_checkpoint", lambda name=None: predict.load_checkpoint(r2_like))
    yield
    inference._ensemble_cache.clear()


def _run(path: Path, kind: str) -> dict:
    import json

    job = Job(id=f"j_route_{kind}", kind=kind, filename=path.name, file_path=path, state="running",
              progress=0.0, stage_text="")
    return json.loads(inference.run_job_inference(job, lambda pct, msg: None).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------------------- routing


def test_csv_upload_is_served_by_r2_and_builds_no_packet_inputs(tmp_path, monkeypatch, route_to, r2_like):
    def no_packets(*a, **k):
        raise AssertionError("a CSV upload must not read packets")

    def no_ensemble(*a, **k):
        raise AssertionError("a CSV upload must not load the PCAP ensemble")

    monkeypatch.setattr(predict, "read_packets", no_packets)
    monkeypatch.setattr(inference, "get_pcap_ensemble", no_ensemble)
    payload = _run(_flow_csv(tmp_path / "up.csv"), "csv")
    inf = payload["inference"]
    assert inf["input_modality"] == "csv" and inf["telemetry"] == "flow"
    assert inf["model_mode"] == "flow-only"
    assert inf["checkpoints"] == [str(r2_like)]
    assert inf["packet_features"] == "unavailable (flow input)"
    assert payload["source"]["packet_features"] == "unavailable (flow input)"
    AnalysisResultPayload.model_validate(payload)


def test_pcap_upload_is_served_by_all_three_members_with_packet_features(monkeypatch, route_to, pcap, e20r_like):
    calls = []
    real_read = predict.read_packets
    monkeypatch.setattr(predict, "read_packets", lambda p, *a, **k: calls.append(p) or real_read(p, *a, **k))

    def no_r2(*a, **k):
        raise AssertionError("the PCAP route must never load r2")

    monkeypatch.setattr(inference, "get_checkpoint", no_r2)
    payload = _run(pcap, "pcap")
    inf = payload["inference"]
    assert inf["input_modality"] == "pcap" and inf["telemetry"] == "flow + packet"
    assert inf["model_mode"] == "packet-enriched ensemble of 3"
    assert inf["checkpoints"] == [str(p) for p in e20r_like]
    assert inf["packet_features"] == "measured from the capture"
    assert len(calls) == 1  # the packet block is built once and shared by the members
    assert payload["threshold_policy"] == "expanding-10pct"  # never the members' stored 0.9
    AnalysisResultPayload.model_validate(payload)


def test_pcap_route_never_falls_back_to_r2_or_a_fixture(monkeypatch, tmp_path, pcap, e20r_like):
    inference._ensemble_cache.clear()
    missing = tmp_path / "models" / "m1v2-e20r-s44" / "missing.pt"
    monkeypatch.setattr(inference, "pcap_ensemble_paths", lambda day=None: [*e20r_like[:2], missing])

    def forbidden(*a, **k):
        raise AssertionError("fallback taken")

    monkeypatch.setattr(inference, "get_checkpoint", forbidden)
    monkeypatch.setattr(inference, "_load_fallback_fixture", forbidden)
    with pytest.raises(APIError) as err:
        _run(pcap, "pcap")
    assert err.value.code == "no_model" and "missing.pt" in err.value.message


def test_a_packet_model_refuses_a_flow_csv(pcap, e20r_like):
    """E20r has no absent-packet input: fed a CSV it would see zeros it never trained on."""
    ckpt = predict.load_checkpoint(e20r_like[0])
    with pytest.raises(ValueError, match="PCAP uploads only"):
        predict.state_matrix(pcap_to_flows(pcap), ckpt["feature_names"], SPEC, None)


# --------------------------------------------------------------------------------- the ensemble


def test_members_share_one_window_grid_and_the_score_is_their_mean(pcap, e20r_like):
    flows = pcap_to_flows(pcap)
    ensemble = predict.load_ensemble(e20r_like)
    both = predict.analyze_flows(flows, ensemble, n_samples=4, pcap_path=pcap)
    singles = [predict.analyze_flows(flows, predict.load_checkpoint(p), n_samples=4, pcap_path=pcap) for p in e20r_like]
    lengths = {len(s["timeline"]) for s in singles} | {len(both["timeline"])}
    assert len(lengths) == 1
    assert [e["ts"] for e in both["timeline"]] == [e["ts"] for e in singles[0]["timeline"]]
    member = np.array([[e["p_max"] for e in s["timeline"]] for s in singles])
    mean = np.array([e["p_max"] for e in both["timeline"]])
    np.testing.assert_allclose(mean, member.mean(axis=0), atol=2e-4)  # payloads round to 4 dp


def test_the_causal_threshold_is_applied_once_to_the_mean(monkeypatch, pcap, e20r_like):
    flows = pcap_to_flows(pcap)
    ensemble = predict.load_ensemble(e20r_like)
    seen = []
    monkeypatch.setattr(predict, "causal_threshold", lambda s, q: seen.append((np.array(s), q)) or causal_threshold(s, q))
    payload = predict.analyze_flows(flows, ensemble, n_samples=4, pcap_path=pcap)
    assert len(seen) == 1 and seen[0][1] == pytest.approx(0.90)
    names = ensemble["feature_names"]
    feats, *_ = predict.state_matrix(flows, names, SPEC, pcap)
    member = [predict._forecast(m, m["scaler"].transform(feats[names]), 3, 1, True)["p_max"] for m in ensemble["members"]]
    np.testing.assert_allclose(seen[0][0], np.mean(member, axis=0), rtol=1e-6)
    assert payload["threshold_policy"] == "expanding-10pct"


def test_the_ensemble_alarm_score_is_deterministic(pcap, e20r_like):
    flows = pcap_to_flows(pcap)
    ensemble = predict.load_ensemble(e20r_like)
    a, b = (predict.analyze_flows(flows, ensemble, n_samples=4, pcap_path=pcap) for _ in range(2))
    assert [e["p_max"] for e in a["timeline"]] == [e["p_max"] for e in b["timeline"]]
    assert [e["alarm"] for e in a["timeline"]] == [e["alarm"] for e in b["timeline"]]


def test_no_lookahead_in_scaling_or_threshold(pcap, e20r_like):
    """D-038 criterion 1: the scaler is a per-window transform and the causal threshold at t reads
    windows before t only - no whole-capture statistic or future window enters either."""
    flows = pcap_to_flows(pcap)
    ensemble = predict.load_ensemble(e20r_like)
    names = ensemble["feature_names"]
    feats, *_ = predict.state_matrix(flows, names, SPEC, pcap)
    cut = len(feats) // 2
    scores = []
    for m in ensemble["members"]:
        x = m["scaler"].transform(feats[names])
        np.testing.assert_array_equal(m["scaler"].transform(feats[names].iloc[:cut]), x[:cut])
        scores.append(predict._forecast(m, x, 3, 1, True)["p_max"])
    full = np.mean(scores, axis=0)
    np.testing.assert_array_equal(causal_threshold(full[:cut], 0.9), causal_threshold(full, 0.9)[:cut])


def test_forecast_is_prefix_invariant(pcap, e20r_like):
    """A window's score must not change when later windows are appended (a live stream's view). Was a
    strict xfail until D-041: the interp positions stretched to the input length (N-8, E27 finding 5)."""
    flows = pcap_to_flows(pcap)
    ensemble = predict.load_ensemble(e20r_like)
    names = ensemble["feature_names"]
    feats, *_ = predict.state_matrix(flows, names, SPEC, pcap)
    cut = len(feats) // 2
    for m in ensemble["members"]:
        x = m["scaler"].transform(feats[names])
        full = predict._forecast(m, x, 3, 1, True)["p_max"]
        part = predict._forecast(m, x[:cut], 3, 1, True)["p_max"]
        np.testing.assert_allclose(part, full[:cut], rtol=1e-5, atol=1e-7)


def test_members_of_different_folds_are_refused(tmp_path, pcap, e20r_like):
    other = torch.load(e20r_like[2], weights_only=False)
    other["train_days"] = ["monday", "tuesday", "wednesday", "thursday"]
    torch.save(other, tmp_path / "friday_fold.pt")
    with pytest.raises(ValueError, match="not one fold"):
        predict.load_ensemble([*e20r_like[:2], tmp_path / "friday_fold.pt"])


# ------------------------------------------------------------------- the real E20r checkpoints


needs_e20r = pytest.mark.skipif(not all(p.exists() for p in REAL), reason="E20r checkpoints not in models/")


@needs_e20r
def test_the_real_e20r_checkpoints_are_one_method_reading_real_packets():
    """D-038 Step 2: same architecture, same 105 inputs in the same order, one fold, the 18 pcap_
    features present and no has_pcap."""
    ensemble = predict.load_ensemble(REAL)
    names = ensemble["feature_names"]
    assert len(names) == 105
    assert set(PCAP_WINDOW_FEATURES) <= set(names) and set(PACKET_CSV_FEATURES) <= set(names)
    assert HAS_PCAP not in names
    params = {sum(p.numel() for p in m["model"].parameters()) for m in ensemble["members"]}
    assert params == {593_500}
    configs = [m["model_config"] for m in ensemble["members"]]
    assert all(c == configs[0] for c in configs)


@needs_e20r
def test_the_served_pcap_checkpoints_are_prefix_invariant(pcap):
    """D-041 G1 on the real served models: window positions, and no window's score moves when the
    capture continues."""
    ensemble = predict.load_ensemble(REAL)
    names = ensemble["feature_names"]
    feats, *_ = predict.state_matrix(pcap_to_flows(pcap), names, SPEC, pcap)
    cut = len(feats) // 2
    for m in ensemble["members"]:
        assert m["model_config"]["pos_mode"] == "window"
        x = m["scaler"].transform(feats[names])
        full = predict._forecast(m, x, 10, 1, True)["p_max"]
        np.testing.assert_allclose(predict._forecast(m, x[:cut], 10, 1, True)["p_max"], full[:cut], rtol=1e-5, atol=1e-7)


@pytest.mark.skipif(not REAL_CSV.exists(), reason="CSV-route checkpoint not in models/")
def test_the_served_csv_checkpoint_is_prefix_invariant(tmp_path):
    ckpt = predict.load_checkpoint(REAL_CSV)
    assert ckpt["model_config"]["pos_mode"] == "window"
    names = ckpt["feature_names"]
    feats, *_ = predict.state_matrix(predict.read_flow_csv(_flow_csv(tmp_path / "flows.csv")), names, SPEC, None)
    x = ckpt["scaler"].transform(feats[names])
    cut = len(x) // 2
    full = predict._forecast(ckpt, x, 10, 1, True)["p_max"]
    np.testing.assert_allclose(predict._forecast(ckpt, x[:cut], 10, 1, True)["p_max"], full[:cut], rtol=1e-5, atol=1e-7)


@needs_e20r
def test_the_live_builder_produces_every_e20r_input(pcap):
    """The live PCAP path builds each of E20r's 105 inputs (the values' parity with training is
    scripts/pcap_route_parity.py's job, on the processed matrices)."""
    names = predict.load_ensemble(REAL)["feature_names"]
    feats, *_ = predict.state_matrix(pcap_to_flows(pcap), names, SPEC, pcap)
    assert set(names) <= set(feats.columns)
