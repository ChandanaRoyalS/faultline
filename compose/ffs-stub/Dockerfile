# T1.1/T1.3 - native-arm64 stand-in for the demo's feature-flag service.
# See ADR-0006. gRPC code is generated from the demo's own proto at build time,
# so the contract cannot drift from what callers expect.
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir grpcio==1.62.2 grpcio-tools==1.62.2
COPY demo.proto .
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. demo.proto
# T1.4 builds a faulty variant of this image (:broken) by pointing SERVER at
# server_broken.py. One Dockerfile and one generated stub keep the healthy and
# faulty builds identical in everything except the injected regression - so a
# bad_deploy scenario blames the deploy, not an incidental image difference.
ARG SERVER=server.py
COPY ${SERVER} ./server.py
CMD ["python", "server.py"]
