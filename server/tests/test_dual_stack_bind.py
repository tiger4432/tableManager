"""The backend must answer on both IP stacks, and the port guard must probe both.

THE INCIDENT THIS PINS DOWN (2026-08-04)
----------------------------------------
netstat on the live stack showed exactly one listener for the web server:

    TCP    0.0.0.0:8080    LISTENING    8444

`0.0.0.0` is the IPv4 wildcard; there was no `[::]:8080`. On Windows `localhost`
resolves to `::1` BEFORE `127.0.0.1`. So an operator reaching the app as
`localhost` got the page (the browser's HTTP falls back to IPv4) and a WebSocket
that sat in CONNECTING - no onopen, no onclose, and therefore no retry, because
the client's reconnect ladder is driven by onclose. The same server reached by
its LAN address worked at that same moment. The only variable was name
resolution.

WHY THE OBVIOUS FIX IS A WORSE BUG
----------------------------------
"Bind :: and let it be dual-stack" is wrong here. asyncio's create_server - the
path uvicorn's single-process mode uses - explicitly sets IPV6_V6ONLY=True and
binds one socket per resolved address, so `::` yields an IPv6-ONLY listener.
Measured with real uvicorn on a throwaway port:

    --host 0.0.0.0  ->  IPv4 only, ::1 refused          (the bug)
    --host ::       ->  IPv6 only, 127.0.0.1 refused    (the bug, mirrored)
    --host ""       ->  both, both accept               (the fix)

test_the_default_serves_ipv4_and_ipv6 below is written to fail on BOTH broken
rows, not just the first, because losing IPv4 while gaining IPv6 is the failure
an operator would only find out about from a user.

Real sockets, throwaway ports only. :8080 and :8090 belong to the running
production stack and are never touched.
"""
import asyncio
import os
import socket

import pytest

import process_supervisor as ps


def free_port():
    """A port number nothing is listening on."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def has_ipv6():
    """Is IPv6 usable on this box at all? The suite must not fail where it is off."""
    if not socket.has_ipv6:
        return False
    try:
        s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    except OSError:
        return False
    try:
        s.bind(("::1", 0))
        return True
    except OSError:
        return False
    finally:
        s.close()


requires_ipv6 = pytest.mark.skipif(not has_ipv6(), reason="IPv6 unavailable on this host")


def really_listens_on(host, port):
    """Bring a server up on `host` exactly as uvicorn's single-process mode does,
    and report which families ACCEPT. The point is to exercise the real bind path,
    not to assert about a string."""
    async def go():
        server = await asyncio.get_running_loop().create_server(
            lambda: asyncio.Protocol(), host=host, port=port)
        try:
            out = set()
            for family, addr in ((socket.AF_INET, "127.0.0.1"),
                                 (socket.AF_INET6, "::1")):
                s = socket.socket(family, socket.SOCK_STREAM)
                s.settimeout(3.0)
                try:
                    s.connect((addr, port))
                    out.add("IPv4" if family == socket.AF_INET else "IPv6")
                except OSError:
                    pass
                finally:
                    s.close()
            return out
        finally:
            server.close()
            await server.wait_closed()

    return asyncio.run(go())


# ===========================================================================
# (1) The default bind reaches both stacks - and does not lose either one.
# ===========================================================================

@requires_ipv6
def test_the_default_serves_ipv4_and_ipv6():
    """The regression itself, asserted by connecting rather than by reading config.

    Both halves are load-bearing and they fail on opposite defects: the IPv6 half
    goes red on today's `0.0.0.0`, the IPv4 half goes red on the naive `::`.
    """
    accepting = really_listens_on(ps.DUAL_STACK_HOST, free_port())
    assert "IPv6" in accepting, (
        "the default bind does not accept on ::1 - this is the original incident: "
        "`localhost` resolves to ::1 first on Windows and the WebSocket hangs")
    assert "IPv4" in accepting, (
        "the default bind lost IPv4 - a careless dual-stack fix that swaps the "
        "outage for its mirror image, which only a user would notice")


@requires_ipv6
def test_binding_the_ipv6_wildcard_alone_would_have_dropped_ipv4():
    """Why DUAL_STACK_HOST is "" and not "::". Guards the reasoning, not the value.

    If a future edit "simplifies" the default to "::", the test above goes red -
    and this one explains why by showing that `::` really is IPv6-only here.
    """
    assert really_listens_on("::", free_port()) == {"IPv6"}, (
        "`::` behaved as a dual-stack socket on this platform; the comment in "
        "process_supervisor.DUAL_STACK_HOST is now wrong and must be re-measured")


# ===========================================================================
# (2) ASSY_API_HOST keeps working EXACTLY as it did. Only the default moved.
# ===========================================================================

def test_an_explicit_narrow_host_is_still_narrow_and_still_ipv4():
    """The variable exists so an operator can narrow the bind. If the dual-stack
    default leaked into explicit values it would silently WIDEN a deployment that
    was deliberately restricted - the opposite of what the operator asked for."""
    assert ps.bind_targets("127.0.0.1") == ((socket.AF_INET, "127.0.0.1"),)
    assert really_listens_on("127.0.0.1", free_port()) == {"IPv4"}


def test_an_explicit_wildcard_still_means_exactly_what_it_meant_yesterday():
    """Someone who typed 0.0.0.0 typed an address. Only the DEFAULT changed."""
    assert ps.bind_targets("0.0.0.0") == ((socket.AF_INET, "0.0.0.0"),)


def test_the_launcher_default_is_the_dual_stack_host():
    """The launcher must read its default from the one place that documents it,
    so the guard and the bind cannot drift apart."""
    import run_decoupled_app  # noqa: F401  (imported for its module source)
    src = open(os.path.join(
        os.path.dirname(os.path.abspath(run_decoupled_app.__file__)),
        "run_decoupled_app.py"), encoding="utf-8").read()
    assert 'os.environ.get("ASSY_API_HOST", DUAL_STACK_HOST)' in src, \
        "the launcher stopped defaulting to the shared dual-stack constant"


# ===========================================================================
# (3) The pre-flight guard probes what is REALLY bound.
# ===========================================================================

@requires_ipv6
def test_the_guard_catches_a_holder_that_owns_only_the_ipv6_wildcard():
    """The guard's whole job, in the case the old guard could not see.

    Measured: with only `[::]:P` held and `0.0.0.0:P` verifiably free, a
    dual-stack create_server does NOT come up half-bound - it raises and the child
    dies. The old guard hardcoded AF_INET, so it would have called this port free
    and handed back the silent startup failure the gate exists to prevent.
    """
    port = free_port()
    held = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    held.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, True)
    held.bind(("::", port))
    held.listen(1)
    try:
        # The premise: IPv4 really is free, so an IPv4-only guard sees nothing.
        v4 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            v4.bind(("0.0.0.0", port))
        except OSError:
            pytest.skip("this platform blocks the IPv4 wildcard too; premise absent")
        finally:
            v4.close()

        conflicts = ps.preflight_port_check([port], host=ps.DUAL_STACK_HOST)
        assert conflicts, (
            "the guard called a port free that the server cannot bind - it is "
            "probing a different address than the server uses")
        assert str(port) in conflicts[0][1]
    finally:
        held.close()


@requires_ipv6
def test_the_bind_probe_alone_catches_an_ipv6_holder_that_is_not_accepting():
    """Isolates the BIND probe from the connect probe, which is the only way this
    file can actually score the guard's family-awareness.

    Found by injecting the defect: reverting the guard's probe to a hardcoded
    AF_INET left the suite GREEN, because the holder in the test above was
    listening and the connect probe to ::1 caught it instead. The OR rescued the
    mutation, so that test scores "the guard noticed", not "the guard probes both
    families". A holder that has BOUND `[::]:P` without calling listen() blocks
    the server's bind exactly the same way while accepting nothing at all - so
    the connect probe is blind by construction and only a family-aware bind probe
    can answer.
    """
    port = free_port()
    held = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    held.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, True)
    held.bind(("::", port))   # deliberately NOT listen()
    try:
        # Premise 1: nothing is accepting, so the connect probe cannot help.
        probe = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        probe.settimeout(2.0)
        try:
            probe.connect(("::1", port))
            pytest.skip("something is accepting on ::1; premise absent")
        except OSError:
            pass
        finally:
            probe.close()
        # Premise 2: the server really would fail, i.e. this is not a false alarm.
        with pytest.raises(OSError):
            asyncio.run(_try_dual_bind(port))

        taken, how = ps.port_is_taken(port, host=ps.DUAL_STACK_HOST)
        assert taken, (
            "the bind probe missed an IPv6 holder that blocks startup and accepts "
            "nothing - the guard is probing a different family than the server binds")
        assert "bind failed" in how, f"caught by the wrong probe: {how!r}"
    finally:
        held.close()


async def _try_dual_bind(port):
    server = await asyncio.get_running_loop().create_server(
        lambda: asyncio.Protocol(), host=ps.DUAL_STACK_HOST, port=port)
    server.close()
    await server.wait_closed()


def test_the_guard_still_catches_an_ipv4_holder_under_the_new_default():
    """The direction that already worked must not have been traded away."""
    port = free_port()
    held = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    held.bind(("0.0.0.0", port))
    held.listen(1)
    try:
        assert ps.preflight_port_check([port], host=ps.DUAL_STACK_HOST), \
            "the guard lost the IPv4 conflict it used to catch"
    finally:
        held.close()


def test_the_guard_says_nothing_about_a_free_port_under_the_new_default():
    """The control. Without it "always refuses" would pass both tests above -
    and a guard that always refuses is a stack that never starts."""
    assert ps.preflight_port_check([free_port()], host=ps.DUAL_STACK_HOST) == []


def test_the_guard_probes_every_family_the_server_will_bind():
    """The structural invariant behind the three tests above: the guard's probe
    set IS the server's bind set, by construction rather than by coincidence."""
    for host in (ps.DUAL_STACK_HOST, "127.0.0.1", "0.0.0.0", "::1"):
        targets = ps.bind_targets(host)
        assert targets, f"no bind target derived for {host!r}"
        for family, addr in targets:
            s = socket.socket(family, socket.SOCK_STREAM)
            try:
                s.bind((addr, 0))  # proves the family/address pair is real
            finally:
                s.close()


# ===========================================================================
# (4) What the operator is told matches what is bound.
# ===========================================================================

def test_the_startup_line_names_real_addresses_not_the_empty_string():
    """uvicorn's own line echoes config.host verbatim and prints `http://:8080`
    for the dual bind, naming neither listening address. The launcher's line is
    the one an operator can act on, so it must name them."""
    shown = ps.describe_bind_host(ps.DUAL_STACK_HOST)
    assert shown.strip(), "the startup line would show an empty address"
    for _family, addr in ps.bind_targets(ps.DUAL_STACK_HOST):
        assert addr in shown, f"{addr} is bound but not reported to the operator"
    assert ps.describe_bind_host("127.0.0.1") == "127.0.0.1"
