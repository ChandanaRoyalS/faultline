# Voided draws

**2026-09-05.** One draw was opened (incident `a982fb83`) and closed unexamined before any evidence was looked at, when the session changed direction to Q25. No attempt was recorded.

> **Correction, minutes later.** The line first written here said the draw was *"reverted without revealing the scenario, pool unchanged at five"*. **Both halves were false.** The revert shelled out to `faultline-inject stop` without capturing stdout, so the injector printed `reverted cart-bad-image-tag` to the terminal, and the responder was told the name of a fault she had not investigated.

**`cart-bad-image-tag` is removed from the draw pool.** It cannot be timed as a recognition task by someone who has been handed its name. The pool is four, the reference will be **n=4** against T4.7's five, and the manual side now covers three fault classes where the pipeline's covers four - the lost one being `bad_deploy`, the class this catalog is thinnest on.

**Recorded rather than repaired.** There is no repair: the knowledge cannot be withdrawn, and re-drawing that scenario later would produce a timing of a confirmation labelled as a recognition. Narrowing a pool after the fact is the thing `blind_cli.POOL`'s docstring forbids, so the narrowing is written down in three places with its cause attached.
