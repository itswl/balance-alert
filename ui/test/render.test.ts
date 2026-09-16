/** 渲染函数的冒烟测试：卡片 HTML、筛选、顶部概览。跑在桩 DOM 上。 */

import './stub-dom.js';

import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import type { CheckResult, CreditsResponse, Features, Runway, SubscriptionResult } from '../src/api/types.js';
import { filterProjects, renderProjectCard, renderProjects } from '../src/ui/projects.js';
import { renderSubscriptionCard } from '../src/ui/subscriptions.js';
import { shortestRunway, updateStats } from '../src/ui/stats.js';
import { resetStubDom, stubElement } from './stub-dom.js';

const ALL_OFF: Features = { subscriptions: false, dynamic_config: false, history: false };
const ALL_ON: Features = { subscriptions: true, dynamic_config: true, history: true };

function project(overrides: Partial<CheckResult> = {}): CheckResult {
  return {
    project: 'deepseek',
    owner_project: null,
    provider: 'deepseek',
    type: 'balance',
    success: true,
    credits: 430.37,
    threshold: 50,
    need_alarm: false,
    alarm_sent: false,
    error: null,
    cached: false,
    ...overrides,
  };
}

function runway(overrides: Partial<Runway> = {}): Runway {
  return {
    project_id: 'id',
    project_name: 'deepseek',
    provider: 'deepseek',
    balance_type: 'balance',
    current_balance: 430.37,
    window_days: 7,
    data_points: 168,
    span_hours: 167,
    consumed: 437.5,
    topped_up: 0,
    burn_per_day: 62.5,
    runway_days: 6.89,
    depletion_date: '2026-09-21',
    confidence: 'high',
    daily: [],
    today_consumed: null,
    baseline_consumed: null,
    spike_ratio: null,
    ...overrides,
  };
}

describe('renderProjectCard', () => {
  it('把项目名、平台、余额和跑道都放进卡片', () => {
    const html = renderProjectCard(project({ runway: runway() }), ALL_OFF);
    assert.match(html, /<h3>deepseek<\/h3>/);
    assert.match(html, /class="project-provider">deepseek</);
    assert.match(html, />430\.37</);
    assert.match(html, />6\.9 天</);
    assert.match(html, /runway-warning/);
    assert.match(html, /约 2026-09-21 耗尽/);
  });

  it('没有跑道数据时显示「数据积累中」而不是 0 天', () => {
    const html = renderProjectCard(project(), ALL_OFF);
    assert.match(html, />数据积累中</);
    assert.match(html, /runway-unknown/);
    assert.match(html, /<span class="detail-value">—<\/span>/); // 日均消耗
  });

  it('项目名里的 HTML 被转义，不会注入标签', () => {
    const html = renderProjectCard(project({ project: '<img src=x onerror=alert(1)>' }), ALL_OFF);
    assert.ok(!html.includes('<img src=x'));
    assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
  });

  it('关掉动态配置就没有编辑 / 删除按钮，关掉历史就没有趋势入口', () => {
    const html = renderProjectCard(project(), ALL_OFF);
    assert.ok(!html.includes('js-edit-project'));
    assert.ok(!html.includes('js-delete-project'));
    assert.ok(!html.includes('js-show-trend'));
  });

  it('开关都打开时三个入口都在，并带上定位用的 data 属性', () => {
    const html = renderProjectCard(project(), ALL_ON);
    assert.match(html, /js-edit-project" data-project="deepseek"/);
    assert.match(html, /js-delete-project" data-project="deepseek"/);
    assert.match(html, /js-show-trend" data-project="deepseek" data-provider="deepseek"/);
  });

  it('告警项目的状态位和文案都切换', () => {
    const html = renderProjectCard(project({ need_alarm: true }), ALL_OFF);
    assert.match(html, /data-status="alert"/);
    assert.match(html, /status-text alert">告警</);
  });

  it('配额型显示百分比和「剩余配额」', () => {
    const html = renderProjectCard(project({ type: 'quota', credits: 42.35, threshold: 10 }), ALL_OFF);
    assert.match(html, /剩余配额/);
    assert.match(html, /42\.4<span class="unit">%<\/span>/);
  });
});

describe('filterProjects', () => {
  const projects = [
    project({ project: 'deepseek', provider: 'deepseek', need_alarm: false }),
    project({ project: '火山-主账号', provider: 'volcengine', need_alarm: true }),
    project({ project: 'openrouter', provider: 'openrouter', need_alarm: false }),
  ];

  it('搜索同时匹配项目名和平台名，且不区分大小写', () => {
    assert.equal(filterProjects(projects, { search: 'DEEP', provider: 'all', alertsOnly: false }).length, 1);
    assert.equal(filterProjects(projects, { search: 'volcengine', provider: 'all', alertsOnly: false }).length, 1);
    assert.equal(filterProjects(projects, { search: '火山', provider: 'all', alertsOnly: false }).length, 1);
  });

  it('平台筛选和「仅告警」可以叠加', () => {
    assert.equal(filterProjects(projects, { search: '', provider: 'openrouter', alertsOnly: false }).length, 1);
    assert.equal(filterProjects(projects, { search: '', provider: 'all', alertsOnly: true }).length, 1);
    assert.equal(filterProjects(projects, { search: '', provider: 'openrouter', alertsOnly: true }).length, 0);
  });
});

describe('shortestRunway', () => {
  it('挑出最先见底的那个账户', () => {
    const projects = [
      project({ project: 'a', runway: runway({ runway_days: 12 }) }),
      project({ project: 'b', runway: runway({ runway_days: 2.5 }) }),
      project({ project: 'c', runway: runway({ runway_days: 30 }) }),
    ];
    assert.equal(shortestRunway(projects)?.project, 'b');
  });

  it('失败的项目和没有估算的项目都不参与排序', () => {
    const projects = [
      project({ project: 'failed', success: false, runway: runway({ runway_days: 0.1 }) }),
      project({ project: 'no-estimate', runway: runway({ runway_days: null }) }),
      project({ project: 'ok', runway: runway({ runway_days: 9 }) }),
    ];
    assert.equal(shortestRunway(projects)?.project, 'ok');
  });

  it('一个都算不出来时返回 null', () => {
    assert.equal(shortestRunway([project()]), null);
  });
});

describe('renderSubscriptionCard', () => {
  function subscription(overrides: Partial<SubscriptionResult> = {}): SubscriptionResult {
    return {
      name: 'Netflix',
      owner_project: null,
      renewal_day: 15,
      cycle_type: 'monthly',
      days_until_renewal: 20,
      next_renewal_date: '2026-10-15',
      need_alert: false,
      alert_sent: false,
      amount: 99,
      already_renewed: false,
      last_renewed_date: null,
      ...overrides,
    };
  }

  it('显示金额、周期、下次续费日和剩余天数', () => {
    const html = renderSubscriptionCard(subscription());
    assert.match(html, /<h3>Netflix<\/h3>/);
    assert.match(html, />99\.00</);
    assert.match(html, />月付</);
    assert.match(html, />2026-10-15</);
    assert.match(html, /days-remaining ">20<span class="unit">天<\/span>/);
  });

  it('剩余 7 天内标红，14 天内标黄', () => {
    assert.match(renderSubscriptionCard(subscription({ days_until_renewal: 5 })), /days-remaining danger/);
    assert.match(renderSubscriptionCard(subscription({ days_until_renewal: 10 })), /days-remaining warning/);
  });

  it('已续费时换成「取消续费标记」按钮', () => {
    const html = renderSubscriptionCard(subscription({ already_renewed: true }));
    assert.match(html, /js-clear-renewed/);
    assert.ok(!html.includes('js-mark-renewed'));
    assert.match(html, /status-badge success">已续费</);
  });

  it('未续费时是「标记已续费」按钮', () => {
    const html = renderSubscriptionCard(subscription());
    assert.match(html, /js-mark-renewed/);
    assert.ok(!html.includes('js-clear-renewed'));
  });
});

describe('桩 DOM 上的顶部概览', () => {
  it('统计数字与最短跑道都写进对应元素', () => {
    resetStubDom();
    const total = stubElement('total-projects');
    const normal = stubElement('normal-projects');
    const alert = stubElement('alert-projects');
    const lastUpdate = stubElement('last-update');
    const runwayValue = stubElement('shortest-runway');
    const runwayLabel = stubElement('shortest-runway-label');

    const data: CreditsResponse = {
      last_update: new Date().toISOString(),
      projects: [
        project({ project: 'a', runway: runway({ runway_days: 2 }) }),
        project({ project: 'b', need_alarm: true }),
        project({ project: 'c', success: false, credits: null, threshold: null }),
      ],
      summary: {},
    };
    updateStats(data);

    assert.equal(total.textContent, '3');
    assert.equal(normal.textContent, '1'); // 失败的和告警的都不算正常
    assert.equal(alert.textContent, '1');
    assert.equal(lastUpdate.textContent, '刚刚');
    assert.equal(runwayValue.textContent, '2.0 天');
    assert.equal(runwayValue.className, 'stat-value runway-danger');
    assert.equal(runwayLabel.textContent, '最短跑道 · a');
  });

  it('一个项目都估算不出跑道时退回破折号', () => {
    resetStubDom();
    stubElement('total-projects');
    stubElement('normal-projects');
    stubElement('alert-projects');
    stubElement('last-update');
    const runwayValue = stubElement('shortest-runway');
    const runwayLabel = stubElement('shortest-runway-label');

    updateStats({ last_update: null, projects: [project()], summary: {} });

    assert.equal(runwayValue.textContent, '—');
    assert.equal(runwayValue.className, 'stat-value');
    assert.equal(runwayLabel.textContent, '最短跑道');
  });
});

describe('桩 DOM 上的项目列表', () => {
  it('筛不出结果时渲染空状态而不是空白', () => {
    resetStubDom();
    const container = stubElement('projects-container');
    renderProjects({ last_update: null, projects: [], summary: {} });

    assert.match(container.innerHTML, /empty-state/);
    assert.match(container.innerHTML, /没有找到符合条件的项目/);
    assert.equal(container.className, 'projects-grid');
  });

  it('有数据时每个项目一张卡片', () => {
    resetStubDom();
    const container = stubElement('projects-container');
    renderProjects({
      last_update: null,
      projects: [project({ project: 'a' }), project({ project: 'b' })],
      summary: {},
    });

    assert.equal(container.innerHTML.match(/class="project-card"/g)?.length, 2);
  });
});
