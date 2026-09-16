package store

import (
	"context"
	"database/sql"
	"embed"
	"fmt"
	"strings"
)

// 改了 schema/*.sql 或 queries/*.sql 之后要重新生成 internal/store/sqlc 下的代码。
// sqlc 版本由 go.mod 的 tool 指令钉住，本机与 CI 生成的结果一致。
//go:generate go tool sqlc generate -f ../../sqlc.yaml

//go:embed schema/*.sql
var schemaFS embed.FS

// createTables 启动时建表，与 Python 版 init_database() 的 create_all 行为一致：
// 全是 CREATE ... IF NOT EXISTS，接上现有生产库时是空操作。
func createTables(ctx context.Context, db *sql.DB, engine Engine) error {
	raw, err := schemaFS.ReadFile("schema/" + string(engine) + ".sql")
	if err != nil {
		return fmt.Errorf("找不到 %s 的建表 SQL：%w", engine, err)
	}
	for _, stmt := range splitStatements(string(raw)) {
		if _, err := db.ExecContext(ctx, stmt); err != nil {
			return fmt.Errorf("建表失败（%.60s...）：%w", stmt, err)
		}
	}
	return nil
}

// splitStatements 把建表脚本拆成一条条语句。
//
// 必须逐条执行：MySQL 驱动默认不开 multiStatements，一次塞多条会被拒。
// 建表 SQL 里没有带分号的字符串字面量，所以按分号切就够了，不需要真的做词法分析。
func splitStatements(script string) []string {
	var lines []string
	for _, line := range strings.Split(script, "\n") {
		if trimmed := strings.TrimSpace(line); strings.HasPrefix(trimmed, "--") {
			continue // 注释里有中文，留着会被当成语句的一部分送进驱动
		}
		lines = append(lines, line)
	}

	var out []string
	for _, stmt := range strings.Split(strings.Join(lines, "\n"), ";") {
		if stmt = strings.TrimSpace(stmt); stmt != "" {
			out = append(out, stmt)
		}
	}
	return out
}
