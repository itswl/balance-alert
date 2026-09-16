package config

import (
	"os"
	"strings"
	"testing"
)

// TestMain 清掉会影响自动发现的环境变量。
//
// Python 版在这里栽过：开发机 .env 里的真实密钥漏进测试，用例一跑就真的去请求上游平台。
// 测试必须从一张白纸开始，只看用例自己 Setenv 的那些值。
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
