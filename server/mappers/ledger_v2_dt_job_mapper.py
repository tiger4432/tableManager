"""Ledger v2 Role mapper for one dt_job's worth of dt_log rows.

⚰️ RETIRED IN THE DECLARATION, KEPT FOR ONE DEPLOY (S-100 ⓐ, 판정 211). The shipped sample no
longer names this: the count is computed by the chain rule `dt_log_to_dt_job_rollup` and read
declaratively from `dt_job_rollup`, because a ledger declaration is local and
calculation-free and this mapper was the ledger computing.

⛔ IT IS NOT DELETED YET, AND THE REASON IS DEPLOYMENT ORDER RATHER THAN DOUBT. A trusted
implementation is derived from the classes that EXIST, so removing this class makes every
deployment whose `ledger_config.json` still says `dt-job-role` fail to compile - and that is
not one source stopping, it is the whole setup refusing. Measured 2026-09-09: deleting it
turned six `test_ledger_setup_boundary` cases red on this box alone, because the box's own
(gitignored) declaration still names it. Production has its own such file.

So the order is: this declaration ships -> each deployment's own declaration moves to
`dt_job_rollup` -> THEN the class goes. Deleting it first is the same shape as the self-edge
check that refused the live setup on 2026-09-09 and had to be narrowed the same day.

A dt_job is not one row: the count only exists once the rows are grouped, which is why this
needed a mapper at all rather than the generic declarative one.
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
