package store

import (
	"fmt"
	"net"
	"net/url"
	"regexp"
	"strings"
)

// Engine 是识别出来的数据库类型，决定用哪套生成代码与建表 SQL。
type Engine string

const (
	EngineSQLite   Engine = "sqlite"
	EnginePostgres Engine = "postgres"
	EngineMySQL    Engine = "mysql"
)

// Target 是 DATABASE_URL 翻译后的结果。
//
// 配置里写的是连接串 URL 形式（scheme://user:password@host:port/database?params），
// 这里翻成各 Go 驱动认识的 DSN。
type Target struct {
	Engine     Engine
	DriverName string // database/sql 注册名
	DSN        string
	FilePath   string // 仅 SQLite：库文件路径，Open 要先建好父目录
}

// ParseURL 把 URL 形式的 DATABASE_URL 翻译成 Go 驱动的 DSN。
func ParseURL(databaseURL string) (Target, error) {
	raw := strings.TrimSpace(databaseURL)
	if raw == "" {
		return Target{}, fmt.Errorf("DATABASE_URL 为空")
	}

	scheme, rest, ok := strings.Cut(raw, "://")
	if !ok {
		return Target{}, fmt.Errorf("DATABASE_URL 缺少 :// ：%q", databaseURL)
	}
	// scheme 可能写成 dialect+driver（mysql+pymysql、postgresql+psycopg2）：
	// + 后面是驱动名，本实现只取前半段的数据库类型，驱动由这边自己选。
	dialect, _, _ := strings.Cut(strings.ToLower(scheme), "+")

	switch dialect {
	case "sqlite":
		return sqliteTarget(rest)
	case "postgresql", "postgres":
		return postgresTarget(rest)
	case "mysql", "mariadb":
		return mysqlTarget(rest)
	default:
		return Target{}, fmt.Errorf("不支持的数据库类型 %q，只支持 sqlite / postgresql / mysql", dialect)
	}
}

// urlParts 是连接串拆开后的各段：scheme://user:password@host:port/database?params。
type urlParts struct {
	User     string
	Password string
	HasPass  bool
	Host     string
	Port     string
	Database string
	Query    string
}

// parseConnURL 用自己的正则拆连接串，而不是交给 net/url。
//
// 差别要命：net/url 把 # 当片段起点、? 当查询起点，而数据库密码里这两个字符很常见。
// 生产上就踩到过——密码里一个 # 让整个连接串在那里被截断，报成「invalid port」。
// 这条正则只把第一个 @ 当凭据边界，# 和 ? 落在密码里都只是普通字符。
var connURLPattern = regexp.MustCompile(
	`^(?:(?P<user>[^:/@]*)(?::(?P<pass>[^@]*))?@)?` + // 凭据，密码取到第一个 @ 为止
		`(?:\[(?P<v6>[^\]]+)\]|(?P<host>[^/:@]*))?` + // 主机，支持 [::1] 形式
		`(?::(?P<port>[0-9]*))?` +
		`(?:/(?P<db>[^?]*))?` +
		`(?:\?(?P<query>.*))?$`)

func parseConnURL(rest string) (urlParts, error) {
	m := connURLPattern.FindStringSubmatch(rest)
	if m == nil {
		return urlParts{}, fmt.Errorf("连接串格式无法识别")
	}
	group := func(name string) string {
		return m[connURLPattern.SubexpIndex(name)]
	}

	host := group("host")
	if v6 := group("v6"); v6 != "" {
		host = v6
	}
	parts := urlParts{
		User:     unescapeLenient(group("user")),
		Host:     host,
		Port:     group("port"),
		Database: group("db"),
		Query:    group("query"),
	}
	// 有没有写密码要区分开：没写和写了空串是两回事
	if idx := strings.Index(rest, "@"); idx >= 0 {
		credentials := rest[:idx]
		if _, pass, ok := strings.Cut(credentials, ":"); ok {
			parts.Password, parts.HasPass = unescapeLenient(pass), true
		}
	}
	return parts, nil
}

// unescapeLenient 还原用户名密码里的百分号编码。
// 遇到不合法的转义序列就原样保留，而不是报错——密码里单独一个 % 很常见，
// 配置里也不会为它多写一层转义。
func unescapeLenient(value string) string {
	decoded, err := url.PathUnescape(value)
	if err != nil {
		return value
	}
	return decoded
}

// sqliteTarget 解析 sqlite:/// 后面的路径。
//
// 三斜杠与四斜杠的区别是相对路径与绝对路径：`sqlite:///./data/x.db`
// 指工作目录下的 ./data/x.db，`sqlite:////var/lib/x.db` 指根下的 /var/lib/x.db。
// 表现成字符串就是「去掉 :// 之后再去掉一个斜杠」，所以这里不走 net/url，免得它把路径规整掉。
func sqliteTarget(rest string) (Target, error) {
	path, query, _ := strings.Cut(rest, "?")
	path = strings.TrimPrefix(path, "/")
	if path == "" {
		path = ":memory:" // sqlite:// 与 sqlite:///:memory: 都是内存库
	}

	params, err := url.ParseQuery(query)
	if err != nil {
		return Target{}, fmt.Errorf("sqlite 连接串的查询参数有误：%w", err)
	}
	// 时间写回的格式必须钉死：驱动默认用 time.Time.String()，写出来是
	// "2026-09-14 03:09:37.277711 +0000 UTC"，和库里既有行的写法对不上，
	// 也让 SQLite 按文本比较的 timestamp >= ? 结果不可预期。
	// _time_format=sqlite 写成 ISO-8601，与既有数据同一种格式，新旧行才能一起比较排序。
	if !params.Has("_time_format") {
		params.Set("_time_format", "sqlite")
	}
	// SQLite 自身默认 busy_timeout 为 0，写锁一撞上就立刻返回 SQLITE_BUSY。
	// 这里给 5 秒锁等待，定时任务与页面写入撞在一起时才不会直接报错。
	if !params.Has("_pragma") {
		params.Set("_pragma", "busy_timeout(5000)")
	}

	filePath := path
	if path == ":memory:" {
		filePath = ""
	}
	return Target{
		Engine:     EngineSQLite,
		DriverName: "sqlite",
		DSN:        path + "?" + params.Encode(),
		FilePath:   filePath,
	}, nil
}

// postgresTarget 重新拼一个转义正确的 URL 再交给 pgx。
//
// 不能把原文直接透传：pgx 内部也是 net/url，密码里有 # 或 ? 一样会被截断。
func postgresTarget(rest string) (Target, error) {
	parts, err := parseConnURL(rest)
	if err != nil {
		return Target{}, fmt.Errorf("postgresql 连接串解析失败：%w", err)
	}

	target := url.URL{Scheme: "postgres", Path: "/" + parts.Database}
	if parts.User != "" {
		if parts.HasPass {
			target.User = url.UserPassword(parts.User, parts.Password)
		} else {
			target.User = url.User(parts.User)
		}
	}
	host := parts.Host
	if host == "" {
		host = "127.0.0.1"
	}
	if parts.Port != "" {
		host = net.JoinHostPort(host, parts.Port)
	}
	target.Host = host
	target.RawQuery = parts.Query

	return Target{Engine: EnginePostgres, DriverName: "pgx", DSN: target.String()}, nil
}

// mysqlTarget 把 URL 拆开重拼成 go-sql-driver 的 user:pass@tcp(host:port)/db?params 形式。
func mysqlTarget(rest string) (Target, error) {
	parts, err := parseConnURL(rest)
	if err != nil {
		return Target{}, fmt.Errorf("mysql 连接串解析失败：%w", err)
	}

	host := parts.Host
	if host == "" {
		host = "127.0.0.1"
	}
	port := parts.Port
	if port == "" {
		port = "3306"
	}

	// go-sql-driver 的 DSN 不做百分号解码，直接用还原后的原文
	var credentials string
	if parts.User != "" {
		credentials = parts.User
		if parts.HasPass {
			credentials += ":" + parts.Password
		}
		credentials += "@"
	}

	params, err := url.ParseQuery(parts.Query)
	if err != nil {
		return Target{}, fmt.Errorf("mysql 连接串的查询参数有误：%w", err)
	}
	// 时间列要拿到 time.Time 而不是 []byte，否则所有 timestamp 都得自己解析。
	if !params.Has("parseTime") {
		params.Set("parseTime", "true")
	}
	// 入库时间戳一律 UTC 是全局约定，这里显式钉住，免得驱动默认值变化或被人改掉。
	if !params.Has("loc") {
		params.Set("loc", "UTC")
	}

	dsn := fmt.Sprintf("%stcp(%s)/%s", credentials, net.JoinHostPort(host, port), parts.Database)
	if encoded := params.Encode(); encoded != "" {
		dsn += "?" + encoded
	}
	return Target{Engine: EngineMySQL, DriverName: "mysql", DSN: dsn}, nil
}
