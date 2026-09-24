import pytest

from netwm.labels.mitre_map import (
    Stage,
    UnknownLabelError,
    is_attempted,
    map_label,
    stage_of,
    window_stage,
)


@pytest.mark.parametrize(
    "label,stage",
    [
        ("BENIGN", Stage.BENIGN),
        ("Portscan", Stage.RECONNAISSANCE),
        ("FTP-Patator", Stage.INITIAL_ACCESS),
        ("Web Attack - SQL Injection", Stage.INITIAL_ACCESS),
        ("Heartbleed", Stage.INITIAL_ACCESS),
        ("Infiltration", Stage.LATERAL_MOVEMENT),
        ("Infiltration - Portscan", Stage.LATERAL_MOVEMENT),
        ("Botnet", Stage.COMMAND_AND_CONTROL),
        ("DDoS", Stage.IMPACT),
        ("DoS Hulk", Stage.IMPACT),
    ],
)
def test_every_cicids2017_label_maps(label, stage):
    assert stage_of(label) is stage


def test_mojibake_dash_still_maps():
    # the original release ships "Web Attack � Brute Force"
    assert stage_of("Web Attack � Brute Force") is Stage.INITIAL_ACCESS


def test_attempted_flag_does_not_change_stage():
    assert is_attempted("Botnet - Attempted")
    assert map_label("Botnet - Attempted").stage is Stage.COMMAND_AND_CONTROL
    assert not is_attempted("Botnet")


def test_unknown_label_raises_rather_than_defaulting_to_benign():
    with pytest.raises(UnknownLabelError):
        stage_of("Some Future Attack 9000")


def test_progression_beats_impact_in_a_window():
    # D-003: a window with both a DDoS and an infiltration is an infiltration window
    assert window_stage(["DDoS", "Infiltration"]) is Stage.LATERAL_MOVEMENT
    assert window_stage(["DDoS", "BENIGN"]) is Stage.IMPACT
