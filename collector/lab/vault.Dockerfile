# Disposable qualification image. Resolve latest Chrome for Testing outside
# the build, retain its download/hash, then inspect and use the exact image ID.
FROM debian:trixie-slim
RUN apt-get update && apt-get install -y --no-install-recommends nodejs unzip ca-certificates libnss3 libatk-bridge2.0-0 libgtk-3-0 libgbm1 libasound2 libxss1 libx11-xcb1 libxshmfence1 fonts-liberation && rm -rf /var/lib/apt/lists/*
ARG CHROME_SHA256
COPY headless.zip /opt/chrome.zip
RUN echo "${CHROME_SHA256}  /opt/chrome.zip" | sha256sum -c - && unzip -q /opt/chrome.zip -d /opt && rm /opt/chrome.zip && useradd -u 1000 -m -s /bin/sh fixture
USER 1000:1000
ENV HOME=/home/fixture
WORKDIR /home/fixture
ENTRYPOINT ["/usr/bin/node"]
