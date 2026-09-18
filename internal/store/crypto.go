package store

import (
	"crypto/sha256"
	"encoding/base64"
	"strings"

	"github.com/fernet/fernet-go"
)

// Implementation note.
// Implementation note.
const encryptedPrefix = "enc:v1:"

// Implementation note.
//
// Implementation note.
// Implementation note.
type cipher struct {
	key *fernet.Key
}

// Implementation note.
// Implementation note.
// Implementation note.
func newCipher(rawKey string) *cipher {
	raw := strings.TrimSpace(rawKey)
	if raw == "" {
		return &cipher{}
	}

	var key fernet.Key
	if decoded, ok := decodeFernetKey(raw); ok {
		copy(key[:], decoded)
	} else {
		// Implementation note.
		// Implementation note.
		sum := sha256.Sum256([]byte(raw))
		copy(key[:], sum[:])
	}
	return &cipher{key: &key}
}

// Implementation note.
//
// Implementation note.
// Implementation note.
//
// Implementation note.
// Implementation note.
// Implementation note.
func decodeFernetKey(raw string) ([]byte, bool) {
	var b strings.Builder
	for _, r := range raw {
		switch {
		case r >= 'A' && r <= 'Z', r >= 'a' && r <= 'z', r >= '0' && r <= '9', r == '=':
			b.WriteRune(r)
		case r == '-', r == '+':
			b.WriteByte('+')
		case r == '_', r == '/':
			b.WriteByte('/')
		}
	}
	decoded, err := base64.StdEncoding.DecodeString(b.String())
	if err != nil || len(decoded) != 32 {
		return nil, false
	}
	return decoded, true
}

// Implementation note.
func (c *cipher) enabled() bool { return c != nil && c.key != nil }

// Implementation note.
func isEncrypted(value string) bool { return strings.HasPrefix(value, encryptedPrefix) }

// Implementation note.
// Implementation note.
func (c *cipher) encrypt(value string) string {
	if value == "" || isEncrypted(value) || !c.enabled() {
		return value
	}
	token, err := fernet.EncryptAndSign([]byte(value), c.key)
	if err != nil {
		// Implementation note.
		return value
	}
	return encryptedPrefix + string(token)
}

// Implementation note.
//
// Implementation note.
// Implementation note.
func (c *cipher) decrypt(value string) string {
	if !isEncrypted(value) || !c.enabled() {
		return value
	}
	token := strings.TrimPrefix(value, encryptedPrefix)
	// Implementation note.
	plain := fernet.VerifyAndDecrypt([]byte(token), 0, []*fernet.Key{c.key})
	if plain == nil {
		return value
	}
	return string(plain)
}
