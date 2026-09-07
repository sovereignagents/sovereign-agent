# Part 2: Bounded autonomy

Durable state is necessary, but it is not enough. Work must stay inside its assigned
boundary, authority must expire without allowing a stale writer to return, and recovery
must reconcile evidence rather than guess what a dead process accomplished.

Chapters 4 through 7 turn those constraints into mechanisms. You will qualify five
different isolation planes, fence late writers, recover a process killed between intent
and completion, and finally let a durable signal create governed work without a human
prompt. The sequence matters. Proactive execution arrives last because it amplifies every
boundary mistake that came before it.

The result is bounded autonomy: the organization may wake and act, while the host can
still show which authority admitted the action, which workspace contained it, and which
evidence survived a crash.

Continue to [Chapter 4: Work stays inside its boundary](../ch04_work_stays_inside_its_boundary/README.md).
