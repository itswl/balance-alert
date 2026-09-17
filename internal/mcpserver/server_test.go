package mcpserver

import "testing"

func TestStateKind(t *testing.T) {
	for _, tc := range []struct {
		uri, want string
	}{
		{"balance-alert://state/balance", "balance"},
		{"balance-alert://state/subscriptions", "subscriptions"},
		{"balance-alert://state/email", "email"},
	} {
		got, err := stateKind(tc.uri)
		if err != nil || got != tc.want {
			t.Errorf("stateKind(%q) = %q, %v; want %q", tc.uri, got, err, tc.want)
		}
	}
	for _, uri := range []string{"https://example.test/state/balance", "balance-alert://other/balance", "balance-alert://state/"} {
		if _, err := stateKind(uri); err == nil {
			t.Errorf("stateKind(%q) accepted an invalid URI", uri)
		}
	}
}

func TestBounded(t *testing.T) {
	if got := bounded(0, 30, 1, 365); got != 30 {
		t.Errorf("zero should use fallback, got %d", got)
	}
	if got := bounded(-1, 30, 1, 365); got != 1 {
		t.Errorf("low value should clamp, got %d", got)
	}
	if got := bounded(500, 30, 1, 365); got != 365 {
		t.Errorf("high value should clamp, got %d", got)
	}
}
