# syntax=docker/dockerfile:1
#
# 三段构建：前端 → 二进制 → 运行镜像。
# 运行镜像是 scratch，里面只有一个静态二进制和 CA 证书：
#   - 时区数据由 time/tzdata 编进二进制，不必装 tzdata
#   - SQLite 用纯 Go 实现（modernc.org/sqlite），不必开 CGO，也就不必带 libc
#   - 健康检查由二进制自己的 -healthcheck 承担，不必带 curl
#
# 多架构：不锁 --platform，由 buildx 的目标平台决定。
#   docker buildx build --platform linux/amd64,linux/arm64 -t <registry>/balance-alert --push .
# 国内环境可换源：
#   docker build --build-arg GOPROXY=https://goproxy.cn,direct \
#                --build-arg NPM_REGISTRY=https://registry.npmmirror.com .

# 版本要跟得上 go.mod 的 go 指令，否则 go mod download 会直接拒绝
ARG GO_IMAGE=golang:1.27-alpine
ARG NODE_IMAGE=node:22-alpine

# ---------- 前端 ----------
FROM ${NODE_IMAGE} AS ui
ARG NPM_REGISTRY=https://registry.npmjs.org
WORKDIR /ui
COPY ui/package.json ui/package-lock.json* ./
RUN npm config set registry "${NPM_REGISTRY}" && npm install --no-audit --no-fund
COPY ui/ ./
RUN npm run build

# ---------- 二进制 ----------
FROM --platform=$BUILDPLATFORM ${GO_IMAGE} AS build
ARG GOPROXY=https://proxy.golang.org,direct
ARG TARGETOS
ARG TARGETARCH
ENV GOPROXY=${GOPROXY} CGO_ENABLED=0
WORKDIR /src

# 依赖单独一层，改代码不用重新下载
COPY go.mod go.sum ./
RUN go mod download

COPY . .
# 前端产物覆盖掉仓库里提交的那份，保证镜像里是这次构建出来的
COPY --from=ui /ui/dist ./ui/dist
RUN GOOS=${TARGETOS} GOARCH=${TARGETARCH} \
    go build -trimpath -ldflags="-s -w" -o /out/balance-alert ./cmd/balance-alert

# 运行时要写的两个目录，在这里建好再整个拷过去：scratch 里没有 mkdir
RUN mkdir -p /out/data /out/logs

# ---------- 运行镜像 ----------
FROM scratch
ENV TZ=Asia/Shanghai
WORKDIR /app

# 访问各平台的 HTTPS 接口需要根证书
COPY --from=build /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
COPY --from=build /out/balance-alert /app/balance-alert
COPY --from=build --chown=65532:65532 /out/data /app/data
COPY --from=build --chown=65532:65532 /out/logs /app/logs

# 非 root 运行。scratch 没有 /etc/passwd，用数字 UID
USER 65532:65532

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD ["/app/balance-alert", "-healthcheck"]

EXPOSE 8080 9100
ENTRYPOINT ["/app/balance-alert"]
