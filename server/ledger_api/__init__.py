"""Read-side modules behind the ledger console's HTTP routes.

WHAT BELONGS HERE
-----------------
A module that answers a ledger read -- a census, a contrast, a subgraph, a kind
registry, a selection -- and is reached only through `ledger_trace_router` or
another module in this package.  Nothing here is imported by a write path, by a
worker, or by boot: `server/main.py` names exactly one member of this package
(`ontology_config_explorer_router`) and reaches the rest through the router.

WHY IT IS A PACKAGE AND NOT A NAMING CONVENTION
-----------------------------------------------
`server/` root is the import root for every runtime process, so a flat file there
is addressable from anywhere and a reader cannot tell a read-side helper from a
worker entry point by looking.  A package makes the boundary a fact the import
statement has to state.

WHAT IS DELIBERATELY NOT HERE
-----------------------------
Several root-level `ledger_*` modules read the ledger too and were left at
`server/` root on purpose -- they are inside a retirement fence and moving them
would only make the deletion diff harder to read.  `server/` root is therefore
not evidence that a module is write-side; the fence is recorded with the
retirement, not here, so that this docstring cannot go stale as members leave.
"""
