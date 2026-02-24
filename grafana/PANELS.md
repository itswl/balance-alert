# Dashboard 面板说明

## 面板清单

### 第一行 - 关键指标概览（6个面板）

#### 1. 监控项目总数
- **类型**: Stat
- **查询**: `count(balance_alert_balance)`
- **用途**: 显示当前监控的项目总数

#### 2. 正常项目数
- **类型**: Stat
- **查询**: `count(balance_alert_status == 1)`
- **颜色**: 绿色（> 5）→ 黄色（1-4）→ 红色（0）
- **用途**: 余额充足的项目数量

#### 3. 告警项目数
- **类型**: Stat
- **查询**: `count(balance_alert_status == 0) or vector(0)`
- **颜色**: 绿色（0）→ 红色（≥ 1）
- **用途**: 余额不足需要告警的项目

#### 4. 订阅总数
- **类型**: Stat
- **查询**: `count(balance_alert_subscription_days)`
- **用途**: 配置的订阅总数

#### 5. 7天内到期订阅
- **类型**: Stat
- **查询**: `count(balance_alert_subscription_days <= 7 and balance_alert_subscription_status == 0)`
- **颜色**: 绿色（0）→ 红色（≥ 1）
- **用途**: 即将到期需要续费的订阅

#### 6. 最后检查时间
- **类型**: Stat
- **查询**: `balance_alert_last_check_timestamp * 1000`
- **格式**: 相对时间（如 "5 minutes ago"）
- **用途**: 系统最后一次检查的时间

---

### 第二行 - 余额对比与比例（2个面板）

#### 7. 项目余额/积分对比
- **类型**: Time Series (Bars)
- **查询**: `sort_desc(balance_alert_balance{project=~"$project"})`
- **样式**:
  - 柱状图
  - 按余额降序排列
  - 显示 last, min, max 值
- **用途**: 横向对比各项目余额大小

#### 8. 余额比例（余额/阈值）
- **类型**: Gauge
- **查询**: `balance_alert_ratio{project=~"$project"}`
- **阈值**:
  - 🔴 红色: 0-20%
  - 🟡 黄色: 20-50%
  - 🟢 绿色: 50-100%
- **布局**: 横向排列
- **用途**: 快速识别余额充裕程度

---

### 第三行 - 余额趋势（1个面板）

#### 9. 余额趋势图
- **类型**: Time Series
- **查询**: `balance_alert_balance{project=~"$project"}`
- **样式**:
  - Smooth 平滑曲线
  - 20% 透明度填充
  - 渐变效果
- **图例**: last, min, max, mean
- **用途**: 观察余额变化趋势，发现异常波动

---

### 第四行 - 余额详情表（1个面板）

#### 10. 项目余额详情表
- **类型**: Table
- **查询**:
  - `balance_alert_balance` - 余额
  - `balance_alert_threshold` - 阈值
  - `balance_alert_ratio` - 余额比例
  - `balance_alert_status` - 状态
- **列**:
  - 项目 (project)
  - 服务商 (provider)
  - 类型 (type)
  - 余额 (Value #A) - 颜色编码
  - 阈值 (Value #B)
  - 余额比例 (Value #C) - 仪表盘显示
  - 状态 (Value #D) - ✅/❌
- **功能**:
  - 可排序
  - 可筛选（通过 $project 变量）
  - 默认按余额比例升序排列
- **用途**: 详细查看每个项目的余额状态

---

### 第五行 - 订阅管理（2个面板）

#### 11. 订阅续费倒计时（天）
- **类型**: Stat
- **查询**: `sort(balance_alert_subscription_days{name=~"$subscription"})`
- **阈值**:
  - 🔴 红色: 0-3 天
  - 🟡 黄色: 3-7 天
  - 🟢 绿色: > 7 天
- **布局**: 横向排列
- **排序**: 按天数升序
- **用途**: 快速查看哪些订阅即将到期

#### 12. 订阅状态详情表
- **类型**: Table
- **查询**:
  - `balance_alert_subscription_days` - 剩余天数
  - `balance_alert_subscription_amount` - 续费金额
  - `balance_alert_subscription_status` - 状态
- **列**:
  - 订阅名称 (name)
  - 周期 (cycle_type)
  - 剩余天数 (Value #A) - 颜色编码
  - 货币 (currency)
  - 续费金额 (Value #B)
  - 状态 (Value #C) - 🟢正常/🔴需续费/🔵已续费
- **功能**:
  - 可排序
  - 默认按剩余天数升序
- **用途**: 详细管理订阅续费

---

## 变量说明

### project（项目筛选器）
- **类型**: Query Variable
- **查询**: `label_values(balance_alert_balance, project)`
- **选项**:
  - Multi-select（多选）
  - Include All（包含全部）
- **刷新**: On Dashboard Load
- **排序**: Alphabetical
- **用途**: 筛选指定项目的数据

### subscription（订阅筛选器）
- **类型**: Query Variable
- **查询**: `label_values(balance_alert_subscription_days, name)`
- **选项**:
  - Multi-select（多选）
  - Include All（包含全部）
- **刷新**: On Dashboard Load
- **排序**: Alphabetical
- **用途**: 筛选指定订阅的数据

---

## 颜色编码规则

### 余额状态
```
🟢 绿色 (green)  - 余额充足（> 50% 阈值）
🟡 黄色 (yellow) - 余额偏低（20-50% 阈值）
🔴 红色 (red)    - 余额不足（< 20% 阈值）
```

### 订阅状态
```
🟢 正常 (1)    - 距离续费日还有较长时间
🔴 需续费 (0)  - 已到续费时间或即将到期
🔵 已续费 (-1) - 用户已手动标记为已续费
```

### 剩余天数
```
🔴 红色 (red)    - < 3 天（紧急）
🟡 黄色 (yellow) - 3-7 天（警告）
🟢 绿色 (green)  - > 7 天（正常）
```

---

## 面板尺寸

```
┌────────────────────────────────────────────┐
│ Row 1: h=4, w=4 × 6 panels (total w=24)   │
│ [4×4] [4×4] [4×4] [4×4] [4×4] [4×4]       │
├────────────────────────────────────────────┤
│ Row 2: h=8                                 │
│ [8×12]           [8×12]                    │
├────────────────────────────────────────────┤
│ Row 3: h=9, w=24                           │
│ [9×24]                                     │
├────────────────────────────────────────────┤
│ Row 4: h=8, w=24                           │
│ [8×24]                                     │
├────────────────────────────────────────────┤
│ Row 5: h=7                                 │
│ [7×12]           [7×12]                    │
└────────────────────────────────────────────┘

总高度: 36 (4+8+9+8+7)
总宽度: 24 (Grafana 标准)
```

---

## 推荐配置

### 时间范围
- **默认**: 最近 6 小时
- **推荐**:
  - 实时监控: 1-6 小时
  - 趋势分析: 24 小时 - 7 天
  - 历史回溯: 30 天

### 自动刷新
- **默认**: 1 分钟
- **推荐**:
  - 生产环境: 1-5 分钟
  - 开发测试: 10-30 秒

### 时区
- **默认**: Browser（浏览器时区）
- **可选**: UTC, Asia/Shanghai, 等

---

## 性能优化

### 查询优化
- 使用 `{project=~"$project"}` 筛选减少数据量
- Instant 查询用于表格（不需要时间序列）
- Range 查询用于图表（需要历史数据）

### 面板刷新
- 表格使用 Instant 查询，减少数据传输
- 趋势图使用合理的时间范围
- 避免过于频繁的自动刷新

### 数据源
- 使用变量 `${DS_PROMETHEUS}` 支持动态数据源
- 导入时自动替换为实际数据源 UID

---

**面板版本**: 2.0
**总面板数**: 12
**支持 Grafana**: 10.0+
