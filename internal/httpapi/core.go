package httpapi

import (
	"math"
	"net/http"
	"time"
)

// stalenessMultiplier 余额数据超过多少个刷新周期没更新就算过期。
// 给三个周期的余量：偶尔一次刷新失败不该让就绪探针把容器摘掉。
const stalenessMultiplier = 3

type liveBody struct {
	Status        string `json:"status"`
	UptimeSeconds int    `json:"uptime_seconds"`
	Version       string `json:"version"`
}

func (s *Server) handleLive(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, liveBody{
		Status:        "alive",
		UptimeSeconds: int(s.State.UptimeSeconds()),
		Version:       s.Settings.AppVersion,
	})
}

type healthBody struct {
	Status        string   `json:"status"`
	HasData       bool     `json:"has_data"`
	IsStale       bool     `json:"is_stale"`
	JobsHealthy   bool     `json:"jobs_healthy"`
	FailedJobs    []string `json:"failed_jobs"`
	LastUpdate    *string  `json:"last_update"`
	UptimeSeconds int      `json:"uptime_seconds"`
	Version       string   `json:"version"`
}

// handleHealth 是就绪探针：有数据、数据没过期、定时任务上次都成功才 200。
func (s *Server) handleHealth(w http.ResponseWriter, _ *http.Request) {
	balance := s.State.Balance()
	jobs := s.State.Jobs()
	failed := s.State.FailedJobs()
	if failed == nil {
		failed = []string{}
	}

	hasData := len(balance.Projects) > 0
	isStale := s.isStale(balance.LastUpdate)
	healthy := hasData && !isStale && jobs.Healthy

	status := http.StatusOK
	label := "healthy"
	if !healthy {
		status, label = http.StatusServiceUnavailable, "degraded"
	}
	writeJSON(w, status, healthBody{
		Status: label, HasData: hasData, IsStale: isStale,
		JobsHealthy: jobs.Healthy, FailedJobs: failed,
		LastUpdate:    balance.LastUpdate,
		UptimeSeconds: int(s.State.UptimeSeconds()),
		Version:       s.Settings.AppVersion,
	})
}

func (s *Server) isStale(lastUpdate *string) bool {
	if lastUpdate == nil {
		return false
	}
	updatedAt, err := time.Parse("2006-01-02T15:04:05.999999Z", *lastUpdate)
	if err != nil {
		return false
	}
	limit := time.Duration(s.Settings.RefreshInterval()*stalenessMultiplier) * time.Second
	return time.Since(updatedAt) > limit
}

type featuresBody struct {
	Status   string         `json:"status"`
	Features featureToggles `json:"features"`
}

type featureToggles struct {
	Subscriptions bool `json:"subscriptions"`
	DynamicConfig bool `json:"dynamic_config"`
	History       bool `json:"history"`
}

// handleFeatures 告诉前端哪些高级入口该显示。
func (s *Server) handleFeatures(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, featuresBody{
		Status: "success",
		Features: featureToggles{
			Subscriptions: s.Settings.EnableSubscriptions,
			DynamicConfig: s.Settings.EnableDynamicConfig,
			History:       s.Settings.EnableHistoryAPI,
		},
	})
}

func (s *Server) handleCredits(w http.ResponseWriter, r *http.Request) {
	balance := s.State.Balance()
	if len(balance.Projects) == 0 {
		fail(w, http.StatusServiceUnavailable, "余额数据未初始化，请稍后重试")
		return
	}
	etagJSON(w, r, balance)
}

func (s *Server) handleSubscriptions(w http.ResponseWriter, r *http.Request) {
	etagJSON(w, r, s.State.Subscriptions())
}

func (s *Server) handleJobs(w http.ResponseWriter, r *http.Request) {
	etagJSON(w, r, s.State.Jobs())
}

type refreshRequest struct {
	ProjectName *string `json:"project_name"`
}

// handleRefresh 立即检查余额；带 project_name 时只刷新那一个并合并进现有状态。
func (s *Server) handleRefresh(w http.ResponseWriter, r *http.Request) {
	projectName := ""
	if r.Method == http.MethodPost && r.ContentLength > 0 {
		var body refreshRequest
		if !decodeJSON(w, r, &body) {
			return
		}
		if body.ProjectName != nil {
			projectName = trimSpace(*body.ProjectName)
		}
	}

	if busy := s.refreshGuard.acquire(); busy != "" {
		fail(w, http.StatusTooManyRequests, "刷新"+busy)
		return
	}
	defer s.refreshGuard.release()

	started := time.Now()
	// 页面触发的刷新默认不发真实告警，除非显式打开 ENABLE_WEB_ALARM
	dryRun := !s.Settings.EnableWebAlarm

	outcome, err := s.Monitor.Run(r.Context(), projectName, dryRun)
	if err != nil {
		fail(w, http.StatusInternalServerError, "刷新失败: "+err.Error())
		return
	}

	if projectName != "" {
		s.State.MergeBalance(outcome.Results)
	} else {
		s.State.SetBalance(outcome.Results)
	}
	if s.OnBalanceUpdated != nil {
		s.OnBalanceUpdated(s.State.Balance().Projects)
	}

	message := "刷新完成"
	if projectName != "" {
		message += "（项目: " + projectName + "）"
	}
	ok(w, map[string]any{
		"message":                message,
		"refreshed_count":        len(outcome.Results),
		"execution_time_seconds": round2(time.Since(started).Seconds()),
		"dry_run":                dryRun,
	})
}

// round2 保留两位小数，用银行家舍入，与项目里其它地方的取整口径统一。
func round2(value float64) float64 {
	return math.RoundToEven(value*100) / 100
}
