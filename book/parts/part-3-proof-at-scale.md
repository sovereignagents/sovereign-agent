# Part 3: Proof at scale

A mechanism that works for one product can still hide identity, concurrency, and
attribution bugs. This part adds the second instance that forces those assumptions into
the open.

Chapters 8 through 12 replace the single-product fixture with a catalog, make stock and
reorder policy independent per SKU, trace one signal to one governed need, and make retry
converge on one canonical effect. The final chapter assembles release evidence and then
demonstrates the limit of that evidence: internal consistency is not the same claim as
truth in the world.

By the end, the reader has a pilot-start receipt and a ladder for moving from deterministic
local checks toward credentialed evaluation, human review, canary rollout, and wider
release. Each rung proves something new; none inherits the claim of the rung above it.

Continue to [Chapter 8: The Store becomes a catalog](../ch08_the_store_becomes_a_catalog/README.md).
