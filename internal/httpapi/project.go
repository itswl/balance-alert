package httpapi

import (
	"net/http"
	"strings"

	"github.com/itswl/balance-alert/internal/model"
	"github.com/itswl/balance-alert/internal/provider"
	"github.com/itswl/balance-alert/internal/store"
)

func trimSpace(s string) string { return strings.TrimSpace(s) }

// requireDynamicConfig 拦住所有写操作。读接口任何时候都可用，
// 这样没开数据库的核心版页面上也能看到项目清单，只是改不了。
func (s *Server) requireDynamicConfig(w http.ResponseWriter, what string) bool {
	if s.Settings.EnableDynamicConfig {
		return true
	}
	fail(w, http.StatusServiceUnavailable, "修改"+what+"需要数据库动态配置，请设置 ENABLE_DYNAMIC_CONFIG=true")
	return false
}

func (s *Server) handleProviders(w http.ResponseWriter, r *http.Request) {
	etagJSON(w, r, map[string]any{"status": "success", "providers": provider.All()})
}

// maskedProject 是项目配置的对外形状，密钥永远打码。
type maskedProject struct {
	Name         string  `json:"name"`
	Provider     string  `json:"provider"`
	APIKey       string  `json:"api_key"`
	Threshold    float64 `json:"threshold"`
	Type         string  `json:"type"`
	OwnerProject *string `json:"owner_project"`
	Enabled      bool    `json:"enabled"`
	FromEnv      bool    `json:"from_env"`
}

func (s *Server) handleListProjects(w http.ResponseWriter, r *http.Request) {
	cfg := s.Resolver.Load(r.Context())
	projects := make([]maskedProject, 0, len(cfg.Projects))
	for _, p := range cfg.Projects {
		projects = append(projects, maskedProject{
			Name: p.Name, Provider: p.Provider, APIKey: maskSecret(p.APIKey, 4, 4),
			Threshold: p.Threshold, Type: p.Type, OwnerProject: p.OwnerProject,
			Enabled: p.Enabled, FromEnv: p.FromEnv,
		})
	}
	etagJSON(w, r, map[string]any{"status": "success", "projects": projects})
}

type projectRequest struct {
	Name         string   `json:"name"`
	Provider     *string  `json:"provider"`
	APIKey       *string  `json:"api_key"`
	Threshold    *float64 `json:"threshold"`
	Type         *string  `json:"type"`
	OwnerProject *string  `json:"owner_project"`
	Enabled      *bool    `json:"enabled"`
}

// handleSaveProject 新增或更新项目。name 是唯一键；更新时只改传了的字段，
// 密钥留空表示不变——页面上看到的是打码后的值，原样提交回来不能把密钥覆盖成星号。
func (s *Server) handleSaveProject(w http.ResponseWriter, r *http.Request) {
	if !s.requireDynamicConfig(w, "项目配置") {
		return
	}
	var body projectRequest
	if !decodeJSON(w, r, &body) {
		return
	}
	body.Name = trimSpace(body.Name)
	if body.Name == "" {
		failValidation(w, []string{"name: 不能为空"})
		return
	}

	cfg := s.Resolver.Load(r.Context())
	existing := findProject(cfg.Projects, body.Name)
	isNew := existing == nil

	target := model.Project{Name: body.Name, Enabled: true}
	if existing != nil {
		target = *existing
	}
	applyProjectPatch(&target, body)

	if isNew {
		var missing []string
		if target.Provider == "" {
			missing = append(missing, "provider")
		}
		if target.APIKey == "" {
			missing = append(missing, "api_key")
		}
		if len(missing) > 0 {
			fail(w, http.StatusBadRequest, "新增项目缺少必要参数: "+strings.Join(missing, ", "))
			return
		}
	}
	if _, known := provider.Lookup(target.Provider); !known {
		fail(w, http.StatusBadRequest, "未知的服务商: "+target.Provider+"，支持: "+strings.Join(provider.Keys(), ", "))
		return
	}
	model.NormalizeProject(&target)
	// 环境变量发现的项目在这里改动，等于把它固化进数据库，之后以数据库为准
	target.FromEnv = false

	if err := s.Store.UpsertProject(r.Context(), target); err != nil {
		s.log().Error("保存项目配置失败", "project", body.Name, "error", err)
		fail(w, http.StatusInternalServerError, "保存失败")
		return
	}
	s.log().Info("[AUDIT] 保存项目", "project", body.Name, "new", isNew)

	s.refreshOne(r, target.Name)
	action := "更新"
	if isNew {
		action = "添加"
	}
	ok(w, map[string]any{"message": "项目 [" + body.Name + "] 已" + action})
}

func applyProjectPatch(target *model.Project, body projectRequest) {
	if body.Provider != nil && *body.Provider != "" {
		target.Provider = strings.ToLower(trimSpace(*body.Provider))
	}
	if body.APIKey != nil && trimSpace(*body.APIKey) != "" {
		target.APIKey = trimSpace(*body.APIKey)
	}
	if body.Threshold != nil {
		target.Threshold = *body.Threshold
	}
	if body.Type != nil && *body.Type != "" {
		target.Type = *body.Type
	}
	if body.OwnerProject != nil {
		target.OwnerProject = model.OwnerProjectOf(*body.OwnerProject)
	}
	if body.Enabled != nil {
		target.Enabled = *body.Enabled
	}
}

type nameRequest struct {
	Name string `json:"name"`
}

func (s *Server) handleDeleteProject(w http.ResponseWriter, r *http.Request) {
	if !s.requireDynamicConfig(w, "项目配置") {
		return
	}
	var body nameRequest
	if !decodeJSON(w, r, &body) {
		return
	}
	if body.Name == "" {
		fail(w, http.StatusBadRequest, "缺少必要参数: name")
		return
	}

	cfg := s.Resolver.Load(r.Context())
	existing := findProject(cfg.Projects, body.Name)
	if existing == nil {
		fail(w, http.StatusNotFound, "未找到项目: "+body.Name)
		return
	}
	// 环境变量发现的项目删不掉：数据库里本来就没有它，删了下次启动还会回来
	if existing.FromEnv {
		fail(w, http.StatusBadRequest, "项目 ["+body.Name+"] 来自环境变量自动发现，请移除对应的 "+
			strings.ToUpper(existing.Provider)+"_API_KEY 后重启")
		return
	}

	if err := s.Store.DeleteProject(r.Context(), body.Name); err != nil {
		s.log().Error("删除项目配置失败", "project", body.Name, "error", err)
		fail(w, http.StatusInternalServerError, "删除失败")
		return
	}
	s.State.RemoveBalanceProject(body.Name)
	if s.OnBalanceUpdated != nil {
		s.OnBalanceUpdated(s.State.Balance().Projects)
	}
	s.log().Info("[AUDIT] 删除项目", "project", body.Name)
	ok(w, map[string]any{"message": "项目 [" + body.Name + "] 已删除"})
}

type thresholdRequest struct {
	ProjectName  string   `json:"project_name"`
	NewThreshold *float64 `json:"new_threshold"`
}

// handleUpdateThreshold 是只改阈值的快捷入口，保留给旧的调用方。
func (s *Server) handleUpdateThreshold(w http.ResponseWriter, r *http.Request) {
	if !s.requireDynamicConfig(w, "项目配置") {
		return
	}
	var body thresholdRequest
	if !decodeJSON(w, r, &body) {
		return
	}
	if body.ProjectName == "" || body.NewThreshold == nil {
		fail(w, http.StatusBadRequest, "缺少必要参数: project_name, new_threshold")
		return
	}
	if *body.NewThreshold < 0 {
		fail(w, http.StatusBadRequest, "阈值不能为负数")
		return
	}

	cfg := s.Resolver.Load(r.Context())
	target := findProject(cfg.Projects, body.ProjectName)
	if target == nil {
		fail(w, http.StatusNotFound, "未找到项目: "+body.ProjectName)
		return
	}
	updated := *target
	updated.Threshold = *body.NewThreshold
	updated.FromEnv = false

	if err := s.Store.UpsertProject(r.Context(), updated); err != nil {
		s.log().Error("更新阈值失败", "project", body.ProjectName, "error", err)
		fail(w, http.StatusInternalServerError, "保存失败")
		return
	}
	s.log().Info("[AUDIT] 更新项目阈值", "project", body.ProjectName,
		"old", target.Threshold, "new", *body.NewThreshold)

	s.refreshOne(r, body.ProjectName)
	ok(w, map[string]any{"message": "项目 [" + body.ProjectName + "] 阈值已更新"})
}

// refreshOne 只重查这一个项目并合并进看板，不把所有上游都打一遍。
func (s *Server) refreshOne(r *http.Request, name string) {
	outcome, err := s.Monitor.Run(r.Context(), name, !s.Settings.EnableWebAlarm)
	if err != nil {
		s.log().Warn("刷新项目失败", "project", name, "error", err)
		return
	}
	s.State.MergeBalance(outcome.Results)
	if s.OnBalanceUpdated != nil {
		s.OnBalanceUpdated(s.State.Balance().Projects)
	}
}

func findProject(projects []model.Project, name string) *model.Project {
	for i := range projects {
		if projects[i].Name == name {
			return &projects[i]
		}
	}
	return nil
}

// storeWriteStatus 把"数据库没开"翻译成 503，其余写失败算 500。
func storeWriteStatus(err error) int {
	if err == store.ErrDisabled {
		return http.StatusServiceUnavailable
	}
	return http.StatusInternalServerError
}
