package config

import (
	"os"
	"strings"
	"testing"
)

// Implementation note.
//
// Implementation note.
// Implementation note.
func TestMain(m *testing.M) {
	for _, entry := range os.Environ() {
		name, _, _ := strings.Cut(entry, "=")
		if shouldClear(name) {
			os.Unsetenv(name)
		}
	}
	os.Exit(m.Run())
}

func shouldClear(name string) bool {
	for _, suffix := range []string{"_API_KEY", "_THRESHOLD", "_OWNER_PROJECT"} {
		if strings.HasSuffix(name, suffix) {
			return true
		}
	}
	for _, prefix := range []string{"EMAIL_", "WEBHOOK_", "BALANCE_", "MAX_", "WEB_", "ENABLE_", "DATABASE_"} {
		if strings.HasPrefix(name, prefix) {
			return true
		}
	}
	return false
}
