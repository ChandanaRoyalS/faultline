"""The bad_deploy fault variant of the feature-flag stub (T1.4).

This is the "deploy" in bad_deploy: same image, same contract, one regression.
GetFlag - the only method the demo calls on a hot path - fails with
UNAVAILABLE, which is what a half-broken dependency looks like from the
outside. Callers record the failed lookup as an error span, so the failure
cascades recommendationservice -> frontend. ADR-0006 measured that exact
cascade when the real service was dead, which is why it is worth reproducing
deliberately: it is a realistic, already-observed shape of failure.

The remaining methods keep working, so the service still starts, still passes a
naive health check, and still serves gRPC. A fault that announces itself by
refusing to boot teaches the investigator nothing.
"""

import os
from concurrent import futures

import demo_pb2
import demo_pb2_grpc
import grpc


class FeatureFlagService(demo_pb2_grpc.FeatureFlagServiceServicer):
    """Flag lookups fail; everything else is unchanged from the healthy stub."""

    def GetFlag(self, request, context):
        context.abort(grpc.StatusCode.UNAVAILABLE, "flag store unreachable")

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
    print(f"ffs-stub (broken build) listening on :{port}", flush=True)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
