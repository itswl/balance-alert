/** 格式化、跑道文案、状态判定的冒烟测试。这几个函数决定了看板上每个数字怎么读。 */

import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import type { Runway } from '../src/api/types.js';
import {
  cycleLabel,
  escapeHTML,
  formatBalance,
  formatCurrency,
  formatRunway,
  getBalancePercentage,
  getBalanceStatus,
  getRelativeTime,
  renewalUrgency,
  typeLabel,
} from '../src/format.js';

/** 造一份跑道数据，只覆盖当前用例关心的字段 */
function runway(overrides: Partial<Runway>): Runway {
  return {
    project_id: 'id',
    project_name: 'p',
    provider: 'deepseek',
    balance_type: 'balance',
    current_balance: 100,
    window_days: 7,
    data_points: 168,
    span_hours: 167,
    consumed: 0,
    topped_up: 0,
    burn_per_day: null,
    runway_days: null,
    depletion_date: null,
    confidence: 'high',
    daily: [],
    today_consumed: null,
    baseline_consumed: null,
    spike_ratio: null,
    ...overrides,
  };
}

describe('formatCurrency', () => {
  it('保留两位小数', () => {
    assert.equal(formatCurrency(430.371), '430.37');
    assert.equal(formatCurrency(0), '0.00');
  });

  it('拿不到数字时给 - 而不是 0', () => {
    assert.equal(formatCurrency(null), '-');
    assert.equal(formatCurrency(undefined), '-');
    assert.equal(formatCurrency('abc'), '-');
  });
});

describe('formatBalance', () => {
  it('配额型带百分号单位', () => {
    assert.equal(formatBalance(42.35, 'quota'), '42.4<span class="unit">%</span>');
  });

  it('其余类型带千分位并保留两位', () => {
    assert.equal(formatBalance(1234.5, 'balance'), '1,234.50');
    assert.equal(formatBalance(1234.5, 'credits'), '1,234.50');
  });

  it('非数字给 -', () => {
    assert.equal(formatBalance(null, 'balance'), '-');
  });
});

describe('typeLabel', () => {
  it('已知类型翻成中文', () => {
    assert.equal(typeLabel('balance'), '余额');
    assert.equal(typeLabel('credits'), 'Credits');
    assert.equal(typeLabel('quota'), '配额');
  });

  it('未知或空类型退回「余额」', () => {
    assert.equal(typeLabel(''), '余额');
    assert.equal(typeLabel(null), '余额');
    assert.equal(typeLabel('unknown'), 'unknown');
  });
});

describe('formatRunway', () => {
  it('没有跑道数据时说「数据积累中」，绝不能显示成 0 天', () => {
    const result = formatRunway(null);
    assert.equal(result.text, '数据积累中');
    assert.equal(result.level, 'unknown');
    assert.match(result.hint, /攒够/);
  });

  it('置信度 none 等同于没有数据', () => {
    assert.equal(formatRunway(runway({ confidence: 'none', burn_per_day: 10, runway_days: 5 })).text, '数据积累中');
  });

  it('没有消耗时说「无消耗」，不是「用不完」也不是 0', () => {
    const result = formatRunway(runway({ burn_per_day: 0, window_days: 7 }));
    assert.equal(result.text, '无消耗');
    assert.equal(result.level, 'normal');
    assert.equal(result.hint, '最近 7 天余额没有下降');
  });

  it('有日均消耗但算不出天数时给破折号', () => {
    const result = formatRunway(runway({ burn_per_day: 12, runway_days: null }));
    assert.equal(result.text, '—');
    assert.equal(result.level, 'unknown');
  });

  it('不足一天单独说明', () => {
    assert.equal(formatRunway(runway({ burn_per_day: 100, runway_days: 0.4 })).text, '不足 1 天');
  });

  it('十天以内保留一位小数，之后取整', () => {
    assert.equal(formatRunway(runway({ burn_per_day: 62.5, runway_days: 6.89 })).text, '6.9 天');
    assert.equal(formatRunway(runway({ burn_per_day: 1, runway_days: 12.4 })).text, '12 天');
  });

  it('超过一年不给具体数字', () => {
    assert.equal(formatRunway(runway({ burn_per_day: 0.01, runway_days: 400 })).text, '超过 1 年');
  });

  it('颜色档位：3 天内红、7 天内黄、再往上正常', () => {
    assert.equal(formatRunway(runway({ burn_per_day: 1, runway_days: 3 })).level, 'danger');
    assert.equal(formatRunway(runway({ burn_per_day: 1, runway_days: 3.1 })).level, 'warning');
    assert.equal(formatRunway(runway({ burn_per_day: 1, runway_days: 7 })).level, 'warning');
    assert.equal(formatRunway(runway({ burn_per_day: 1, runway_days: 7.1 })).level, 'normal');
  });

  it('有预计耗尽日期时提示里带上日期和日均', () => {
    const result = formatRunway(runway({ burn_per_day: 62.5, runway_days: 6.89, depletion_date: '2026-09-21' }));
    assert.equal(result.hint, '按日均 62.50 估算，约 2026-09-21 耗尽');
  });
});

describe('getBalanceStatus', () => {
  it('按余额相对阈值的比例分三档', () => {
    assert.equal(getBalanceStatus(100, 50), 'normal'); // 200%
    assert.equal(getBalanceStatus(25, 50), 'normal'); // 50%
    assert.equal(getBalanceStatus(20, 50), 'warning'); // 40%
    assert.equal(getBalanceStatus(10, 50), 'warning'); // 20%
    assert.equal(getBalanceStatus(9, 50), 'danger'); // 18%
  });

  it('阈值为 0（不告警）时一律算正常', () => {
    assert.equal(getBalancePercentage(0, 0), 100);
    assert.equal(getBalanceStatus(0, 0), 'normal');
  });
});

describe('escapeHTML', () => {
  it('项目名里的尖括号和引号不会变成标签', () => {
    assert.equal(escapeHTML('<img src=x onerror="alert(1)">'), '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;');
    assert.equal(escapeHTML("it's"), 'it&#39;s');
  });

  it('null / undefined 变成空串', () => {
    assert.equal(escapeHTML(null), '');
    assert.equal(escapeHTML(undefined), '');
  });
});

describe('getRelativeTime', () => {
  const now = new Date('2026-09-14T12:00:00Z');

  it('按间隔给出不同粒度', () => {
    assert.equal(getRelativeTime('2026-09-14T11:59:30Z', now), '刚刚');
    assert.equal(getRelativeTime('2026-09-14T11:30:00Z', now), '30分钟前');
    assert.equal(getRelativeTime('2026-09-14T09:00:00Z', now), '3小时前');
    assert.equal(getRelativeTime('2026-09-12T12:00:00Z', now), '2天前');
  });

  it('超过一周退回绝对时间，「8天前」没有信息量', () => {
    assert.ok(!getRelativeTime('2026-09-01T12:00:00Z', now).endsWith('天前'));
  });

  it('没有时间戳时说「未知」', () => {
    assert.equal(getRelativeTime(null, now), '未知');
  });
});

describe('订阅展示', () => {
  it('周期翻成中文', () => {
    assert.equal(cycleLabel('monthly'), '月付');
    assert.equal(cycleLabel('yearly'), '年付');
    assert.equal(cycleLabel('weekly'), '周付');
  });

  it('续费紧迫度：7 天内红，14 天内黄', () => {
    assert.equal(renewalUrgency(3), 'danger');
    assert.equal(renewalUrgency(7), 'danger');
    assert.equal(renewalUrgency(8), 'warning');
    assert.equal(renewalUrgency(14), 'warning');
    assert.equal(renewalUrgency(15), '');
  });
});
