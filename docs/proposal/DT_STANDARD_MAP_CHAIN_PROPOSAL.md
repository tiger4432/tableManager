# DT frame to standard DT map chain proposal

> Status: approved implementation direction. This remains in `proposal` until
> the operational rollout is verified; it is not a product specification yet.

## Goal

`dt_log` is the source record. For every `dt_job`, the confirmed `dt_frame`
creates a portable DT coordinate equation, then that equation builds the
standard-coordinate `dt_map` containing `dt_x`, `dt_y`, and `c_bn`.

There are exactly two projection chains:

```text
wafer_map_metadata (target=dt_log, map_id=dt_job)
  -> dt_inventory: dt_frame + DT equation
  -> dt_map: replace scope {dt_job}, standard dt_x/dt_y/c_bn
```

No chain writes `wafer_map_metadata` for `dt_map`. The normalized coordinates
are the map's coordinate contract.

## Chain 1: dt_frame to DT equation

`dt_metadata_to_dt_inventory` receives the confirmed `dt_frame` JSON for one
`dt_job`. It saves that JSON in `dt_inventory.dt_frame` and derives:

```text
dt_x_base, dt_x_sign, dt_x_offset
dt_y_base, dt_y_sign, dt_y_offset
```

For raw DT axes in `dt_log`:

```text
standard_dt_x = select(dt_x_base, dt_log.dt_x, dt_log.dt_y) * dt_x_sign + dt_x_offset
standard_dt_y = select(dt_y_base, dt_log.dt_x, dt_log.dt_y) * dt_y_sign + dt_y_offset
```

`*_base` is `X` or `Y`; `*_sign` is `-1` or `1`; offsets are integers. The
coefficients are derived from the confirmed frame through the existing frame
transform engine, rather than duplicating rotation, side, origin, and y-invert
math in the chain mapper.

## Chain 2: equation to dt_map

`dt_inventory_to_standard_dt_map` triggers on the chain-1 update. For each
changed `dt_job`, it first upserts `wafer_map_metadata(target_table=dt_map,
map_id=dt_job)` as an ancillary write of the same chain, then reads all matching
`dt_log` rows, applies the persisted equation, and emits one scoped replacement
batch:

```text
target_table = dt_map
replace_map = true
scope = { dt_job: <changed job> }
```

The metadata is copied from `dt_frame`, with only the standard coordinate fields
overridden. Its `valid_die_ref` is explicitly read from
`wafer_map_metadata(dt_log, dt_job)`, so it remains identical even if the stored
frame predates a reference stamp. It registers
`grid_start_x = 1`, `grid_start_y = 1`, `rotation = 0`, `side = front`, and
`grid_y_invert = false`. `allow_map_metadata_upsert: true` and
`allow_replace_map: true` are required on this rule. The batch writes `dt_job`,
normalized `dt_x`, normalized `dt_y`, `dt_index`, and `c_bn`. Reconfirmation
therefore purges only that job's old map cells before inserting its current
projection; it cannot modify another job's map.

## Standard coordinate convention

The normalized output uses the fixed convention:

```text
rotation = 0
side = front
grid_start_x = 1
grid_start_y = 1
grid_y_invert = false
```

## Deliberate boundary

`core_x_*` and `core_y_*` are not derived here. A DT frame does not establish a
core frame; core equations must wait for separately confirmed core metadata.

## Rollout

Reload the chain configuration and mapper modules. New completed `dt_job`
ingests flow through both chains. Existing jobs need a replay that emits the
canonical cell payload (`data.<column>.value`) so chain 2 receives `dt_job` and
all six equation fields.
