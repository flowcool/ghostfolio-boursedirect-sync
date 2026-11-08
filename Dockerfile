# Selectively adapted from the approved ibkr package image.
FROM python:3.15.2-slim@sha256:8c13a3f37a6a5b71498228e902c4b9f51c1f7900d49fabf71f9a650c6120e0d0

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends apt libapt-pkg7.0 zlib1g poppler-utils tzdata \
    && rm -rf /var/lib/apt/lists/*

# Install supercronic for cron support.
# SHA256 of each release binary, verified against the official release asset.
# Renovate tracks SUPERCRONIC_VERSION. Update both sums with each version;
# stale sums fail the build. Reuses DEGIRO renovate.json:100 regex management.
ARG SUPERCRONIC_VERSION=v0.2.51
ARG SUPERCRONIC_SHA256SUM_amd64=cc232108374e8e2b537045f2d5eaa1229f619db314c3ba6a14d38b35dc0aa123
ARG SUPERCRONIC_SHA256SUM_arm64=4ae22576a78223d8ccdf5f3b3660a5cbb5288416bf0ca96afc4a36d195932b94
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
ARG APP_REVISION=unknown
ENV APP_VERSION=${APP_VERSION} APP_REVISION=${APP_REVISION}
COPY entrypoint.sh .
RUN chmod 0555 /app /app/entrypoint.sh \
    && chmod 0444 /app/requirements.txt \
    && addgroup --gid 10001 appuser \
    && adduser --uid 10001 --no-create-home --gecos "" --ingroup appuser \
        --disabled-password --shell /usr/sbin/nologin appuser
USER appuser
ENTRYPOINT ["/app/entrypoint.sh"]
