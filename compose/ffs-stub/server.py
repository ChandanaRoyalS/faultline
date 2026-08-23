"""Minimal stand-in for the OTel demo's feature-flag service (ADR-0006).

The real service is Elixir/Erlang and segfaults under x86 emulation on Apple
Silicon; its native build is blocked by upstream bit-rot. Disabling it caused a
cascading failure to the storefront, because callers treat a failed flag lookup
as an error span.

This implements the same gRPC contract and answers every lookup with
"disabled" - which is what the real service returns in normal demo operation,
since flags exist to inject faults on demand.

FAULTLINE_ENABLED_FLAGS turns that dial back on for named flags, so the demo's
own failure modes (productCatalogFailure and friends, read by the demo services
themselves) become injectable as configuration rather than as a rebuilt image.
It is read once at startup, because that is when compose applies an environment
override, and it defaults to empty: an unconfigured stub behaves exactly as it
did before, with every flag off.
"""

import os
from concurrent import futures

import demo_pb2
import demo_pb2_grpc
import grpc


def enabled_flags():
    """Flag names FAULTLINE_ENABLED_FLAGS switches on. Empty unless it is set."""
    raw = os.getenv("FAULTLINE_ENABLED_FLAGS", "")
    return frozenset(name.strip() for name in raw.split(",") if name.strip())


class FeatureFlagService(demo_pb2_grpc.FeatureFlagServiceServicer):
    """Every flag is off unless FAULTLINE_ENABLED_FLAGS names it. Mutations are ignored."""

    def __init__(self, enabled=frozenset()):
        self._enabled = enabled

    def GetFlag(self, request, context):
        enabled = request.name in self._enabled
        return demo_pb2.GetFlagResponse(
            flag=demo_pb2.Flag(
                name=request.name,
                description=(
                    "stub: enabled by FAULTLINE_ENABLED_FLAGS"
                    if enabled
                    else "stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them"
                ),
                enabled=enabled,
            )
        )

    def CreateFlag(self, request, context):
        return demo_pb2.CreateFlagResponse()

    def UpdateFlag(self, request, context):
        return demo_pb2.UpdateFlagResponse()

    def ListFlags(self, request, context):
        return demo_pb2.ListFlagsResponse()

    def DeleteFlag(self, request, context):
        return demo_pb2.DeleteFlagResponse()


def serve() -> None:
    port = os.getenv("FEATURE_FLAG_GRPC_SERVICE_PORT", "50053")
    enabled = enabled_flags()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    demo_pb2_grpc.add_FeatureFlagServiceServicer_to_server(FeatureFlagService(enabled), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    # Printed rather than assumed: an operator reading the logs mid-incident needs
    # to see which flags this instance is answering "on" to.
    print(
        f"ffs-stub listening on :{port}; enabled flags: {', '.join(sorted(enabled)) or 'none'}",
        flush=True,
    )
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
