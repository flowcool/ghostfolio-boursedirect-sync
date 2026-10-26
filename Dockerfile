# Selectively adapted from the approved ibkr package image.
FROM python:3.15.1-slim@sha256:533b0b2f9b5d46fd097091cf826f27902f1d6c3bca714b6dc74551356aa97a51

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils tzdata \
    && rm -rf /var/lib/apt/lists/*

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
