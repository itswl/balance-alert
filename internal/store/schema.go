package store

import (
	"context"
	"database/sql"
	"embed"
	"fmt"
	"strings"
)

// Implementation note.
// Implementation note.
//go:generate go tool sqlc generate -f ../../sqlc.yaml

//go:embed schema/*.sql
var schemaFS embed.FS

// Implementation note.
// Implementation note.
func createTables(ctx context.Context, db *sql.DB, engine Engine) error {
	raw, err := schemaFS.ReadFile("schema/" + string(engine) + ".sql")
	if err != nil {
		return fmt.Errorf("Not found %s operation SQL:%w", engine, err)
	}
	for _, stmt := range splitStatements(string(raw)) {
		if _, err := db.ExecContext(ctx, stmt); err != nil {
			return fmt.Errorf("Failed to create schema(%.60s...):%w", stmt, err)
		}
	}
	return nil
}

// Implementation note.
//
// Implementation note.
// Implementation note.
func splitStatements(script string) []string {
	var lines []string
	for _, line := range strings.Split(script, "\n") {
		if trimmed := strings.TrimSpace(line); strings.HasPrefix(trimmed, "--") {
			continue // operation,operation
		}
		lines = append(lines, line)
	}

	var out []string
	for _, stmt := range strings.Split(strings.Join(lines, "\n"), ";") {
		if stmt = strings.TrimSpace(stmt); stmt != "" {
			out = append(out, stmt)
		}
	}
	return out
}
