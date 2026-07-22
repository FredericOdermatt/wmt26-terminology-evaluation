FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /usr/local/bin/uv
ENV UV_NO_CACHE=1
WORKDIR /app

# The lock pins the CUDA torch build; the service is CPU-only. The GPU stack is
# excluded from every layer (skipping it at sync, not uninstalling later, keeps
# it out of the image) and the cpu torch wheel is installed instead. Runtime
# must use --no-sync, or uv would restore the locked CUDA build.
ENV SKIP_GPU_STACK="--no-install-package torch --no-install-package triton \
    --no-install-package nvidia-cublas --no-install-package nvidia-cuda-cupti \
    --no-install-package nvidia-cuda-nvrtc --no-install-package nvidia-cuda-runtime \
    --no-install-package nvidia-cudnn-cu13 --no-install-package nvidia-cufft \
    --no-install-package nvidia-cufile --no-install-package nvidia-curand \
    --no-install-package nvidia-cusolver --no-install-package nvidia-cusparse \
    --no-install-package nvidia-cusparselt-cu13 --no-install-package nvidia-nccl-cu13 \
    --no-install-package nvidia-nvjitlink --no-install-package nvidia-nvshmem-cu13 \
    --no-install-package nvidia-nvtx"

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev $SKIP_GPU_STACK
COPY src ./src
RUN uv sync --frozen --no-dev $SKIP_GPU_STACK \
    && uv pip install "torch==2.13.0" --index-url https://download.pytorch.org/whl/cpu
RUN uv run --no-sync python -c "import stanza; stanza.download('pl'); stanza.download('eu')"
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "wmt26_terminology.server.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
