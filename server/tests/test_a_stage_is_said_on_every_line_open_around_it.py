"""Lead 11-10: the retroactive run's step line, the chain group's line and the request's slow line were three copies of
one stage recorder - now one `runtime.stages.stage`, and only the line it lands on differs.

A stage is handed to every line open around it. A line that sums its stages (the group's, the request's) takes the
outer stage only; the run's takes the inner ones too - its beat names the innermost.
"""
from admin import retroactive
from maps import alignment_batch_counts
from runtime import request_timing
from runtime import stages


def _three_lines(lines):
    control = retroactive.RunControl(None, op="probe_op", log=lines.append)
    control.debug = True
    return control


def test_one_stage_lands_on_every_line_open_around_it():
    lines = []
    control = _three_lines(lines)
    began = request_timing.begin("/probe")
    try:
        with stages.receiving(control), alignment_batch_counts.counting_group() as summary:
            with stages.stage("write:t", rows=7):
                assert [name for name, _since, _rows in control.stages] == ["write:t"]
            group = summary()
        asked = request_timing.spent()["stages"]
    finally:
        request_timing.end(began, None, None, None)
    assert [line.split(": ", 1)[1].split(" · ")[:2] for line in lines] == [["write:t", "7 rows"]]
    assert list(group["stages"]) == ["write:t"]
    assert [one[0] for one in asked] == ["write:t"]
    assert control.stages == []


def test_a_line_that_sums_its_stages_takes_the_outer_one_only():
    lines = []
    control = _three_lines(lines)
    began = request_timing.begin("/probe")
    try:
        with stages.receiving(control), alignment_batch_counts.counting_group() as summary:
            with stages.stage("outer"):
                with stages.stage("inner") as told:
                    told["note"] = "said"
                    assert [name for name, _since, _rows in control.stages] == ["outer", "inner"]
            group = summary()
        asked = request_timing.spent()["stages"]
    finally:
        request_timing.end(began, None, None, None)
    assert [line.split(": ", 1)[1].split(" · ")[0] for line in lines] == ["inner", "outer"]
    assert lines[0].endswith(" · said")
    assert list(group["stages"]) == ["outer"]
    assert [one[0] for one in asked] == ["outer"]

