# Rulings

Binding decisions for the 1.x line. A ruling the code contradicts is worse
than no ruling, so each records how to check it against the repository.
`scripts/verify_curriculum.py` fails if a ruling file is missing from this
list, so the list cannot silently drift behind the directory.

- [Ruling: Sovereign Agent 1.x educational reset](2026-08-25-educational-reset.md)
- [Ruling amendment: `main` is the 1.x educational integration line](2026-08-25-main-is-the-1x-line.md)
- [Ruling amendment: effects are required where a SOW declares them](2026-08-26-amendment-conditional-effects.md)
- [Deferral: multi-process fencing is Unit 8, not Unit 4](2026-08-26-deferral-unit4-fencing.md)
- [Deferral: credentialed provider smokes are Unit 12](2026-08-26-deferral-unit6-smokes.md)
- [Ruling: one process per actor in 1.x; lease fencing is Unit 8](2026-08-26-one-process-per-actor.md)
- [Ruling: an outcome is a standing condition; a SOW is a unit of work](2026-08-26-outcomes-are-conditions-sows-are-work.md)
- [Ruling: the persistence boundary, refined](2026-08-26-persistence-boundary-refinement.md)
- [Ruling: SQLite writers are inside the trust boundary](2026-08-26-sqlite-writers-are-inside-the-boundary.md)
- [Ruling: the book is published by `zeo-site`; this repository builds no site](2026-08-27-book-publication-destination.md) — **SUPERSEDED**, see below
- [Ruling: the book's rendered home is a section of `profrod-site`; this repository still builds no site](2026-09-03-book-publication-destination-is-profrod-site.md)
- [Ruling: Unit 7 is workspace lifecycle; Pulse stays out until Unit 9](2026-08-27-unit7-is-workspaces-not-pulse.md)
- [Ruling: Unit 9 Pulse is a separate mechanism from the supervisor; attribution is structured and durable](2026-08-29-unit9-pulse-is-separate-from-supervisor.md)
- [Ruling: attributed governance communication protocol](2026-08-29-attributed-governance-communication-protocol.md)
- [Ruling: Unit 11 scope — pilot start marker, multi-SKU catalog, Chapters 8-12](2026-08-30-unit11-scope.md)
- [Ruling: Unit 11 closes on local, learner-controlled SQLite — the real-deployment pilot-start gate is withdrawn](2026-08-30-unit11-local-closure-supersedes-real-deployment-gate.md)
- [Ruling: Unit 12 scope — release evaluation, proof pack, Andrea protocol, provider truthfulness, release sequence](2026-08-31-unit12-scope.md)
- [Ruling: build the complete always-on teaching agent](2026-09-07-always-on-teaching-scope.md)
- [Ruling: count the complete always-on teaching distribution](2026-09-07-always-on-source-budget.md)
