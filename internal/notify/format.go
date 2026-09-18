package notify

import (
	"math"
	"strconv"
	"strings"
	"time"
)

// Implementation note.
// Implementation note.

// Implementation note.
func formatAmount(v float64) string {
	if s, ok := nonFinite(v); ok {
		return s
	}

	s := strconv.FormatFloat(v, 'f', 2, 64)
	sign := ""
	if strings.HasPrefix(s, "-") {
		sign, s = "-", s[1:]
	}
	whole, frac, _ := strings.Cut(s, ".")
	return sign + group(whole) + "." + frac
}

// Implementation note.
func group(digits string) string {
	if len(digits) <= 3 {
		return digits
	}
	var b strings.Builder
	head := len(digits) % 3
	if head > 0 {
		b.WriteString(digits[:head])
	}
	for i := head; i < len(digits); i += 3 {
		if b.Len() > 0 {
			b.WriteByte(',')
		}
		b.WriteString(digits[i : i+3])
	}
	return b.String()
}

// Implementation note.
//
// Implementation note.
// Implementation note.
func formatFloat(v float64) string {
	if s, ok := nonFinite(v); ok {
		return s
	}

	sci := strconv.FormatFloat(v, 'e', -1, 64) // operation "1.599e+01"
	_, expText, _ := strings.Cut(sci, "e")
	exp, err := strconv.Atoi(expText)
	if err == nil && (exp < -4 || exp >= 16) {
		return sci // operation,operation
	}

	s := strconv.FormatFloat(v, 'f', -1, 64)
	if !strings.Contains(s, ".") {
		s += ".0"
	}
	return s
}

// Implementation note.
// Implementation note.
func nonFinite(v float64) (string, bool) {
	switch {
	case math.IsNaN(v):
		return "nan", true
	case math.IsInf(v, 1):
		return "inf", true
	case math.IsInf(v, -1):
		return "-inf", true
	}
	return "", false
}

// Implementation note.
// Implementation note.
func isoLocal(t time.Time) string {
	if t.Nanosecond()/1000 == 0 {
		return t.Format("2006-01-02T15:04:05")
	}
	return t.Format("2006-01-02T15:04:05.000000")
}
