# syntax=docker/dockerfile:1
FROM python:3.12-slim AS build

WORKDIR /build
COPY pyproject.toml README.md uv.lock ./
COPY src ./src
RUN python -m pip install --no-cache-dir build && python -m build --wheel --outdir /dist

FROM python:3.12-slim

RUN useradd --create-home --uid 10001 exporter
COPY --from=build /dist/ /tmp/dist/
RUN python -m pip install --no-cache-dir /tmp/dist/*.whl && rm -rf /tmp/dist

USER exporter
EXPOSE 9476
ENTRYPOINT ["hermes-lcm-prometheus-exporter"]
