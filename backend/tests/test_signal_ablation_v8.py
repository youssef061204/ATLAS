from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest
from atlas.rsm_v8 import parse_rsm
from atlas.signal_ablation_v8 import approximate_stage, write_approximate_signal_program


def test_completed_cycle_selects_its_own_split_without_future_state_feedback() -> None:
    rows = parse_rsm(
        "08:28:00 2 100 15 0 100 0 0 0 100 0 0\n08:29:40 2 100 15 0 65 10 20 0 65 0 30\n"
    )
    assert approximate_stage(8 * 3600 + 28 * 60 + 5, rows) == "main"
    assert approximate_stage(8 * 3600 + 29 * 60 + 6, rows) == "main_yellow"
    assert approximate_stage(8 * 3600 + 29 * 60 + 20, rows) == "cross"
    with pytest.raises(ValueError, match="after the final"):
        approximate_stage(8 * 3600 + 29 * 60 + 40, rows)


def test_rewritten_program_keeps_existing_safe_link_states() -> None:
    tree = ET.ElementTree(ET.Element("net"))
    logic = ET.SubElement(tree.getroot(), "tlLogic", id="J")
    for state in ("G", "y", "r"):
        ET.SubElement(logic, "phase", duration="1", state=state)
    ET.SubElement(
        tree.getroot(), "connection", tl="J", linkIndex="0", **{"from": "N_in", "dir": "s"}
    )
    # Coverage begins before the fixed official controller-clock origin.
    rows = parse_rsm("08:29:00 2 100 15 0 85 0 15 0 85 0 15\n")
    with pytest.raises(ValueError, match="after the final"):
        write_approximate_signal_program(tree, rows, 200)
