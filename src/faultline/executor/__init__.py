"""The action plane (T6.2): the one part of this system that can change the world.

Everything else here reads. The investigation runtime holds a tool surface with no write path
(ADR-0019 §4, ADR-0028 §3), and it stays that way: this package is a **separate process** with its
own credential — in this world, the Docker socket and the compose files — reachable from agent
context by no import (`tests/test_executor_boundary.py` holds it by AST). The agent emits a
proposal as data; a human approves it; this executes it, once, with a token that names exactly
that action against exactly that target, and writes down what it did in a table nothing can edit.

`evals/runs/PREREGISTRATION-T6.2.md` fixed the shape before a line of this existed. ADR-0038
records the design and what building it changed.
"""
