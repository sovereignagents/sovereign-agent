**Created:** 2026-09-07 · **Last-updated:** 2026-09-07 · **Status:** FINDING

# Route distinguishes a local result from an outbound message

Actual Linux deployment of releasef05a3a6 preserved the two purchases, inventory
and2600pence, then printed five uncertain outbound deliveries. A read-only grouped
query found all five records had channel local. account_recovery.py deliberately
marks pending/sending delivery records UNKNOWN after restore, including local
results. Their history remains valid; the report's interpretation was wrong.

Both assistant_service.health and operating_report now restrict outbound delivery
uncertainty to the implemented telegram route. No history is rewritten. A new
regression first failed on the reported false warning, then passed after the
query correction. Positive Telegram UNKNOWN remains counted by both interfaces.
Ten focused tests pass. Updated Chapter15/16 executable definitions match the code;
Chapter16 explains the live-host finding. Both fresh draft-shape scores remain100.

Candidate source executed on the same Linux host now reports0 uncertain outbound
deliveries while preserving all5 local UNKNOWN markers. Its separate warning about
incomplete model usage remains correct and visible. linux-operating-report-route-v1
retains the before report, actual frozen release switch, corrected candidate,
source hashes and red/green evidence. The installed services remainf05a3a6 until
this repair passes the repository gate and is deployed as a new immutable release.

The complete publication overhaul remains active. No chapter is markedREADY.
