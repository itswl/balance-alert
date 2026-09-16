package config

import (
	"bufio"
	"fmt"
	"os"
	"strconv"
	"strings"

	"github.com/itswl/balance-alert/internal/model"
	"github.com/itswl/balance-alert/internal/provider"
)

// MaxEnvAccounts 是自动发现时一个 provider / 一组邮箱变量最多认几个账号（后缀 _1 … _N）。
const MaxEnvAccounts = 10

// LoadEnvFile 把 .env 写进环境变量，已存在的同名变量会被覆盖。
// 文件不存在不是错误：容器和 K8s 里本来就直接给环境变量。
func LoadEnvFile(path string) error {
	file, err := os.Open(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return err
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	for lineNo := 1; scanner.Scan(); lineNo++ {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		line = strings.TrimPrefix(line, "export ")
		key, value, ok := strings.Cut(line, "=")
		if !ok {
			return fmt.Errorf("%s 第 %d 行不是 KEY=VALUE 格式", path, lineNo)
		}
		key = strings.TrimSpace(key)
		value = strings.TrimSpace(value)
		// 整体加引号时去掉引号；不去行内 # 注释，密钥里本来就可能有 #
		if len(value) >= 2 && (value[0] == '"' && value[len(value)-1] == '"' ||
			value[0] == '\'' && value[len(value)-1] == '\'') {
			value = value[1 : len(value)-1]
		}
		if err := os.Setenv(key, value); err != nil {
			return err
		}
	}
	return scanner.Err()
}

// envVariants 返回一个字段可用的环境变量名。
// 序号 1 同时接受 PREFIX_SUFFIX 与 PREFIX_1_SUFFIX，避免同一账号被认成两个。
func envVariants(prefix, suffix string, ordinal int) []string {
	if ordinal <= 1 {
		return []string{prefix + "_" + suffix, prefix + "_1_" + suffix}
	}
	return []string{fmt.Sprintf("%s_%d_%s", prefix, ordinal, suffix)}
}

// envFirst 取第一个有值的变体。
func envFirst(prefix, suffix string, ordinal int) string {
	for _, name := range envVariants(prefix, suffix, ordinal) {
		if value, ok := raw(name); ok {
			return value
		}
	}
	return ""
}

func envFirstFloat(prefix, suffix string, ordinal int) float64 {
	value := envFirst(prefix, suffix, ordinal)
	if value == "" {
		return 0
	}
	f, err := strconv.ParseFloat(value, 64)
	if err != nil {
		return 0
	}
	return f
}

// ProviderKeyEnvNames 是某个 provider 第 ordinal 个账号的密钥变量名，自检用它提示该配哪个。
func ProviderKeyEnvNames(providerKey string, ordinal int) []string {
	if providerKey == "" {
		return nil
	}
	return envVariants(strings.ToUpper(providerKey), "API_KEY", ordinal)
}

// DiscoverProjects 从环境变量里发现受监控项目。
//
// 没在 declared 里出现过的 provider，只要设了 {PROVIDER}_API_KEY 就自动纳入。
// 阈值取 {PROVIDER}_THRESHOLD，不填就是 0，永不告警，自检会提示。
func DiscoverProjects(declared []model.Project) []model.Project {
	declaredProviders := make(map[string]bool, len(declared))
	for _, p := range declared {
		declaredProviders[strings.ToLower(strings.TrimSpace(p.Provider))] = true
	}

	var discovered []model.Project
	for _, key := range provider.Keys() {
		if declaredProviders[key] {
			continue
		}
		upper := strings.ToUpper(key)

		type account struct {
			ordinal int
			apiKey  string
		}
		var accounts []account
		for ordinal := 1; ordinal <= MaxEnvAccounts; ordinal++ {
			if apiKey := envFirst(upper, "API_KEY", ordinal); apiKey != "" {
				accounts = append(accounts, account{ordinal, apiKey})
			}
		}

		for _, acct := range accounts {
			name := key
			if len(accounts) > 1 {
				name = fmt.Sprintf("%s-%d", key, acct.ordinal)
			}
			discovered = append(discovered, model.Project{
				Name:         name,
				Provider:     key,
				APIKey:       acct.apiKey,
				Threshold:    envFirstFloat(upper, "THRESHOLD", acct.ordinal),
				Type:         model.DefaultBalanceType(key),
				OwnerProject: model.OwnerProjectOf(envFirst(upper, "OWNER_PROJECT", acct.ordinal)),
				Enabled:      true,
				FromEnv:      true,
			})
		}
	}
	return discovered
}

// DiscoverMailboxes 从环境变量里发现要扫描的邮箱。
//
// EMAIL_HOST / EMAIL_USERNAME / EMAIL_PASSWORD 三个齐全就纳入扫描，
// 多个邮箱用 EMAIL_1_HOST / EMAIL_2_HOST。名称或账号已声明过的不重复添加。
func DiscoverMailboxes(declared []model.Mailbox) []model.Mailbox {
	declaredNames := make(map[string]bool, len(declared)*2)
	for _, m := range declared {
		declaredNames[m.Name] = true
		declaredNames[m.Username] = true
	}

	var discovered []model.Mailbox
	for ordinal := 1; ordinal <= MaxEnvAccounts; ordinal++ {
		host := envFirst("EMAIL", "HOST", ordinal)
		username := envFirst("EMAIL", "USERNAME", ordinal)
		password := envFirst("EMAIL", "PASSWORD", ordinal)
		if host == "" || username == "" || password == "" {
			continue
		}
		name := envFirst("EMAIL", "NAME", ordinal)
		if name == "" {
			name = username
		}
		if declaredNames[name] || declaredNames[username] {
			continue
		}

		port := 993
		if value := envFirst("EMAIL", "PORT", ordinal); value != "" {
			if n, err := strconv.Atoi(value); err == nil && n > 0 {
				port = n
			}
		}
		useSSL := true
		if value := envFirst("EMAIL", "USE_SSL", ordinal); value != "" {
			useSSL = truthy[strings.ToLower(value)]
		}

		discovered = append(discovered, model.Mailbox{
			Name: name, Host: host, Port: port, Username: username,
			Password: password, UseSSL: useSSL, Enabled: true, FromEnv: true,
		})
		// 同一轮里也不许重名
		declaredNames[name] = true
		declaredNames[username] = true
	}
	return discovered
}

// ResolveAPIKey 给没写密钥的项目按约定补上环境变量里的值。
// ordinal 是同一 provider 在清单里的出现次序。返回密钥与它的来源说明。
func ResolveAPIKey(p model.Project, ordinal int) (string, string) {
	if p.APIKey != "" {
		return p.APIKey, "配置里的 api_key 字段"
	}
	for _, name := range ProviderKeyEnvNames(p.Provider, ordinal) {
		if value, ok := raw(name); ok {
			return value, "环境变量 " + name
		}
	}
	return "", ""
}
