# T1.1/T1.3 - native-arm64 stand-in for the demo's feature-flag service.
# See ADR-0006. gRPC code is generated from the demo's own proto at build time,
# so the contract cannot drift from what callers expect.
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir grpcio==1.62.2 grpcio-tools==1.62.2
COPY demo.proto .
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. demo.proto
COPY server.py .
CMD ["python", "server.py"]
