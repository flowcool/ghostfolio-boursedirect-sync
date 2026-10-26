# Selectively adapted from the approved ibkr package image.
FROM python:3.15.1-slim@sha256:533b0b2f9b5d46fd097091cf826f27902f1d6c3bca714b6dc74551356aa97a51

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils tzdata \
    && rm -rf /var/lib/apt/lists/*

# Install supercronic for cron support.
# SHA256 of each release binary, verified against the official release asset.
# Renovate tracks SUPERCRONIC_VERSION. Update both sums with each version;
# stale sums fail the build. Reuses DEGIRO renovate.json:100 regex management.
ARG SUPERCRONIC_VERSION=v0.2.49
ARG SUPERCRONIC_SHA256SUM_amd64=a53ae236602c7338aba3fbaff40bda6300eae3b9fedb8261eb06cfe3724430c1
ARG SUPERCRONIC_SHA256SUM_arm64=02aa0cb229ba09050cba6638059dadb9eedc2276632ea43d6a57a2f8c1629dd5
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    curl --proto '=https' --proto-redir '=https' --tlsv1.2 -fsSLO "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-${TARGETARCH}" && \
    case "${TARGETARCH}" in \
      amd64) EXPECTED="${SUPERCRONIC_SHA256SUM_amd64}" ;; \
      arm64) EXPECTED="${SUPERCRONIC_SHA256SUM_arm64}" ;; \
      *) echo "unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac && \
    echo "${EXPECTED}  supercronic-linux-${TARGETARCH}" | sha256sum -c - && \
    chmod +x "supercronic-linux-${TARGETARCH}" && \
    mv "supercronic-linux-${TARGETARCH}" /usr/local/bin/supercronic && \
    apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
COPY pyproject.toml /build/pyproject.toml
COPY ghostfolio_boursedirect_sync/*.py /build/ghostfolio_boursedirect_sync/
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --no-deps /build \
    && rm -rf /build \
    && pip uninstall -y pip

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}
COPY entrypoint.sh .
RUN chmod 0555 /app /app/entrypoint.sh \
    && chmod 0444 /app/requirements.txt \
    && addgroup --gid 10001 appuser \
    && adduser --uid 10001 --no-create-home --gecos "" --ingroup appuser \
        --disabled-password --shell /usr/sbin/nologin appuser
USER appuser
ENTRYPOINT ["/app/entrypoint.sh"]
