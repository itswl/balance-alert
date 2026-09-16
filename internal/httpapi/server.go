package httpapi

import (
	"context"
	"crypto/subtle"
	"io/fs"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/itswl/balance-alert/internal/config"
	"github.com/itswl/balance-alert/internal/mailscan"
	"github.com/itswl/balance-alert/internal/model"
	"github.com/itswl/balance-alert/internal/monitor"
	"github.com/itswl/balance-alert/internal/state"
	"github.com/itswl/balance-alert/internal/store"
	"github.com/itswl/balance-alert/internal/subscription"
)

// Server 持有 HTTP 层的全部依赖。
type Server struct {
	Settings *config.Settings
	Resolver *config.Resolver
	Store    store.Store
	State    *state.Manager
	Monitor  *monitor.Monitor
	Subs     *subscription.Checker
	Scanner  *mailscan.Scanner
	Log      *slog.Logger

	// Assets 是打包好的前端产物，由 cmd 层用 embed.FS 传进来。
	Assets fs.FS

	// OnBalanceUpdated 等回调让指标跟着页面操作一起更新，
	// 否则页面上改完配置，Grafana 要等到下一次定时任务才看得到。
	OnBalanceUpdated      func([]model.CheckResult)
	OnSubscriptionUpdated func([]model.SubscriptionResult)
	OnEmailScanned        func(model.ScanResult)

	refreshGuard cooldown
	scanGuard    cooldown
}

// 页面上手动触发的重操作，完成后冷却这么多秒。
const guardCooldownSeconds = 30

// Handler 装配路由。
func (s *Server) Handler() http.Handler {
	s.refreshGuard.seconds = guardCooldownSeconds
	s.scanGuard.seconds = guardCooldownSeconds

	mux := http.NewServeMux()

	// 探针：/live 只证明进程活着，/health 才检查数据与任务
	mux.HandleFunc("GET /live", s.handleLive)
	mux.HandleFunc("GET /health", s.handleHealth)

	// 核心读接口
	mux.HandleFunc("GET /api/features", s.handleFeatures)
	mux.HandleFunc("GET /api/credits", s.handleCredits)
	mux.HandleFunc("GET /api/subscriptions", s.handleSubscriptions)
	mux.HandleFunc("GET /api/jobs", s.handleJobs)
	mux.HandleFunc("GET /api/refresh", s.handleRefresh)
	mux.HandleFunc("POST /api/refresh", s.handleRefresh)

	// 项目配置
	mux.HandleFunc("GET /api/providers", s.handleProviders)
	mux.HandleFunc("GET /api/config/projects", s.handleListProjects)
	mux.HandleFunc("POST /api/config/project", s.handleSaveProject)
	mux.HandleFunc("POST /api/config/project/delete", s.handleDeleteProject)
	mux.HandleFunc("POST /api/config/threshold", s.handleUpdateThreshold)

	// 订阅
	mux.HandleFunc("GET /api/config/subscriptions", s.handleListSubscriptions)
	mux.HandleFunc("POST /api/config/subscription", s.handleUpdateSubscription)
	mux.HandleFunc("POST /api/subscription/add", s.handleAddSubscription)
	mux.HandleFunc("POST /api/subscription/delete", s.handleDeleteSubscription)
	mux.HandleFunc("DELETE /api/subscription/delete", s.handleDeleteSubscription)
	mux.HandleFunc("POST /api/subscription/mark_renewed", s.handleMarkRenewed)
	mux.HandleFunc("POST /api/subscription/clear_renewed", s.handleClearRenewed)

	// 邮箱
	mux.HandleFunc("GET /api/config/emails", s.handleListMailboxes)
	mux.HandleFunc("POST /api/config/email", s.handleSaveMailbox)
	mux.HandleFunc("POST /api/config/email/delete", s.handleDeleteMailbox)
	mux.HandleFunc("GET /api/email/scan", s.handleEmailScanState)
	mux.HandleFunc("POST /api/email/scan", s.handleEmailScan)

	// 历史查询：未开 ENABLE_HISTORY_API 时整组不注册，访问即 404，与旧版一致
	if s.Settings.EnableHistoryAPI {
		mux.HandleFunc("GET /api/history/balance", s.handleBalanceHistory)
		mux.HandleFunc("GET /api/history/trend/{projectID}", s.handleBalanceTrend)
		mux.HandleFunc("GET /api/history/alerts", s.handleAlertHistory)
		mux.HandleFunc("GET /api/history/stats", s.handleAlertStats)
		mux.HandleFunc("GET /api/history/email-alerts", s.handleEmailAlertHistory)
	}

	// 看板静态资源，放最后兜底
	mux.Handle("GET /", s.assetHandler())

	return s.withCORS(s.withAPIKey(s.withRecovery(mux)))
}

// withAPIKey 给所有 /api/ 路径加访问控制。
// 没配 WEB_API_KEY 时一律 503：这比默认放开安全得多，密钥都在这后面。
func (s *Server) withAPIKey(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.HasPrefix(r.URL.Path, "/api/") || r.Method == http.MethodOptions {
			next.ServeHTTP(w, r)
			return
		}
		expected := s.Settings.WebAPIKey
		if expected == "" {
			fail(w, http.StatusServiceUnavailable, "API Key 未配置，请设置 WEB_API_KEY")
			return
		}
		token := extractAPIKey(r)
		if token == "" || subtle.ConstantTimeCompare([]byte(token), []byte(expected)) != 1 {
			fail(w, http.StatusUnauthorized, "API Key 无效或未提供")
			return
		}
		next.ServeHTTP(w, r)
	})
}

func extractAPIKey(r *http.Request) string {
	if token := strings.TrimSpace(r.Header.Get("X-API-Key")); token != "" {
		return token
	}
	auth := strings.TrimSpace(r.Header.Get("Authorization"))
	if len(auth) > 7 && strings.EqualFold(auth[:7], "bearer ") {
		return strings.TrimSpace(auth[7:])
	}
	return ""
}

func (s *Server) withCORS(next http.Handler) http.Handler {
	if !s.Settings.WebEnableCORS {
		return next
	}
	allowed := s.Settings.CORSOriginList()
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		origin := r.Header.Get("Origin")
		for _, candidate := range allowed {
			if candidate == origin || candidate == "*" {
				w.Header().Set("Access-Control-Allow-Origin", origin)
				w.Header().Set("Access-Control-Allow-Headers", "Content-Type, X-API-Key, Authorization, If-None-Match")
				w.Header().Set("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
				break
			}
		}
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

// withRecovery 兜住处理器里的 panic：一个坏请求不该带走整个进程。
func (s *Server) withRecovery(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer func() {
			if recovered := recover(); recovered != nil {
				s.log().Error("请求处理 panic", "path", r.URL.Path, "panic", recovered)
				fail(w, http.StatusInternalServerError, "服务器内部错误")
			}
		}()
		next.ServeHTTP(w, r)
	})
}

// assetHandler 提供打包好的前端；没有嵌入产物时给一句提示，方便开发时定位。
func (s *Server) assetHandler() http.Handler {
	if s.Assets == nil {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			http.Error(w, "前端产物未嵌入，请先执行 npm --prefix ui run build 再编译", http.StatusNotFound)
		})
	}
	files := http.FileServer(http.FS(s.Assets))
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// 单页应用：非静态资源路径一律回 index.html，前端自己按 hash 切视图
		if path := strings.TrimPrefix(r.URL.Path, "/"); path != "" {
			if _, err := fs.Stat(s.Assets, path); err != nil {
				r = r.Clone(r.Context())
				r.URL.Path = "/"
			}
		}
		files.ServeHTTP(w, r)
	})
}

func (s *Server) log() *slog.Logger {
	if s.Log != nil {
		return s.Log
	}
	return slog.Default()
}

// ListenAndServe 起服务并在 ctx 取消时优雅关闭。
func (s *Server) ListenAndServe(ctx context.Context, addr string) error {
	server := &http.Server{
		Addr:              addr,
		Handler:           s.Handler(),
		ReadHeaderTimeout: 10 * time.Second,
		IdleTimeout:       120 * time.Second,
	}
	go func() {
		<-ctx.Done()
		// 收到停止信号后先继续服务一会儿：K8s 把 Pod 从 endpoints 摘掉和发 SIGTERM 是
		// 并行的，立刻关会让最后几个请求打空。容器外没有 shell 可以 sleep，只能自己等。
		if delay := s.Settings.ShutdownDelaySeconds; delay > 0 {
			s.log().Info("收到停止信号，先继续服务再关闭", "delay_seconds", delay)
			time.Sleep(time.Duration(delay) * time.Second)
		}
		s.log().Info("正在关闭 Web 服务")
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		_ = server.Shutdown(shutdownCtx)
	}()

	s.log().Info("Web 服务已启动", "addr", addr)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		return err
	}
	return nil
}
