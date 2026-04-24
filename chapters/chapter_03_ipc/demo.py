"""Chapter 3 demo — filesystem IPC and the ticket state machine.

Run:

    python -m chapters.chapter_03_ipc.demo

Shows:
  - Atomic write + read of an IPC message.
  - A ticket going pending -> running -> success with a verified manifest.
  - A ticket correctly REFUSING to succeed when the manifest's sha256 is wrong.

Session artifacts go to your user-data directory so you can inspect them
afterwards:

    Linux:   ~/.local/share/sovereign-agent/demos/ch3/
    macOS:   ~/Library/Application Support/sovereign-agent/demos/ch3/
    Windows: %LOCALAPPDATA%\\sovereign-agent\\demos\\ch3\\

Override with SOVEREIGN_AGENT_DATA_DIR=<path> if you'd rather pin it
somewhere specific.
"""

from __future__ import annotations

from sovereign_agent._internal.atomic import atomic_write_json, compute_sha256
from sovereign_agent._internal.paths import demo_sessions_dir
from sovereign_agent.ipc.protocol import read_and_consume, write_ipc_message
from sovereign_agent.session.directory import create_session
from sovereign_agent.session.state import now_utc
from sovereign_agent.tickets.manifest import Manifest, OutputRecord
from sovereign_agent.tickets.ticket import create_ticket


def main() -> None:
    sessions_root = demo_sessions_dir("ch3")
    print(f"Session artifacts will go in: {sessions_root}")
    print()
    session = create_session(scenario="ch3-demo", sessions_dir=sessions_root)

    print("[1/4] Writing three IPC messages atomically...")
    for i in range(3):
        write_ipc_message(session.ipc_output_dir, {"i": i})
    # Force age the files so read_and_consume accepts them.
    import os
    import time

    for p in session.ipc_output_dir.iterdir():
        if p.is_file():
            past = time.time() - 1
            os.utime(p, (past, past))
    consumed = read_and_consume(session.ipc_output_dir, max_age_ms=0)
    print(f"      Consumed {len(consumed)} messages. Contents: {[p for _, p in consumed]}")

    print("\n[2/4] Happy-path ticket: pending -> running -> success")
    t = create_ticket(session, operation="demo.happy")
    t.start()
    raw_path = t.directory / "raw_output.json"
    atomic_write_json(raw_path, {"result": "ok"})
    manifest = Manifest(
        ticket_id=t.ticket_id,
        operation="demo.happy",
        started_at=now_utc(),
        completed_at=now_utc(),
        duration_ms=0,
        outputs=[
            OutputRecord(
                path=raw_path,
                sha256=compute_sha256(raw_path),
                size_bytes=raw_path.stat().st_size,
            )
        ],
    )
    t.succeed(manifest, "Produced one result, size 15 bytes.")
    print(f"      State: {t.read_state().value}")
    print(f"      Summary: {t.read_summary().strip()}")
    print(f"      Manifest verifies? {manifest.verify()}")

    print("\n[3/4] Unhappy path: ticket REFUSES to succeed with a bad manifest")
    t2 = create_ticket(session, operation="demo.bad_manifest")
    t2.start()
    bad_path = t2.directory / "raw_output.json"
    atomic_write_json(bad_path, {"x": 1})
    bad_manifest = Manifest(
        ticket_id=t2.ticket_id,
        operation="demo.bad_manifest",
        started_at=now_utc(),
        completed_at=now_utc(),
        duration_ms=0,
        outputs=[
            OutputRecord(
                path=bad_path,
                sha256="f" * 64,  # intentionally wrong
                size_bytes=bad_path.stat().st_size,
            )
        ],
    )
    try:
        t2.succeed(bad_manifest, "Should fail to land.")
    except Exception as exc:
        print(f"      REJECTED as expected: {type(exc).__name__}: {exc}")
    print(f"      Ticket state remains: {t2.read_state().value}")

    print("\n[4/4] Tampering detection: modify the output file, then verify()")
    raw_path.write_text('{"tampered": true}')
    print(f"      Manifest verify() now: {manifest.verify()}  (False = tamper detected)")

    print("\nDone. Inspect the session with:")
    print(f'      ls -R "{session.directory}"')
    print(f"      cat {session.trace_path}")


if __name__ == "__main__":
    main()
