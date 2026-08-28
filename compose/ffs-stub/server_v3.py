"""The crash-loop fault variant of the feature-flag stub (T1.5).

Three ways a deploy can be bad, and this is the third. `server_broken.py` starts
and fails on the hot path; an unresolvable image tag never starts at all. This
one starts, serves correctly, and then dies - over and over, because the world
gives the flag service `restart: always`.

The signature is therefore neither steady errors nor a flat outage but a
sawtooth: the container's restart count climbing, healthy stretches separated by
bursts of UNAVAILABLE at the callers, and a fresh "listening" line in the logs
every time. An investigator who only looks at an error-rate graph sees
intermittent failure with no obvious cause; the restart count is what names it.

FAULTLINE_CRASH_AFTER_SECONDS must stay above 10. Docker resets a container's
restart backoff only once it has stayed up for 10 seconds; crash faster than
that and the backoff doubles away to a minute between attempts, which stops
looking like a crash loop and starts looking like a service that is simply down.
"""

import os
import sys
import threading
from concurrent import futures

import demo_pb2
import demo_pb2_grpc
import grpc

CRASH_AFTER_SECONDS = float(os.getenv("FAULTLINE_CRASH_AFTER_SECONDS", "20"))


class FeatureFlagService(demo_pb2_grpc.FeatureFlagServiceServicer):
    """Identical to the healthy stub. Nothing here is what is wrong."""

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


def crash() -> None:
    """Die the way a process with a real bug dies: abruptly, and non-zero.

    os._exit rather than sys.exit because this runs on a timer thread, where
    SystemExit would unwind that thread alone and leave the gRPC server serving.
    """
    print(
        "ffs-stub (crash build): flag store connection lost, aborting",
        file=sys.stderr,
        flush=True,
    )
    os._exit(1)


def serve() -> None:
    port = os.getenv("FEATURE_FLAG_GRPC_SERVICE_PORT", "50053")
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    demo_pb2_grpc.add_FeatureFlagServiceServicer_to_server(FeatureFlagService(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    print(
        f"ffs-stub (crash build) listening on :{port}; exiting in {CRASH_AFTER_SECONDS:.0f}s",
        flush=True,
    )
    threading.Timer(CRASH_AFTER_SECONDS, crash).start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
