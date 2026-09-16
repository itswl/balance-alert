// Package scheduler 是进程内的定时任务调度器，替代容器里的 cron。
//
// 为什么不用 cron：指标要在进程内累计。任务如果跑在另一个进程里，
// Prometheus 抓到的永远是一个没干过活的进程。
//
// 两类触发方式：固定间隔（看板刷新）和每天固定时刻（告警检查、邮箱扫描、周报）。
// 所有任务在同一个 goroutine 里顺序执行、互不并发；单个任务出错只记失败，不影响其它任务。
package scheduler

import (
	"context"
	"fmt"
	"log/slog"
	"strings"
	"sync"
	"time"

	"github.com/itswl/balance-alert/internal/timeutil"
)

// Task 一个定时任务。Interval 与 DailyTimes 二选一，都不填表示关闭。
type Task struct {
	Name        string
	Description string
	// Run 返回的 detail 会随运行记录一起交给 OnResult，用于 /api/jobs 展示。
	Run        func(ctx context.Context) (any, error)
	Interval   time.Duration
	DailyTimes []timeutil.ClockTime
	Weekdays   map[int]bool // 空=每天；1=周一 … 7=周日
	RunAtStart bool

	nextRun time.Time
}

// Enabled 表示这个任务真的会被触发。
func (t *Task) Enabled() bool { return t.Interval > 0 || len(t.DailyTimes) > 0 }

// ScheduleText 是给人看的触发说明。
func (t *Task) ScheduleText() string {
	if t.Interval > 0 {
		return fmt.Sprintf("每 %d 秒", int(t.Interval.Seconds()))
	}
	return timeutil.Describe(t.DailyTimes, t.Weekdays)
}

// NextRun 是下一次触发时刻，零值表示不会再触发。
func (t *Task) NextRun() time.Time { return t.nextRun }

func (t *Task) initialNextRun(now time.Time) time.Time {
	if t.Interval > 0 {
		if t.RunAtStart {
			return now
		}
		return now.Add(t.Interval)
	}
	next, _ := timeutil.NextOccurrence(now, t.DailyTimes, t.Weekdays)
	return next
}

func (t *Task) followingRun(now time.Time) time.Time {
	if t.Interval > 0 {
		return now.Add(t.Interval)
	}
	next, _ := timeutil.NextOccurrence(now, t.DailyTimes, t.Weekdays)
	return next
}

// Result 是一次任务运行的结果。
type Result struct {
	Name      string
	Success   bool
	StartedAt time.Time
	Duration  time.Duration
	Err       error
	Detail    any
	NextRun   time.Time
}

// Scheduler 顺序执行到点的任务。
type Scheduler struct {
	tasks    []*Task
	onResult func(Result)
	log      *slog.Logger
	maxWait  time.Duration

	runMu sync.Mutex // 手动触发与后台循环不并发
	done  chan struct{}
	stop  chan struct{}
	once  sync.Once
}

// New 创建调度器。onResult 可空；它用来把运行记录交给状态管理器与指标，
// 调度器本身不依赖那两个包。
func New(tasks []*Task, onResult func(Result), log *slog.Logger) *Scheduler {
	if log == nil {
		log = slog.Default()
	}
	now := time.Now()
	for _, t := range tasks {
		if t.Enabled() {
			t.nextRun = t.initialNextRun(now)
		}
	}
	return &Scheduler{
		tasks:    tasks,
		onResult: onResult,
		log:      log,
		maxWait:  time.Minute, // 上限一分钟：时钟跳变也能及时反应
		done:     make(chan struct{}),
		stop:     make(chan struct{}),
	}
}

// Tasks 返回全部任务，供启动时登记静态信息。
func (s *Scheduler) Tasks() []*Task { return s.tasks }

// Start 起一个后台 goroutine 跑调度循环。
func (s *Scheduler) Start(ctx context.Context) {
	descriptions := make([]string, 0, len(s.tasks))
	for _, t := range s.tasks {
		descriptions = append(descriptions, t.Name+"="+t.ScheduleText())
	}
	s.log.Info("定时任务调度器已启动", "tasks", strings.Join(descriptions, ", "))

	go func() {
		defer close(s.done)
		for {
			s.RunPending(ctx, time.Now())
			select {
			case <-ctx.Done():
				s.log.Info("定时任务调度器已停止")
				return
			case <-s.stop:
				s.log.Info("定时任务调度器已停止")
				return
			case <-time.After(s.sleepFor(time.Now())):
			}
		}
	}()
}

// Stop 停掉调度循环，最多等 timeout。
func (s *Scheduler) Stop(timeout time.Duration) {
	s.once.Do(func() { close(s.stop) })
	select {
	case <-s.done:
	case <-time.After(timeout):
	}
}

// sleepFor 是到下一个任务还有多久，钳制在 [0.1s, maxWait]。
func (s *Scheduler) sleepFor(now time.Time) time.Duration {
	wait := s.maxWait
	for _, t := range s.tasks {
		if !t.Enabled() || t.nextRun.IsZero() {
			continue
		}
		if d := t.nextRun.Sub(now); d < wait {
			wait = d
		}
	}
	return max(100*time.Millisecond, min(s.maxWait, wait))
}

// RunPending 执行所有到点的任务，返回本轮结果。
func (s *Scheduler) RunPending(ctx context.Context, now time.Time) []Result {
	var results []Result
	for _, t := range s.tasks {
		if !t.Enabled() || t.nextRun.IsZero() || t.nextRun.After(now) {
			continue
		}
		results = append(results, s.RunTask(ctx, t))
	}
	return results
}

// RunTask 立刻执行一个任务并推进它的下次时刻。手动触发也走这里，因此不会与调度循环并发。
func (s *Scheduler) RunTask(ctx context.Context, t *Task) Result {
	s.runMu.Lock()
	defer s.runMu.Unlock()

	startedAt := time.Now()
	s.log.Info("任务开始执行", "task", t.Name)

	detail, err := t.Run(ctx)
	result := Result{
		Name:      t.Name,
		Success:   err == nil,
		StartedAt: startedAt,
		Duration:  time.Since(startedAt),
		Err:       err,
		Detail:    detail,
	}
	if err == nil {
		s.log.Info("任务执行完成", "task", t.Name, "seconds", result.Duration.Seconds())
	} else {
		s.log.Error("任务执行失败", "task", t.Name, "error", err)
	}

	if t.Enabled() {
		t.nextRun = t.followingRun(time.Now())
	}
	result.NextRun = t.nextRun

	if s.onResult != nil {
		s.onResult(result)
	}
	return result
}

// Lookup 按名字找任务，HTTP 层手动触发时用。
func (s *Scheduler) Lookup(name string) *Task {
	for _, t := range s.tasks {
		if t.Name == name {
			return t
		}
	}
	return nil
}
