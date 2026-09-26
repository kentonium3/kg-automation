# The runner: the ONLY process that executes arm code, inside the boundary
# research.md D-8 describes. It copies nothing from the repo; the export is
# bind-mounted read-only at /work by `substrate run`. No torch, no network
# beyond the compose network, no API keys.
# Pinned by digest (resolved 2026-09-25 from the python:3.12-slim tag); a rebuild after
# teardown must produce the same environment. Recorded in setup.json as runner_base.
FROM python:3.12-slim@sha256:44ff437bba879d4941b710a369a8f19266aea34b29002807f0c487fabc9eec9b

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-arms849.txt /tmp/requirements-arms849.txt
RUN pip install --no-cache-dir -r /tmp/requirements-arms849.txt \
    && pip install --no-cache-dir --no-deps transformers tokenizers huggingface-hub \
    && pip install --no-cache-dir regex filelock pyyaml requests tqdm packaging numpy safetensors jinja2 \
    && python -c "import importlib.util,sys; sys.exit(1 if importlib.util.find_spec('torch') else 0)"

ENV HF_HUB_OFFLINE=1 \
    ARMS849_CORPUS=/corpus \
    ARMS849_CACHE=/cache \
    PYTHONUNBUFFERED=1

WORKDIR /work
ENTRYPOINT ["python3", "-m"]
CMD ["scripts.research.run_849_harness", "--help"]
