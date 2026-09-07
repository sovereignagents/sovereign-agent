# Retain a result another builder can inspect

**Created:** 2026-09-07 · **Last-updated:** 2026-09-07 · **Status:** DRAFT

Record the source commit, frozen environment, command, exit status, expected observations and actual artifacts. A screenshot of green text omits the failure that might have appeared earlier in the log. Retain the complete log locally and a content hash in a shareable receipt; review it for secrets before publishing.

The default repository gate excludes tests marked `live`. That is an explicit boundary, not a successful live result. Run the chapter's named live command only after providing the stated facility. An absent optional environment can produce a skip; a configured but broken integration must produce a failure. Keep both outcomes visible when comparing runs.

| Experiment | Required facility | Retain |
| --- | --- | --- |
| First live model call | Configured HTTP model endpoint | Model identity, request settings and observed response |
| Phone exchange | Dedicated Telegram bot and allowlisted operator | Redacted transport result, work identifier and handset observation |
| Linux service | User service manager and persistent state | Unit executable path, restart observation and completed work |
| Restricted code tool | Supported Linux container engine and pinned image | Image digest, resource settings and actual refusal/cleanup results |
| Final accelerated day | Frozen local Python checkout | Both databases, report and evidence JSON |

## When a result differs

First confirm the working directory, source commit and interpreter. Compare the command's prerequisites with the checkpoint you ran. An unavailable live dependency is different from a deterministic assertion failure. Do not substitute a fictional response or silently skip the failing branch.

For a model-dependent difference, retain the model identity and sampling settings, then inspect the actual tool requests. Repeated runs measure variation within those conditions. A second model acting as a judge is additional evidence, not an authority that can overwrite a supplier receipt or numeric business rule.

For a state-dependent difference, preserve the existing directory. Use a fresh directory to reproduce the fixture and compare them. Deleting a confusing database may make the next run green while destroying the only evidence of a duplicate effect. Backup and account recovery are separate operations described in [Chapter 15](../ch15_operation/README.md).

## What to send with a defect report

Include the edition and source commit, a minimal synthetic input, the exact command, the expected result and the actual result. Add a redacted log and the hashes of retained artifacts. Explain whether the failure occurs in a fixture, against a live model, on the Linux host or on the phone. Do not attach tokens, operator identifiers, private conversations or raw production databases.

The manuscript's mechanical score reports, construction checkpoints and executed host receipts live under `docs/evidence/always-on/` in the source repository. Their dates and pins identify their scope; a later source change needs a corresponding new check. Historical receipts remain evidence of the earlier version, not automatic certification of the current tree.
