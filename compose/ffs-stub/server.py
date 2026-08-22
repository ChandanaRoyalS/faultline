"""Minimal stand-in for the OTel demo's feature-flag service (ADR-0006).

The real service is Elixir/Erlang and segfaults under x86 emulation on Apple
Silicon; its native build is blocked by upstream bit-rot. Disabling it caused a
cascading failure to the storefront, because callers treat a failed flag lookup
as an error span.

This implements the same gRPC contract and answers every lookup with
"disabled" - which is what the real service returns in normal demo operation,
since flags exist to inject faults on demand. Faultline injects its own faults
(T1.4), so nothing is lost.
"""

import os
from concurrent import futures

import demo_pb2
import demo_pb2_grpc
import grpc


class FeatureFlagService(demo_pb2_grpc.FeatureFlagServiceServicer):
    """Every flag is off. Mutations are accepted and ignored."""

    def GetFlag(self, request, context):
        return demo_pb2.GetFlagResponse(
            flag=demo_pb2.Flag(
                name=request.name,
                description="stub: flags are always disabled (ADR-0006)",
                enabled=False,
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
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    demo_pb2_grpc.add_FeatureFlagServiceServicer_to_server(FeatureFlagService(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    print(f"ffs-stub listening on :{port}", flush=True)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
