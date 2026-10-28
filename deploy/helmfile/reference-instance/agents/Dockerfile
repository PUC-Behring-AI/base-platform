# The reference instance's agents image: base-agents with one job flow, so the
# system test (scripts/k8s-test.sh) can start a job through the interface and
# poll it to the end. A real instance builds its own the same way (ADAPTATION
# §4): FROM the base image, the instance at /instance, its modules installed.
ARG BASE_IMAGE=localhost:5001/base-agents:local
FROM ${BASE_IMAGE}
COPY module /opt/reference-module
RUN pip install --no-cache-dir /opt/reference-module
COPY instance /instance
