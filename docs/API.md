# API

所有 `/api/*` 需要请求头 `X-API-Key: <WEB_API_KEY>`（或 `Authorization: Bearer <key>`）；`/health` 与 `/live` 不需要。响应是 JSON，出错时 `{"status": "error", "message": "..."}`，参数校验失败还会带 `errors` 列表。

| 状态码 | 含义 |
| --- | --- |
| 400 | 参数错误 |
| 401 | API Key 无效或未提供 |
| 404 | 不存在，或该能力的蓝图未注册（项目配置、历史 API） |
| 429 | 正在执行或冷却中（刷新、扫描） |
| 503 | `WEB_API_KEY` 未配置、能力未启用（订阅、邮箱写入）、服务未就绪 |

## 端点

| 方法与路径 | 说明 | 依赖开关 |
| --- | --- | --- |
| `GET /live` | 存活检查 | — |
| `GET /health` | 就绪检查：有数据、不过期、定时任务上次都成功才 200 | — |
| `GET /api/features` | 启用了哪些可选能力 | — |
| `GET /api/credits` | 所有项目的余额状态 | — |
| `GET/POST /api/refresh` | 立即检查余额，POST 可带 `project_name` 只刷一个；同一时间一个，完成后冷却 30 秒 | — |
| `GET /api/jobs` | 定时任务运行情况 | — |
| `GET /api/subscriptions` | 订阅状态，未启用时为空 | — |
| `GET /api/config/subscriptions` | 订阅配置 | 订阅 |
| `POST /api/subscription/add` | 添加订阅 | 订阅 |
| `POST /api/config/subscription` | 更新订阅，`name` 定位，`new_name` 改名，其余字段按需传 | 订阅 |
| `POST\|DELETE /api/subscription/delete` | 删除订阅 `{name}` | 订阅 |
| `POST /api/subscription/mark_renewed` `clear_renewed` | 标记 / 取消已续费，可带 `renewed_date` | 订阅 |
| `GET /api/config/projects` | 项目配置，密钥脱敏 | 动态配置 |
| `POST /api/config/threshold` | 改阈值 `{project_name, new_threshold}` | 动态配置 |
| `GET /api/config/emails` | 邮箱配置，密码脱敏 | — |
| `POST /api/config/email` | 新增或更新邮箱；`name` 是唯一键，新增需 `host` `username` `password`，更新时密码留空不改 | 动态配置 |
| `POST /api/config/email/delete` | 删除邮箱 `{name}` | 动态配置 |
| `GET /api/email/scan` | 上次扫描结果（进程内存，重启清空） | — |
| `POST /api/email/scan` | 立即扫描 `{days}`，1-30；同一时间一个，冷却 30 秒 | — |
| `GET /api/history/balance` `trend/<project_id>` `alerts` `stats` `email-alerts` | 历史查询；通用参数 `days` `limit`，余额可加 `project_id` `provider`，邮件可加 `mailbox` | 历史 API |

订阅 = `ENABLE_SUBSCRIPTIONS`，动态配置 = `ENABLE_DYNAMIC_CONFIG`（写入还需 `ENABLE_DATABASE`），历史 API = `ENABLE_HISTORY_API`。页面触发的刷新与扫描是否真发通知由 `ENABLE_WEB_ALARM` 决定。

## 示例

```bash
curl -H "X-API-Key: $WEB_API_KEY" http://localhost:8080/api/credits
curl -X POST -H "X-API-Key: $WEB_API_KEY" http://localhost:8080/api/refresh
curl -X POST -H "X-API-Key: $WEB_API_KEY" -H "Content-Type: application/json" \
  -d '{"days": 3}' http://localhost:8080/api/email/scan
curl -X POST -H "X-API-Key: $WEB_API_KEY" -H "Content-Type: application/json" \
  -d '{"name":"Netflix","cycle_type":"monthly","renewal_day":15,"alert_days_before":3,"amount":99}' \
  http://localhost:8080/api/subscription/add
```

`GET /api/credits`

```json
{
  "last_update": "2026-09-14T03:35:17Z",
  "projects": [
    { "project": "deepseek", "provider": "deepseek", "type": "balance", "owner_project": null,
      "success": true, "credits": 430.37, "threshold": 50, "need_alarm": false, "alarm_sent": false,
      "error": null, "cached": false }
  ],
  "summary": { "total": 2, "success": 2, "failed": 0, "need_alarm": 0 }
}
```

`GET /health`

```json
{ "status": "healthy", "has_data": true, "is_stale": false, "jobs_healthy": true, "failed_jobs": [],
  "last_update": "2026-09-14T03:35:17Z", "uptime_seconds": 3600, "version": "1.0.0" }
```

`GET /api/jobs`

```json
{
  "healthy": true,
  "jobs": [
    { "name": "alert_check", "description": "余额与订阅告警检查，发送真实通知", "schedule": "每天 09:00 / 15:00",
      "enabled": true, "next_run": "2026-09-15T01:00:00Z", "last_run": "2026-09-14T07:00:00Z",
      "last_success": "2026-09-14T07:00:00Z", "last_error": null, "last_duration_seconds": 1.42,
      "last_detail": { "projects": 8, "failed": 0, "need_alarm": 1, "subscriptions": 2, "need_alert": 0, "dry_run": false },
      "runs": 12, "failures": 0 }
  ]
}
```

`GET /api/email/scan`

```json
{
  "last_update": "2026-09-14T03:00:00Z", "days": 3, "dry_run": true,
  "mailboxes": [
    { "name": "工作邮箱", "host": "imap.example.com", "port": 993, "username": "me@example.com",
      "total_emails": 12, "alert_count": 1, "success": true, "error": null }
  ],
  "alerts": [
    { "mailbox": "工作邮箱", "subject": "【阿里云】余额不足提醒", "sender": "noreply@aliyun.com",
      "date": "Mon, 01 Sep 2026 10:00:00 +0800", "keywords": ["余额不足"],
      "service_name": "阿里云", "amount": 12.5, "alert_sent": false }
  ],
  "summary": { "total_mailboxes": 1, "failed_mailboxes": 0, "total_emails": 12, "total_alerts": 1, "alerts_sent": 0 }
}
```
