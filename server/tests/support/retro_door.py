"""A stand-in for `retroactive.run_here` in a CLI test whose subject is what the CLI forwards
and prints, not the run record: the operation's adapter runs exactly as the door runs it,
without a record, a gate or a registered table config. The door itself is scored in
`test_a_cli_run_goes_through_the_admin_runs_door.py`."""
from admin import retroactive


class _Db:
    def __init__(self, bind):
        self._bind = bind

    def get_bind(self):
        return self._bind


def run_without_a_record(bind=None):
    def run_here(op, params, log=print):
        control = retroactive.RunControl(None, op=op)
        retroactive.operation(op)["run"](_Db(bind), retroactive.validate(op, params), log,
                                         control)
        return {"stats": control.stats}
    return run_here
