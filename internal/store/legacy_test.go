package store

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/itswl/balance-alert/internal/model"
)

// TestReadsLegacyDatabase 证明现在的实现能直接接上旧版建的库。
//
// testdata/legacy.db 是重写前的实现真实写出来的库，六张表都有数据。
// 升级不需要迁移脚本、不需要停机导数据，这条是整个重写的前提。
func TestReadsLegacyDatabase(t *testing.T) {
	// 复制一份再打开：建表语句会写库，不能弄脏 testdata
	source, err := os.ReadFile("testdata/legacy.db")
	if err != nil {
		t.Fatalf("读取旧版数据库失败: %v", err)
	}
	path := filepath.Join(t.TempDir(), "legacy.db")
	if err := os.WriteFile(path, source, 0o644); err != nil {
		t.Fatalf("复制数据库失败: %v", err)
	}

	ctx := context.Background()
	st, err := Open(ctx, Options{DatabaseURL: "sqlite:///" + path})
	if err != nil {
		t.Fatalf("打开旧版数据库失败: %v", err)
	}
	defer st.Close()

	t.Run("项目配置", func(t *testing.T) {
		projects, err := st.ListProjects(ctx)
		if err != nil {
			t.Fatalf("读取失败: %v", err)
		}
		if len(projects) != 2 {
			t.Fatalf("应有 2 个项目，实际 %d 个", len(projects))
		}
		volc := findByName(projects, func(p model.Project) string { return p.Name }, "火山-主账号")
		if volc == nil {
			t.Fatal("没读到「火山-主账号」，中文字段可能坏了")
		}
		if volc.Provider != "volc" || volc.APIKey != "AK:SK" || volc.Threshold != 7000 {
			t.Errorf("项目字段不对: %+v", *volc)
		}
		if volc.OwnerProject == nil || *volc.OwnerProject != "云服务" {
			t.Errorf("分组标签不对: %v", volc.OwnerProject)
		}
		if !volc.Enabled {
			t.Error("enabled 应为 true")
		}
		// 停用状态也要如实读出来，否则停掉的账户会被重新拉起来查
		deepseek := findByName(projects, func(p model.Project) string { return p.Name }, "deepseek")
		if deepseek == nil || deepseek.Enabled {
			t.Errorf("deepseek 应是停用状态，实际 %+v", deepseek)
		}
	})

	t.Run("订阅配置", func(t *testing.T) {
		subs, err := st.ListSubscriptions(ctx)
		if err != nil {
			t.Fatalf("读取失败: %v", err)
		}
		if len(subs) != 1 {
			t.Fatalf("应有 1 条订阅，实际 %d 条", len(subs))
		}
		s := subs[0]
		// 年付的续费日在旧库里存成 MMDD 整数，新版必须照这个理解
		if s.Name != "域名续费" || s.CycleType != "yearly" || s.RenewalDay != 315 {
			t.Errorf("订阅字段不对: %+v", s)
		}
		if s.Amount != 88 || s.AlertDaysBefore != 3 {
			t.Errorf("金额或提前天数不对: %+v", s)
		}
	})

	t.Run("邮箱配置", func(t *testing.T) {
		boxes, err := st.ListMailboxes(ctx)
		if err != nil {
			t.Fatalf("读取失败: %v", err)
		}
		if len(boxes) != 1 {
			t.Fatalf("应有 1 个邮箱，实际 %d 个", len(boxes))
		}
		m := boxes[0]
		if m.Name != "工作邮箱" || m.Host != "imap.example.com" || m.Port != 993 || !m.UseSSL {
			t.Errorf("邮箱字段不对: %+v", m)
		}
		if m.Password != "pw" {
			t.Errorf("密码应原样读出（旧库未加密），实际 %q", m.Password)
		}
	})

	t.Run("余额历史与跑道输入", func(t *testing.T) {
		series, err := st.BalanceSeries(ctx, 7)
		if err != nil {
			t.Fatalf("读取失败: %v", err)
		}
		if len(series) != 5 {
			t.Fatalf("应有 5 条快照，实际 %d 条", len(series))
		}
		// 必须按时间升序，跑道分析依赖这个顺序
		for i := 1; i < len(series); i++ {
			if series[i].Timestamp < series[i-1].Timestamp {
				t.Fatal("余额快照没有按时间升序返回")
			}
		}
		if series[0].Balance != 9000 || series[4].Balance != 6900 {
			t.Errorf("余额数值不对: 首 %v 末 %v", series[0].Balance, series[4].Balance)
		}
		if series[0].ProjectName != "火山-主账号" || series[0].Provider != "volc" {
			t.Errorf("账户信息不对: %+v", series[0])
		}
		if series[0].Timestamp <= 0 {
			t.Error("时间戳没读出来，跑道分析会算不出跨度")
		}
	})

	t.Run("余额趋势", func(t *testing.T) {
		series, _ := st.BalanceSeries(ctx, 7)
		trend, err := st.BalanceTrend(ctx, series[0].ProjectID, 30)
		if err != nil {
			t.Fatalf("读取失败: %v", err)
		}
		if trend == nil {
			t.Fatal("有数据却返回了空趋势")
		}
		if trend.DataPoints != 5 || trend.MinBalance != 6900 || trend.MaxBalance != 9000 {
			t.Errorf("趋势统计不对: %+v", *trend)
		}
		if trend.Change == nil || *trend.Change != -2100 {
			t.Errorf("变化量应为 -2100，实际 %v", trend.Change)
		}
	})

	t.Run("没有数据的项目返回空趋势", func(t *testing.T) {
		trend, err := st.BalanceTrend(ctx, "不存在的项目", 30)
		if err != nil {
			t.Fatalf("读取失败: %v", err)
		}
		if trend != nil {
			t.Error("没有数据时应返回 nil，让接口回 404")
		}
	})

	t.Run("告警历史与冷却", func(t *testing.T) {
		alerts, err := st.RecentAlerts(ctx, AlertQuery{Days: 7, Limit: 50})
		if err != nil {
			t.Fatalf("读取失败: %v", err)
		}
		if len(alerts) != 1 {
			t.Fatalf("应有 1 条告警，实际 %d 条", len(alerts))
		}
		if alerts[0].AlertType != "low_balance" || alerts[0].Status != "sent" {
			t.Errorf("告警字段不对: %+v", alerts[0])
		}

		// 兼容性 fixture 的时间是固定的；使用足够宽的窗口，避免测试结果随日历漂移。
		series, _ := st.BalanceSeries(ctx, 7)
		cooling, err := st.HasRecentAlert(ctx, series[0].ProjectID, "low_balance", 365*24*time.Hour)
		if err != nil {
			t.Fatalf("查询冷却失败: %v", err)
		}
		if !cooling {
			t.Error("旧库里的告警记录没有让冷却生效")
		}
	})

	t.Run("邮件告警历史", func(t *testing.T) {
		rows, err := st.EmailAlerts(ctx, EmailAlertQuery{Days: 30, Limit: 100})
		if err != nil {
			t.Fatalf("读取失败: %v", err)
		}
		if len(rows) != 1 {
			t.Fatalf("应有 1 条，实际 %d 条", len(rows))
		}
		r := rows[0]
		if r.Mailbox != "工作邮箱" || r.Subject != "【阿里云】余额不足提醒" {
			t.Errorf("中文字段读坏了: %+v", r)
		}
		if r.ServiceName == nil || *r.ServiceName != "阿里云" {
			t.Errorf("服务名不对: %v", r.ServiceName)
		}
		if r.Amount == nil || *r.Amount != 12.5 {
			t.Errorf("金额不对: %v", r.Amount)
		}
		if !r.AlertSent {
			t.Error("alert_sent 应为 true")
		}

		// 去重要能认出旧库里已经通知过的邮件
		seen, err := st.HasRecentEmailAlert(ctx, "工作邮箱", "noreply@aliyun.com",
			"【阿里云】余额不足提醒", "Mon, 01 Sep 2026 10:00:00 +0800", 30)
		if err != nil {
			t.Fatalf("查询去重失败: %v", err)
		}
		if !seen {
			t.Error("旧库里的邮件没有被认作已通知过")
		}
	})

	t.Run("能继续往旧库里写", func(t *testing.T) {
		err := st.UpsertProject(ctx, model.Project{
			Name: "新项目", Provider: "glm", APIKey: "id.secret",
			Threshold: 10, Type: model.TypeQuota, Enabled: true,
		})
		if err != nil {
			t.Fatalf("写入失败: %v", err)
		}
		projects, _ := st.ListProjects(ctx)
		if len(projects) != 3 {
			t.Errorf("写入后应有 3 个项目，实际 %d 个", len(projects))
		}
	})
}

func findByName[T any](items []T, name func(T) string, want string) *T {
	for i := range items {
		if name(items[i]) == want {
			return &items[i]
		}
	}
	return nil
}
