# Architecture and conventions

## Layers

A balance check follows this path: `provider` fetches a balance, `monitor` applies thresholds, `store` records history, `runway` derives trends, and `notify` sends alerts. `state` holds the in-memory dashboard snapshot and `httpapi` exposes it. `app` assembles the dependencies; `cmd` owns CLI flags and signals.

Dependencies are intentionally one-way. `model` and `timeutil` are independent, `store` depends only on `model`, and `notify` depends only on `model`. These packages can be constructed directly in tests without environment setup.

## Conventions

- Comments explain why a decision exists; package comments describe the package responsibility.
- Use pointers for nullable numbers. `*float64` serializes as `null`; using zero for “not found” would make the dashboard display an outage as an empty balance.
- Optional capabilities degrade gracefully. When the database is unavailable, the application falls back to `store.Null()`: history, cooldowns, and audit records are unavailable, but balance alerts continue. Set `STRICT_DATABASE_ERRORS` to fail startup instead.
- Do not add a web framework. Routing uses the standard-library `net/http` `ServeMux`.
- Keep dependencies small: Prometheus, IMAP, Fernet encryption, and the three database drivers.
- Date, signing, and parsing code must have table-driven boundary tests.

## Data contracts

These values are compatibility contracts with existing deployments:

- `project_id = md5("provider:name")` and `subscription_id = md5("subscription:name")` identify history and alert cooldown records.
- Table and column names for the six persisted tables.
- Ciphertext format: `enc:v1:` followed by a Fernet token. A valid Fernet key is used directly; any other encryption setting is SHA-256 hashed and URL-safe base64 encoded.
- `DATABASE_URL` uses `scheme://user:password@host:port/database?params`. The store translates it into each driver's DSN; a `+driver` suffix is accepted and ignored for scheme selection. Do not parse this format with `net/url`, because a `#` in a password is meaningful data.
- Floating-point values use banker’s rounding (`math.RoundToEven`) so the same history produces stable dashboard and alert values.

The fixture at `internal/store/testdata/legacy.db` is a real legacy database. `TestReadsLegacyDatabase` checks that all six tables remain readable and writable.

## Time

- Schedules use the process local time zone; the container's `TZ` controls it.
- Stored timestamps are UTC and API timestamps use ISO 8601 with a trailing `Z`.
- Time-zone data is compiled into the binary with `time/tzdata`; the runtime image does not need a system tzdata package.

## Adding a provider

Most providers make one GET request and extract a number from JSON:

```go
func init() {
    RegisterSpec(Spec{
        Key: "example", Name: "Example", DefaultType: model.TypeBalance,
        URL: "https://api.example.com/v1/balance",
        Extract: func(data map[string]any) (float64, error) {
            value, ok := Num(Dig(data, "data", "balance"))
            if !ok {
                return 0, errors.New("could not read data.balance from provider response")
            }
            return value, nil
        },
    })
}
```

Providers that require signing can implement and register the `Provider` interface directly, following `volc.go` and `aliyun.go`.

## Verification

```bash
go build ./... && go vet ./... && go test -race ./...
gofmt -l .
npm --prefix ui run typecheck
npm --prefix ui test
```
