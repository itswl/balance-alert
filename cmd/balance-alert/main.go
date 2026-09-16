// balance-alert 监控多个平台的余额或配额，算出还能用几天，快见底或消耗突然放大时发 Webhook。
//
// 默认起 Web 服务与进程内定时任务；带上 -check 之类的开关则跑一次就退出，供命令行排障用。
package main

import (
	"context"
	"flag"
	"fmt"
	"io"
	"io/fs"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	// 把时区数据库编进二进制：定时任务的时刻按 TZ 解释，运行镜像因此不必安装 tzdata，
	// 可以直接跑在 scratch 上。系统装了 tzdata 时优先用系统的。
	_ "time/tzdata"

	"github.com/itswl/balance-alert/internal/app"
	"github.com/itswl/balance-alert/internal/config"
	"github.com/itswl/balance-alert/internal/selfcheck"
	"github.com/itswl/balance-alert/ui"
)

func main() {
	opts := parseFlags()

	// .env 先进环境变量，后面所有配置都只读 os.Environ
	if err := config.LoadEnvFile(".env"); err != nil {
		fmt.Fprintln(os.Stderr, "加载 .env 失败:", err)
		os.Exit(1)
	}
	settings, err := config.Load()
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}

	// 健康检查只发一个 HTTP 请求，不需要数据库、通知这些依赖，在装配之前就返回。
	// 镜像基于 scratch，没有 curl 可用，所以由程序自己承担这件事。
	if opts.healthcheck {
		os.Exit(probe(settings.WebPort))
	}

	log, closeLog, err := newLogger(settings)
	if err != nil {
		fmt.Fprintln(os.Stderr, "初始化日志失败:", err)
		os.Exit(1)
	}
	defer closeLog()

	instance, err := app.New(settings, log, assets(log))
	if err != nil {
		log.Error("启动失败", "error", err)
		os.Exit(1)
	}
	defer instance.Close()

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	os.Exit(run(ctx, instance, opts))
}

type options struct {
	showConfig        bool
	healthcheck       bool
	checkBalance      bool
	checkSubscription bool
	checkEmail        bool
	emailDays         int
	project           string
	importConfig      string
	dryRun            bool
}

func parseFlags() options {
	var opts options
	flag.BoolVar(&opts.showConfig, "show-config", false, "自检配置：显示每项配置来自哪里、缺什么，有问题时退出码非零")
	flag.BoolVar(&opts.healthcheck, "healthcheck", false, "探测本机 /live，供容器健康检查使用")
	flag.BoolVar(&opts.checkBalance, "check", false, "跑一次余额检查后退出")
	flag.BoolVar(&opts.checkSubscription, "check-subscriptions", false, "跑一次订阅检查后退出")
	flag.BoolVar(&opts.checkEmail, "check-email", false, "跑一次邮箱扫描后退出")
	flag.IntVar(&opts.emailDays, "email-days", 1, "邮箱扫描覆盖最近几天")
	flag.StringVar(&opts.project, "project", "", "只检查指定项目")
	flag.StringVar(&opts.importConfig, "import-config", "", "把旧版的 config.json 一次性导入数据库动态配置，导完即可删除该文件")
	flag.BoolVar(&opts.dryRun, "dry-run", false, "测试模式，只查不发告警")
	flag.Parse()
	return opts
}

// run 返回进程退出码。
func run(ctx context.Context, instance *app.App, opts options) int {
	switch {
	case opts.showConfig:
		problems := selfcheck.Run(ctx, instance, os.Stdout)
		if problems > 0 {
			return 1
		}
		return 0

	case opts.importConfig != "":
		if _, err := instance.ImportLegacyConfig(ctx, opts.importConfig, os.Stdout); err != nil {
			fmt.Fprintln(os.Stderr, err)
			return 1
		}
		return 0

	case opts.checkBalance || opts.project != "":
		if _, err := instance.Monitor.Run(ctx, opts.project, opts.dryRun); err != nil {
			instance.Log.Error("余额检查失败", "error", err)
			return 1
		}
		return 0

	case opts.checkSubscription:
		cfg := instance.Resolver.Load(ctx)
		instance.Subs.Check(ctx, cfg.EnabledSubscriptions(), opts.dryRun)
		return 0

	case opts.checkEmail:
		if _, err := instance.ScanMailboxes(ctx, opts.emailDays, opts.dryRun); err != nil {
			instance.Log.Error("邮箱扫描失败", "error", err)
			return 1
		}
		return 0
	}

	return serve(ctx, instance)
}

func serve(ctx context.Context, instance *app.App) int {
	settings := instance.Settings

	instance.StartScheduler(ctx)
	defer instance.StopScheduler()
	instance.ServeMetrics(ctx)

	if settings.EnableWebAlarm {
		instance.Log.Warn("看板刷新会发送真实告警（ENABLE_WEB_ALARM=true）")
	} else {
		instance.Log.Info("看板刷新只查不发告警，真实告警由 alert_check / email_scan 定时任务发送")
	}

	addr := fmt.Sprintf(":%d", settings.WebPort)
	if err := instance.Server.ListenAndServe(ctx, addr); err != nil {
		instance.Log.Error("Web 服务异常退出", "error", err)
		return 1
	}
	instance.Log.Info("服务已关闭")
	return 0
}

// probe 探测本机的存活接口，返回进程退出码。
func probe(port int) int {
	client := &http.Client{Timeout: 5 * time.Second}
	url := fmt.Sprintf("http://127.0.0.1:%d/live", port)

	resp, err := client.Get(url)
	if err != nil {
		fmt.Fprintln(os.Stderr, "健康检查失败:", err)
		return 1
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		fmt.Fprintf(os.Stderr, "健康检查失败: HTTP %d\n", resp.StatusCode)
		return 1
	}
	return 0
}

// assets 取嵌入的前端产物；没构建过就返回 nil，页面会给出提示而不是 500。
func assets(log *slog.Logger) fs.FS {
	dist, err := ui.Assets()
	if err != nil {
		log.Warn("未嵌入前端产物，看板页面不可用", "error", err)
		return nil
	}
	return dist
}

// newLogger 按 LOG_FORMAT / LOG_LEVEL / LOG_FILE 建日志器。
// 写文件时同时输出到标准输出，容器日志和文件都能看到。
func newLogger(settings *config.Settings) (*slog.Logger, func(), error) {
	level := slog.LevelInfo
	switch strings.ToUpper(settings.LogLevel) {
	case "DEBUG":
		level = slog.LevelDebug
	case "WARNING", "WARN":
		level = slog.LevelWarn
	case "ERROR":
		level = slog.LevelError
	}

	closeLog := func() {}
	var output io.Writer = os.Stdout
	if settings.LogFile != "" {
		file, err := os.OpenFile(settings.LogFile, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
		if err != nil {
			return nil, nil, err
		}
		closeLog = func() { _ = file.Close() }
		output = io.MultiWriter(os.Stdout, file)
	}

	var handler slog.Handler
	if strings.EqualFold(settings.LogFormat, "json") {
		handler = slog.NewJSONHandler(output, &slog.HandlerOptions{Level: level})
	} else {
		handler = slog.NewTextHandler(output, &slog.HandlerOptions{Level: level})
	}
	log := slog.New(handler)
	slog.SetDefault(log)
	return log, closeLog, nil
}
