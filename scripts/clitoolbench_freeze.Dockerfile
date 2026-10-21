# The only place scripts/clitoolbench_freeze.py runs: it git-clones, pip-installs and runs each
# CLI-Tool-Bench oracle, so that happens in this throwaway container, never on the host. Built
# and started by scripts/clitoolbench_freeze.sh, which passes the digest of the base image the
# owner pulled (python:3.12, the grading host's minor version) and records it.
#
# The container runs as the owner's uid (`docker run --user`), not as this image's user, so the
# folders it writes are mode 1777 (like /tmp). /repo is a link into the /clitb-work volume:
# an oracle cloned there in phase A (network) is still there in phase B (no network). An adapter
# that needs any other writable path is skipped with that reason.
ARG BASE_DIGEST
FROM python:3.12-bookworm@${BASE_DIGEST}
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin clitb \
    && mkdir -p /test_data /clitb-work/repo \
    && ln -s /clitb-work/repo /repo \
    && chown -R 10001:10001 /test_data /clitb-work \
    && chmod 1777 /test_data /clitb-work /clitb-work/repo
ENV CLITOOLBENCH_IN_CONTAINER=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/clitb-work
COPY clitoolbench_freeze.py /freeze/clitoolbench_freeze.py
USER 10001:10001
ENTRYPOINT ["python", "-I", "/freeze/clitoolbench_freeze.py"]
