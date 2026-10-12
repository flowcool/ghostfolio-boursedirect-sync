FROM node:22-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392 AS cli
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl unzip && rm -rf /var/lib/apt/lists/*
RUN set -eu; \
    case "$TARGETARCH" in \
      amd64) asset=bw-linux-2026.9.1.zip; hash=84289eaf59d691f04242605112f21b00e8dba65acdedbc60dde001a2860f2097 ;; \
      arm64) asset=bw-linux-arm64-2026.9.1.zip; hash=c451c773378a6f1f041ea26568a897b285a8656bee16a16e4914ce9e40fb7c79 ;; \
      *) exit 1 ;; \
    esac; \
    curl --fail --silent --show-error --location --connect-timeout 20 --max-time 180 --retry 2 \
      --proto '=https' --proto-redir '=https' \
      "https://github.com/bitwarden/clients/releases/download/cli-v2026.9.1/$asset" -o /opt/bw.zip; \
    echo "$hash  /opt/bw.zip" | sha256sum -c -; \
    unzip /opt/bw.zip -d /opt/bw; chmod 755 /opt/bw/bw; \
    test "$(/opt/bw/bw --version)" = 2026.9.1

FROM node:22-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && apt-get install -y --no-install-recommends python3 python3-venv tzdata unzip curl \
       libnss3 libatk-bridge2.0-0 libgtk-3-0 libgbm1 libasound2 libxss1 libx11-xcb1 libxshmfence1 fonts-liberation \
    && apt-get install -y --only-upgrade perl-base && rm -rf /var/lib/apt/lists/*
ARG TARGETARCH
RUN if [ "$TARGETARCH" = amd64 ]; then \
      curl --fail --silent --show-error --location --connect-timeout 20 --max-time 180 \
        --proto '=https' --proto-redir '=https' \
        https://storage.googleapis.com/chrome-for-testing-public/155.0.8059.39/linux64/chrome-headless-shell-linux64.zip -o /opt/chrome.zip; \
      echo '39dcb8c46550632a3d911850ab3b8af840b4e3f6d8622faa2018eb8756278786  /opt/chrome.zip' | sha256sum -c -; \
      unzip -q /opt/chrome.zip -d /opt && rm /opt/chrome.zip; \
    fi
RUN ln -s /usr/local/bin/node /usr/bin/node
WORKDIR /opt/app
COPY requirements.txt ./
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt
COPY collector/package.json collector/package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts --no-audit --no-fund
RUN rm -rf /usr/local/lib/node_modules/npm /opt/yarn-* \
    && rm -f /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/yarn /usr/local/bin/yarnpkg
COPY --from=cli /opt/bw/bw /usr/local/bin/bw
COPY collector/*.mjs ./
COPY collector/internal/*.mjs ./internal/
COPY collector/lab/source-browser-pipe.mjs collector/lab/browser-sandbox-proof.mjs ./lab/
COPY collector/source-pin.json ./source-pin.json
COPY collector/vault-egress.py ./collector/
COPY boursedirect_to_ghostfolio.py ./
COPY scripts/community_connect.py scripts/source_qualification.py scripts/source_connection.py scripts/source_vault_inspection.py scripts/native_cdp_allocation.py ./scripts/
RUN node --input-type=module -e 'import fs from "node:fs"; import {createHash} from "node:crypto"; fs.writeFileSync("cli-pin.json", JSON.stringify({path:"/usr/local/bin/bw",sha256:createHash("sha256").update(fs.readFileSync("/usr/local/bin/bw")).digest("hex"),version:"2026.9.1",defaultsVerified:true}));' \
    && mkdir -m 700 /data /state /home/fixture && chown node:node /data /state /home/fixture
USER node
ENV HOME=/state
ENTRYPOINT ["/opt/venv/bin/python", "/opt/app/scripts/community_connect.py"]
CMD ["inspect"]
