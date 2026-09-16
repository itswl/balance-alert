package store

import (
	"fmt"
	"net/url"
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
// 配置里仍写 SQLAlchemy 那套 URL（升级时不用改环境变量），这里翻成各 Go 驱动认识的 DSN。
type Target struct {
	Engine     Engine
	DriverName string // database/sql 注册名
	DSN        string
	FilePath   string // 仅 SQLite：库文件路径，Open 要先建好父目录
}

// ParseURL 把 SQLAlchemy 写法的 DATABASE_URL 翻译成 Go 驱动的 DSN。
func ParseURL(databaseURL string) (Target, error) {
	raw := strings.TrimSpace(databaseURL)
	if raw == "" {
		return Target{}, fmt.Errorf("DATABASE_URL 为空")
	}

	scheme, rest, ok := strings.Cut(raw, "://")
	if !ok {
		return Target{}, fmt.Errorf("DATABASE_URL 缺少 :// ：%q", databaseURL)
	}
	// SQLAlchemy 的 dialect+driver 写法（mysql+pymysql、postgresql+psycopg2）里，
	// 驱动名是 Python 侧的事，Go 只认前半段。
	dialect, _, _ := strings.Cut(strings.ToLower(scheme), "+")

	switch dialect {
	case "sqlite":
		return sqliteTarget(rest)
	case "postgresql", "postgres":
		return postgresTarget(raw, rest)
	case "mysql", "mariadb":
		return mysqlTarget(raw, rest)
	default:
		return Target{}, fmt.Errorf("不支持的数据库类型 %q，只支持 sqlite / postgresql / mysql", dialect)
	}
}

// sqliteTarget 解析 sqlite:/// 后面的路径。
//
// 三斜杠与四斜杠的区别在 SQLAlchemy 里是相对路径与绝对路径：`sqlite:///./data/x.db`
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
	// "2026-09-14 03:09:37.277711 +0000 UTC"，既不是 SQLAlchemy 写的格式，
	// 也让 SQLite 按文本比较的 timestamp >= ? 结果不可预期。
	// _time_format=sqlite 让它写成 ISO-8601，Go 与 Python 都能读回。
	if !params.Has("_time_format") {
		params.Set("_time_format", "sqlite")
	}
	// pysqlite 默认有 5 秒锁等待，SQLite 自身默认是 0（立刻返回 SQLITE_BUSY）。
	// 补齐这一条，Go 版并发写才不会比 Python 版更容易失败。
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

// postgresTarget 交给 pgx 的 stdlib 驱动，它直接认 postgres:// URL，只需去掉 +driver 后缀。
func postgresTarget(raw, rest string) (Target, error) {
	if _, err := url.Parse(raw); err != nil {
		return Target{}, fmt.Errorf("postgresql 连接串解析失败：%w", err)
	}
	return Target{
		Engine:     EnginePostgres,
		DriverName: "pgx",
		DSN:        "postgres://" + rest,
	}, nil
}

// mysqlTarget 把 URL 拆开重拼成 go-sql-driver 的 user:pass@tcp(host:port)/db?params 形式。
func mysqlTarget(raw, rest string) (Target, error) {
	u, err := url.Parse("mysql://" + rest)
	if err != nil {
		return Target{}, fmt.Errorf("mysql 连接串解析失败：%w", err)
	}

	host := u.Hostname()
	if host == "" {
		host = "127.0.0.1"
	}
	port := u.Port()
	if port == "" {
		port = "3306"
	}

	var credentials string
	if u.User != nil {
		// URL 里的用户名密码是百分号编码的，go-sql-driver 不解码，这里要还原成原文。
		name := u.User.Username()
		if password, ok := u.User.Password(); ok {
			credentials = name + ":" + password + "@"
		} else if name != "" {
			credentials = name + "@"
		}
	}

	params := u.Query()
	// 时间列要拿到 time.Time 而不是 []byte，否则所有 timestamp 都得自己解析。
	if !params.Has("parseTime") {
		params.Set("parseTime", "true")
	}
	// 入库时间戳一律 UTC 是全局约定，这里显式钉住，免得驱动默认值变化或被人改掉。
	if !params.Has("loc") {
		params.Set("loc", "UTC")
	}

	dsn := fmt.Sprintf("%stcp(%s:%s)/%s", credentials, host, port, strings.TrimPrefix(u.Path, "/"))
	if encoded := params.Encode(); encoded != "" {
		dsn += "?" + encoded
	}
	return Target{Engine: EngineMySQL, DriverName: "mysql", DSN: dsn}, nil
}
