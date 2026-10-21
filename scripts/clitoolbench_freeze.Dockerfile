# The only place scripts/clitoolbench_freeze.py runs: it git-clones and pip-installs each
# CLI-Tool-Bench oracle and runs it, so that happens in this throwaway container, never on the host.
# Built and started by scripts/clitoolbench_freeze.sh. python:3.12 (Debian, has git): the gate
# grades products on 3.12 too. kn: tag not digest-pinned; pin the digest the owner pulls if a
# re-freeze must be byte-identical.
FROM python:3.12-bookworm
ENV CLITOOLBENCH_IN_CONTAINER=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
COPY clitoolbench_freeze.py /freeze/clitoolbench_freeze.py
ENTRYPOINT ["python", "-I", "/freeze/clitoolbench_freeze.py"]
