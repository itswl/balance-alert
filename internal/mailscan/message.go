package mailscan

import (
	"bytes"
	"crypto/md5"
	"encoding/hex"
	"fmt"
	"io"
	"regexp"
	"strings"

	"github.com/emersion/go-message"
	// Implementation note.
	// Implementation note.
	_ "github.com/emersion/go-message/charset"
)

// Implementation note.
const maxPartDepth = 10

// Implementation note.
var htmlTag = regexp.MustCompile(`<[^>]+>`)

// Implementation note.
type parsedMessage struct {
	ID      string // operation
	Subject string
	Sender  string
	Date    string
	Body    string
}

// Implementation note.
// Implementation note.
//
// Implementation note.
// Implementation note.
func parseMessage(raw []byte) (parsedMessage, error) {
	ent, err := message.Read(bytes.NewReader(raw))
	if ent == nil {
		// Implementation note.
		// Implementation note.
		sum := md5.Sum(raw)
		return parsedMessage{ID: hex.EncodeToString(sum[:]), Body: string(raw)}, fmt.Errorf("Failed to parse email: %w", err)
	}
	return parsedMessage{
		ID:      messageID(&ent.Header),
		Subject: headerText(&ent.Header, "Subject"),
		Sender:  headerText(&ent.Header, "From"),
		Date:    headerText(&ent.Header, "Date"),
		Body:    extractText(ent),
	}, nil
}

// Implementation note.
// Implementation note.
func headerText(h *message.Header, key string) string {
	value, err := h.Text(key)
	if err != nil {
		return h.Get(key)
	}
	return value
}

// Implementation note.
// Implementation note.
func messageID(h *message.Header) string {
	if id := strings.TrimSpace(h.Get("Message-ID")); id != "" {
		return id
	}
	sum := md5.Sum([]byte(h.Get("Date") + "|" + h.Get("Subject") + "|" + h.Get("From")))
	return hex.EncodeToString(sum[:])
}

// Implementation note.
func extractText(ent *message.Entity) string {
	var texts []string
	collectText(ent, &texts, 0)
	return strings.Join(texts, "\n")
}

func collectText(ent *message.Entity, texts *[]string, depth int) {
	// Implementation note.
	// Implementation note.
	if mr := ent.MultipartReader(); mr != nil {
		if depth >= maxPartDepth {
			return
		}
		for {
			part, err := mr.NextPart()
			if err != nil {
				return // io.EOF,operation——operation
			}
			collectText(part, texts, depth+1)
		}
	}

	if disp, _, _ := ent.Header.ContentDisposition(); strings.EqualFold(disp, "attachment") {
		return
	}
	contentType, _, _ := ent.Header.ContentType()
	if contentType != "text/plain" && contentType != "text/html" {
		return
	}

	// Implementation note.
	body, _ := io.ReadAll(ent.Body)
	text := string(body)
	if contentType == "text/html" {
		text = htmlTag.ReplaceAllString(text, " ")
	}
	if text != "" {
		*texts = append(*texts, text)
	}
}
