# 架构与约定

## 分层

一条数据从上游到告警要经过：`provider` 查回余额 → `monitor` 判阈值 → `store` 留痕 →
`runway` 从历史算趋势 → `notify` 发出去。`state` 保存看板要展示的那一份，`httpapi` 把它端出去。
`app` 负责把这些装配起来，`cmd` 只管命令行开关与信号。

依赖方向是单向的：`model` 和 `timeutil` 不依赖任何人，`store` 只依赖 `model`，
`notify` 只依赖 `model`。所以这几个包在测试里可以随便构造，不用碰环境变量。

## 约定

- **注释解释为什么**，不复述代码在做什么。包注释说明这个包解决什么问题。
- **可空数值用指针**。`*float64` 序列化成 `null`；用 0 表示"没查到"会让看板把故障显示成余额耗尽。
- **可选能力失败要降级，不要中断**。数据库连不上时退回 `store.Null()`，效果是没有历史、
  不冷却、不留痕，但余额告警照发。这是产品要求：监控工具自己的附加功能不该拖垮主职责。
  想要相反的行为就开 `STRICT_DATABASE_ERRORS`。
- **不引入 Web 框架**。路由用标准库 `net/http` 的 `ServeMux`（Go 1.22 起支持方法与路径模式）。
- **依赖尽量少**。目前只有：Prometheus 客户端、go-imap、fernet、三个数据库驱动。
- 日期、签名、解析这三类必须有表驱动测试，边界条件写进用例名。

## 数据契约

下面这些一旦改动，跑起来不会报错，但会和既有部署的数据对不上——历史曲线断成两截、
告警冷却重新计时、库里的密文解不开。改之前先想清楚已经在跑的实例怎么办。

- `project_id` = `md5("provider:name")`，`subscription_id` = `md5("subscription:name")`。
  它是历史记录与告警冷却的关联键，换算法等于把既有历史全部作废
- 六张表的表名与列名
- 密文格式 `enc:v1:` + Fernet token。`CONFIG_ENCRYPTION_KEY` 本身是合法 Fernet key 就直接用，
  否则取它的 SHA-256 再 urlsafe-base64 当 key
- `DATABASE_URL` 是 `scheme://user:password@host:port/database?params` 形式，
  由 `internal/store` 翻译成各驱动认的 DSN。`scheme` 里 `+` 后面是驱动名，只取前半段。
  注意解析不能用 `net/url`：密码里的 `#` 会被当成片段起点，连接串在那儿断掉
- 浮点数用银行家舍入（`math.RoundToEven`）而不是普通四舍五入。差 0.01 平时无所谓，
  但跑道天数正好压在告警阈值上时会决定发不发告警，同一份数据也不该因为换了实现就显示成别的数字

`internal/store/testdata/legacy.db` 是一个真实写出来的库，`TestReadsLegacyDatabase`
每次跑测试都拿它验证一遍六张表能不能正常读写。

## 时间

- 调度时刻按**进程本地时区**（容器由 `TZ` 决定），跑道按本地日期分天
- 入库时间戳一律 UTC，API 返回 Z 结尾的 ISO 字符串
- 时区数据库由 `time/tzdata` 编进二进制，运行镜像不必安装 tzdata

## 加一个平台

大多数平台是"GET 一次、从 JSON 里取个数"，在 `internal/provider/` 下新建一个文件：

```go
func init() {
	RegisterSpec(Spec{
		Key: "example", Name: "Example", DefaultType: model.TypeBalance,
		URL: "https://api.example.com/v1/balance",
		Extract: func(data map[string]any) (float64, error) {
			value, ok := Num(Dig(data, "data", "balance"))
			if !ok {
				return 0, errors.New("无法从响应中解析 data.balance 字段")
			}
			return value, nil
		},
	})
}
```

需要签名的自己实现 `Provider` 接口后用 `Register` 注册，参考 `volc.go` 与 `aliyun.go`。

## 验证

```bash
go build ./... && go vet ./... && go test -race ./...
gofmt -l .                       # 必须没有输出
npm --prefix ui run typecheck && npm --prefix ui test
```
