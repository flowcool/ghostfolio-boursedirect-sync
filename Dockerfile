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
    && apt-get install -y --only-upgrade perl-base && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/app
COPY collector/package.json collector/package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts --no-audit --no-fund
RUN rm -rf /usr/local/lib/node_modules/npm /opt/yarn-* \
    && rm -f /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/yarn /usr/local/bin/yarnpkg
COPY --from=cli /opt/bw/bw /usr/local/bin/bw
COPY collector/*.mjs ./
COPY collector/internal/*.mjs ./internal/
RUN node --input-type=module -e 'import fs from "node:fs"; import {createHash} from "node:crypto"; fs.writeFileSync("cli-pin.json", JSON.stringify({path:"/usr/local/bin/bw",sha256:createHash("sha256").update(fs.readFileSync("/usr/local/bin/bw")).digest("hex"),version:"2026.9.1",defaultsVerified:true}));' \
    && mkdir -m 700 /data /state && chown node:node /data /state
USER node
ENV HOME=/data
ENTRYPOINT ["node", "/opt/app/native-vault-command.mjs"]
CMD ["inspect"]
