FROM ubuntu:24.04

# Install HTTP(S) tools
RUN --mount=type=cache,target=/var/lib/apt/,sharing=locked \
    --mount=type=cache,target=/var/cache/apt/,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl

RUN --mount=type=cache,target=/var/lib/apt/,sharing=locked \
    --mount=type=cache,target=/var/cache/apt/,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    # For development
    sudo git ssh netcat-openbsd \
    # For run
    gnuradio soapysdr-module-all python3-soapysdr gr-osmosdr

USER ubuntu

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH=/home/ubuntu/.local/bin:$PATH

WORKDIR /workspace/
