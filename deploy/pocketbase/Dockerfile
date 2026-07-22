FROM alpine:3.21
ARG PB_VERSION=0.28.4
# TARGETARCH (amd64/arm64) is set by BuildKit to the platform being built for.
ARG TARGETARCH
RUN apk add --no-cache ca-certificates unzip wget \
    && wget -q "https://github.com/pocketbase/pocketbase/releases/download/v${PB_VERSION}/pocketbase_${PB_VERSION}_linux_${TARGETARCH}.zip" -O /tmp/pb.zip \
    && unzip /tmp/pb.zip -d /pb/ \
    && rm /tmp/pb.zip
COPY pb_migrations /pb/pb_migrations
COPY pocketbase/entrypoint.sh /pb/entrypoint.sh
RUN chmod +x /pb/entrypoint.sh
EXPOSE 8090
CMD ["/pb/entrypoint.sh"]
