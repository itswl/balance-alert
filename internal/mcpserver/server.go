// Package mcpserver exposes the read-only balance-alert state through MCP.
//
// It is deliberately attached to the existing authenticated HTTP service. The
// MCP server therefore observes the same in-memory state as the dashboard and
// does not create a second scheduler, database writer, or credential path.
package mcpserver

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"net/url"
	"strings"

	"github.com/itswl/balance-alert/internal/config"
	"github.com/itswl/balance-alert/internal/state"
	"github.com/itswl/balance-alert/internal/store"
	sdkmcp "github.com/modelcontextprotocol/go-sdk/mcp"
)

const stateResourceTemplate = "balance-alert://state/{kind}"

type emptyInput struct{}

type historyInput struct {
	Days  int `json:"days,omitempty" jsonschema:"number of days to search, between 1 and 365"`
	Limit int `json:"limit,omitempty" jsonschema:"maximum number of rows, between 1 and 100"`
}

// NewHandler returns a stateless Streamable HTTP MCP handler. Authentication is
// applied by the surrounding httpapi middleware, just like /api/*.
func NewHandler(settings *config.Settings, runtime *state.Manager, history store.Store, log *slog.Logger) http.Handler {
	serverFactory := func(_ *http.Request) *sdkmcp.Server {
		server := sdkmcp.NewServer(
			&sdkmcp.Implementation{Name: "balance-alert", Version: settings.AppVersion},
			&sdkmcp.ServerOptions{
				Instructions: "Read balance-alert status, subscriptions, email scan results, jobs, health, and alert history. This server is read-only.",
				Logger:       log,
			},
		)
		addStateTools(server, runtime, history)
		addStateResources(server, runtime)
		return server
	}

	return sdkmcp.NewStreamableHTTPHandler(serverFactory, &sdkmcp.StreamableHTTPOptions{
		Stateless:    true,
		JSONResponse: true,
		Logger:       log,
	})
}

func addStateTools(server *sdkmcp.Server, runtime *state.Manager, history store.Store) {
	addJSONTool(server, "balance_status", "Current balance and runway results for all monitored projects.", runtime.Balance)
	addJSONTool(server, "subscription_status", "Current subscription renewal status.", runtime.Subscriptions)
	addJSONTool(server, "email_scan_status", "Latest mailbox scan results and detected alert emails.", runtime.EmailScan)
	addJSONTool(server, "job_status", "Scheduler status, last runs, failures, and next runs.", runtime.Jobs)
	addJSONTool(server, "health", "Readiness-style health summary for the running service.", func() any {
		balance := runtime.Balance()
		jobs := runtime.Jobs()
		return map[string]any{
			"status":         healthStatus(balance, jobs),
			"has_data":       len(balance.Projects) > 0,
			"jobs":           jobs,
			"uptime_seconds": runtime.UptimeSeconds(),
		}
	})

	sdkmcp.AddTool(server, &sdkmcp.Tool{
		Name:        "recent_alerts",
		Description: "Read recent persisted balance, subscription, runway, and spend-spike alerts. Returns an empty list when database history is disabled.",
	}, func(ctx context.Context, _ *sdkmcp.CallToolRequest, in historyInput) (*sdkmcp.CallToolResult, any, error) {
		q := store.AlertQuery{Days: bounded(in.Days, 30, 1, 365), Limit: bounded(in.Limit, 50, 1, 100)}
		rows, err := history.RecentAlerts(ctx, q)
		if err != nil {
			return nil, nil, err
		}
		return jsonResult(map[string]any{"count": len(rows), "data": rows})
	})

	sdkmcp.AddTool(server, &sdkmcp.Tool{
		Name:        "recent_email_alerts",
		Description: "Read recent persisted email alert records. Returns an empty list when database history is disabled.",
	}, func(ctx context.Context, _ *sdkmcp.CallToolRequest, in historyInput) (*sdkmcp.CallToolResult, any, error) {
		q := store.EmailAlertQuery{Days: bounded(in.Days, 30, 1, 365), Limit: bounded(in.Limit, 50, 1, 100)}
		rows, err := history.EmailAlerts(ctx, q)
		if err != nil {
			return nil, nil, err
		}
		return jsonResult(map[string]any{"count": len(rows), "data": rows})
	})
}

func addJSONTool[T any](server *sdkmcp.Server, name, description string, read func() T) {
	sdkmcp.AddTool(server, &sdkmcp.Tool{Name: name, Description: description},
		func(context.Context, *sdkmcp.CallToolRequest, emptyInput) (*sdkmcp.CallToolResult, any, error) {
			return jsonResult(read())
		})
}

func addStateResources(server *sdkmcp.Server, runtime *state.Manager) {
	server.AddResourceTemplate(&sdkmcp.ResourceTemplate{
		Name:        "balance-alert-state",
		URITemplate: stateResourceTemplate,
		Description: "Read-only JSON resources for the current balance-alert runtime state.",
		MIMEType:    "application/json",
	}, func(_ context.Context, req *sdkmcp.ReadResourceRequest) (*sdkmcp.ReadResourceResult, error) {
		kind, err := stateKind(req.Params.URI)
		if err != nil {
			return nil, err
		}
		var value any
		switch kind {
		case "balance":
			value = runtime.Balance()
		case "subscriptions":
			value = runtime.Subscriptions()
		case "email":
			value = runtime.EmailScan()
		case "jobs":
			value = runtime.Jobs()
		default:
			return nil, fmt.Errorf("unknown state resource %q", kind)
		}
		body, marshalErr := json.MarshalIndent(value, "", "  ")
		if marshalErr != nil {
			return nil, marshalErr
		}
		return &sdkmcp.ReadResourceResult{Contents: []*sdkmcp.ResourceContents{{
			URI: req.Params.URI, MIMEType: "application/json", Text: string(body),
		}}}, nil
	})
}

func stateKind(raw string) (string, error) {
	u, err := url.Parse(raw)
	if err != nil || u.Scheme != "balance-alert" || u.Host != "state" {
		return "", fmt.Errorf("invalid state resource URI")
	}
	kind := strings.Trim(strings.TrimPrefix(u.Path, "/"), " ")
	if strings.Contains(kind, "/") || kind == "" {
		return "", fmt.Errorf("invalid state resource URI")
	}
	return kind, nil
}

func healthStatus(balance state.BalanceState, jobs state.JobState) string {
	if len(balance.Projects) == 0 || !jobs.Healthy {
		return "degraded"
	}
	return "healthy"
}

func bounded(value, fallback, min, max int) int {
	if value == 0 {
		return fallback
	}
	if value < min {
		return min
	}
	if value > max {
		return max
	}
	return value
}

func jsonResult(value any) (*sdkmcp.CallToolResult, any, error) {
	body, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return nil, nil, err
	}
	return &sdkmcp.CallToolResult{Content: []sdkmcp.Content{
		&sdkmcp.TextContent{Text: string(body)},
	}}, nil, nil
}
