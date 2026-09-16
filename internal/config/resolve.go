package config

import (
	"context"
	"log/slog"
	"strings"

	"github.com/itswl/balance-alert/internal/model"
	"github.com/itswl/balance-alert/internal/store"
)

// Resolver 每次调用都重新拼出业务清单：数据库动态配置 + 环境变量自动发现。
//
// 不做缓存。页面上改完配置要立刻生效，而这几张表最多几十行，读一次的代价可以忽略。
type Resolver struct {
	settings *Settings
	store    store.Store
	log      *slog.Logger
}

// NewResolver 创建清单解析器。store 可以是 store.Null()。
func NewResolver(settings *Settings, st store.Store, log *slog.Logger) *Resolver {
	if log == nil {
		log = slog.Default()
	}
	return &Resolver{settings: settings, store: st, log: log}
}

// Load 返回补齐字段后的三段业务清单。
//
// 数据库读失败不致命：退回到"只有环境变量"，服务继续跑，日志里留一条警告。
func (r *Resolver) Load(ctx context.Context) model.Config {
	cfg := model.Config{}
	if r.settings.EnableDynamicConfig {
		cfg = r.fromDatabase(ctx)
	}

	cfg.Projects = append(cfg.Projects, DiscoverProjects(cfg.Projects)...)
	cfg.Mailboxes = append(cfg.Mailboxes, DiscoverMailboxes(cfg.Mailboxes)...)
	r.normalize(&cfg)
	return cfg
}

func (r *Resolver) fromDatabase(ctx context.Context) model.Config {
	var cfg model.Config
	var failed bool

	if projects, err := r.store.ListProjects(ctx); err != nil {
		failed = true
		r.log.Warn("读取数据库项目配置失败，仅使用环境变量", "error", err)
	} else {
		cfg.Projects = projects
	}
	if subs, err := r.store.ListSubscriptions(ctx); err != nil {
		failed = true
		r.log.Warn("读取数据库订阅配置失败", "error", err)
	} else {
		cfg.Subscriptions = subs
	}
	if boxes, err := r.store.ListMailboxes(ctx); err != nil {
		failed = true
		r.log.Warn("读取数据库邮箱配置失败", "error", err)
	} else {
		cfg.Mailboxes = boxes
	}
	if failed && r.settings.StrictDatabaseErrors {
		r.log.Error("STRICT_DATABASE_ERRORS 已开启，动态配置读取失败会影响清单完整性")
	}
	return cfg
}

// normalize 补齐省略字段，让下游只面对完整记录。
func (r *Resolver) normalize(cfg *model.Config) {
	ordinals := make(map[string]int)
	for i := range cfg.Projects {
		p := &cfg.Projects[i]
		model.NormalizeProject(p)
		ordinals[p.Provider]++
		if key, _ := ResolveAPIKey(*p, ordinals[p.Provider]); key != "" {
			p.APIKey = key
		}
	}
	for i := range cfg.Subscriptions {
		s := &cfg.Subscriptions[i]
		if s.CycleType == "" {
			s.CycleType = model.CycleMonthly
		}
		s.CycleType = strings.ToLower(strings.TrimSpace(s.CycleType))
		if s.AlertDaysBefore < 0 {
			s.AlertDaysBefore = 0
		}
	}
	for i := range cfg.Mailboxes {
		m := &cfg.Mailboxes[i]
		if m.Port <= 0 {
			m.Port = 993
		}
		if m.Name == "" {
			m.Name = m.Username
		}
	}
}

// KeySource 返回某个项目密钥的来源说明与可用的候选变量名，自检用。
func KeySource(p model.Project, ordinal int) (source string, candidates []string) {
	source, _ = "", ""
	if p.APIKey == "" {
		return "", ProviderKeyEnvNames(p.Provider, ordinal)
	}
	for _, name := range ProviderKeyEnvNames(p.Provider, ordinal) {
		if value, ok := raw(name); ok && value == p.APIKey {
			return "环境变量 " + name, nil
		}
	}
	return "配置里的 api_key 字段", nil
}
