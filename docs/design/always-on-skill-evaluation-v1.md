**Created:** 2026-09-07 · **Last-updated:** 2026-09-07 · **Status:** ACTIVE

# Evaluate the selected skill configuration

The full overhaul remains active. This checkpoint aligns evaluation with active guidance and prevents a candidate from being activated against a configuration that changed while its model calls were running.

## Grounded defect and correction

At commit `76591c6`, `assistant_cli.handle` called `evaluate` without active skills, while `assistant_context.context` loaded active skill guidance for normal work. `change_skill` evaluated a candidate alone, omitting other active procedures. Its later `activate_skill` call consumed already-computed booleans without binding them to the earlier active configuration. Consequently a passing evaluation could concern different guidance from the eventual running configuration.

`skill_snapshot` now reads active versions, content and provenance in one query and returns their fingerprint with the parsed guidance. CLI evaluation uses this snapshot over isolated scenario fixtures. Candidate evaluation replaces its own named version while preserving other active skills. Reports identify all selected skill versions and the baseline fingerprint. They explicitly exclude live session preferences, conversation history, and optional tools; this is a stock-scenario evaluation, not a replay of every production context.

Activation compares the expected fingerprint inside its write transaction. If another activation changed the configuration during evaluation, it refuses to apply the candidate. The improvement path returns `STALE`, retains the passing scenario report, and records the refused activation outcome. Passing named cases and activating the change are separate facts. The direct activation API also rejects an evaluator that mutates the candidate it claimed to test.

## Proof

Five new behavioral tests cover candidate replacement with another active procedure retained, CLI-to-context data flow without copying a live private preference, candidate mutation, an intervening activation through a second database connection, and a full improvement run that passes scenarios but must report `STALE`.

The live CLI evaluated the active opening-check skill across eight cases twice. All sixteen passed the named checks: 52 model calls, 36 tool calls, 1496 output tokens, about 66.6 seconds. The complete report is `docs/evidence/always-on/evaluation-active-skills-v1.json`, SHA256 `479356b4095c193328d2afad3379baf521909df4ee03e7423362ae75fe24ba39`. This does not certify arbitrary natural-language faithfulness or provider billing correctness.

## Continue

Run the full gate and keep PR88 draft. Twelve manuscript chapters, persistent stock conditions, receiving and restored-account reconciliation, bounded delegation, Linux operation and integrated acceptance, publisher material, exact-source site migration and rendered review remain required. The separate optional Zeocore MCP example proves a connection without adding Zeocore to the teaching runtime's dependencies.
