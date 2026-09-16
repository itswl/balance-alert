package store

import (
	"crypto/sha256"
	"encoding/base64"
	"strings"

	"github.com/fernet/fernet-go"
)

// encryptedPrefix 标记一个值已经是密文。格式与 Python 版 core/secret_crypto.py 完全一致：
// 前缀 + Fernet token，升级后两边能互相读写同一张表。
const encryptedPrefix = "enc:v1:"

// cipher 负责 project_config.api_key 与 email_config.password 的加解密。
//
// key 为 nil 表示没设 CONFIG_ENCRYPTION_KEY，此时原样存取——加密是可选能力，
// 没配密钥不该让服务起不来，也不该把已有明文改坏。
type cipher struct {
	key *fernet.Key
}

// newCipher 按 Python 的规则推导密钥：CONFIG_ENCRYPTION_KEY 本身是合法 Fernet key 就直接用，
// 否则把它当口令，取 SHA-256 当密钥。
func newCipher(rawKey string) *cipher {
	raw := strings.TrimSpace(rawKey)
	if raw == "" {
		return &cipher{}
	}

	var key fernet.Key
	if decoded, ok := decodeFernetKey(raw); ok {
		copy(key[:], decoded)
	} else {
		// Python 是 urlsafe_b64encode(sha256(raw)) 再交给 Fernet 解码，
		// 一来一回就是 sha256 的原始摘要，这里省掉这趟 base64。
		sum := sha256.Sum256([]byte(raw))
		copy(key[:], sum[:])
	}
	return &cipher{key: &key}
}

// decodeFernetKey 判断 raw 是不是一个合法的 Fernet key，即 32 字节的 urlsafe base64。
//
// 这里刻意不用 fernet.DecodeKey：它还接受 64 位十六进制，而 Python 的 Fernet 不接受，
// 于是同一个 CONFIG_ENCRYPTION_KEY 在两边会推出不同的密钥，升级后老数据就解不开了。
//
// 判定规则逐条对齐 Python 的 base64.urlsafe_b64decode：
// 字母表之外的字符直接忽略（掺了一个 '!' 的 key 照样算合法），但补位符不能少——
// 43 个字符不带 '=' 会被判成口令而不是密钥。
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

// enabled 表示配了密钥，写入时才需要加密、读到明文时才需要回写。
func (c *cipher) enabled() bool { return c != nil && c.key != nil }

// isEncrypted 判断一个值是不是本项目格式的密文。
func isEncrypted(value string) bool { return strings.HasPrefix(value, encryptedPrefix) }

// encrypt 把明文变成密文。空值与已经加密过的值原样返回，和 Python 版一致：
// 这样重复保存同一条配置不会套上两层。
func (c *cipher) encrypt(value string) string {
	if value == "" || isEncrypted(value) || !c.enabled() {
		return value
	}
	token, err := fernet.EncryptAndSign([]byte(value), c.key)
	if err != nil {
		// Fernet 加密只在随机数不可用时失败，这种情况下宁可原样存也不要丢配置。
		return value
	}
	return encryptedPrefix + string(token)
}

// decrypt 把密文还原成明文。
//
// 解不开时返回原值而不是报错：密钥换掉或没配的时候，页面上显示一串密文，
// 总好过整个配置列表拉不出来。
func (c *cipher) decrypt(value string) string {
	if !isEncrypted(value) || !c.enabled() {
		return value
	}
	token := strings.TrimPrefix(value, encryptedPrefix)
	// ttl 传 0 表示不校验签发时间；Fernet token 里带时间戳，按有效期校验会让老配置突然读不出来。
	plain := fernet.VerifyAndDecrypt([]byte(token), 0, []*fernet.Key{c.key})
	if plain == nil {
		return value
	}
	return string(plain)
}
