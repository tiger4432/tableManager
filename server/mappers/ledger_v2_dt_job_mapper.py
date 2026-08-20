"""Ledger v2 Role mapper for one dt_job's worth of dt_log rows.

A dt_job is not one row: the count only exists once the rows are grouped, which is why
this needs a mapper at all rather than the generic declarative one.
"""
from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from ledger.roleframe import (
    BaseLedgerMapper,
    MapperContext,
    ProfileSentences,
    RoleEmission,
    RoleFrameError,
    SentenceShape,
    SOURCE_OCCURRED_AT_COLUMN,
    SOURCE_ROW_REF_COLUMN,
)
from ledger.setup_registry import ProfileDescriptor

DT_JOB_COLUMN = "dt_job"


class DtJobRoleMapper(BaseLedgerMapper):
    """One dt_job -> "this job exists" and "it carries this many"."""

    implementation_id = "dt-job-role"
    implementation_version = 1

    #: "this job exists".
    REGISTER = SentenceShape()
    #: "this job carries this many".
    COUNTED = SentenceShape()

    def interpret_unit(
        self,
        context: MapperContext,
        unit: pd.DataFrame,
        profile: ProfileDescriptor,
    ) -> Sequence[RoleEmission]:
        jobs = unit[DT_JOB_COLUMN].unique()
        if len(jobs) != 1:
            raise RoleFrameError(
                "invalid_dt_job_unit", "event_frame.dt_job",
                f"one unit must carry exactly one dt_job, got {len(jobs)}")
        job = str(jobs[0])

        # The declaration says where this source's time comes from -- a world-time column
        # or an admitted basis -- and the preparation boundary has already resolved it to
        # one instant under one engine-owned name. `basis` and `column` are read the same
        # way here, which is the point: a different deployment changes the declaration,
        # not this file.
        sentences = ProfileSentences(
            context, profile, occurred_at=unit.iloc[0][SOURCE_OCCURRED_AT_COLUMN])

        refs = unit[SOURCE_ROW_REF_COLUMN].tolist()
        count = len(unit)

        return [
            sentences.say(self.REGISTER, job, refs),
            sentences.say(self.COUNTED, job, refs, obj=count),
        ]
