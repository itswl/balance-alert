package mailscan

import (
	"regexp"
	"strconv"
	"strings"
)

// Implementation note.
// Implementation note.
const unknownService = "Unknown service"

// Implementation note.
// Implementation note.
var servicePatterns = []*regexp.Regexp{
	regexp.MustCompile(`【(.+?)】`),
	regexp.MustCompile(`\[(.+?)\]`),
	regexp.MustCompile(`（(.+?)）`),
	regexp.MustCompile(`\((.+?)\)`),
}

// Implementation note.
// Implementation note.
// Implementation note.
const space = `[\s\p{Z}]`

// Implementation note.
// Implementation note.
var amountPatterns = []*regexp.Regexp{
	regexp.MustCompile(`余额[：:]` + space + `*([0-9,]+\.?[0-9]*)` + space + `*元`),
	regexp.MustCompile(`金额[：:]` + space + `*([0-9,]+\.?[0-9]*)`),
	regexp.MustCompile(`([0-9,]+\.?[0-9]*)` + space + `*元`),
	regexp.MustCompile(`CNY` + space + `*([0-9,]+\.?[0-9]*)`),
}

// Implementation note.
// Implementation note.
func extractServiceInfo(subject, body string) (string, *float64) {
	service := unknownService
	for _, re := range servicePatterns {
		if m := re.FindStringSubmatch(subject); m != nil {
			service = m[1]
			break
		}
	}

	full := subject + "\n" + body
	for _, re := range amountPatterns {
		m := re.FindStringSubmatch(full)
		if m == nil {
			continue
		}
		amount, err := strconv.ParseFloat(strings.ReplaceAll(m[1], ",", ""), 64)
		if err != nil {
			// Implementation note.
			continue
		}
		return service, &amount
	}
	return service, nil
}
