/** 端点清单。路径与查询参数只在这里出现一次，别处拼字符串就容易和 docs/API.md 走散。 */

import { fetchJson, request } from './client.js';
import type {
  CreditsResponse,
  EmailAlertRecord,
  EmailScanState,
  EmailsConfigResponse,
  FeaturesResponse,
  HealthResponse,
  HistoryListResponse,
  JobsResponse,
  MailboxPayload,
  ProjectPayload,
  ProjectsConfigResponse,
  ProvidersResponse,
  RefreshResponse,
  SubscriptionPayload,
  SubscriptionsConfigResponse,
  SubscriptionsResponse,
  TrendResponse,
} from './types.js';
import type { FetchResult } from './client.js';

// ---------- 读 ----------

export const getFeatures = (): Promise<FeaturesResponse> => request<FeaturesResponse>('/api/features');

export const getCredits = (): Promise<CreditsResponse> => request<CreditsResponse>('/api/credits');

/** noCache：Subscription改完立刻重拉时要绕开 ETag 缓存，否则看到的还是旧值 */
export const getSubscriptions = (noCache = false): Promise<SubscriptionsResponse> =>
  request<SubscriptionsResponse>(
    '/api/subscriptions',
    noCache ? { headers: { 'Cache-Control': 'no-cache', Pragma: 'no-cache' } } : {},
  );

export const getSubscriptionsConfig = (): Promise<SubscriptionsConfigResponse> =>
  request<SubscriptionsConfigResponse>('/api/config/subscriptions');

export const getProviders = (): Promise<ProvidersResponse> => request<ProvidersResponse>('/api/providers');

export const getProjectsConfig = (): Promise<ProjectsConfigResponse> =>
  request<ProjectsConfigResponse>('/api/config/projects');

export const getMailboxes = (): Promise<EmailsConfigResponse> => request<EmailsConfigResponse>('/api/config/emails');

export const getEmailScanState = (): Promise<EmailScanState> => request<EmailScanState>('/api/email/scan');

export const getEmailHistory = (days = 30, limit = 100): Promise<HistoryListResponse<EmailAlertRecord>> =>
  request<HistoryListResponse<EmailAlertRecord>>(`/api/history/email-alerts?days=${days}&limit=${limit}`);

export const getHealth = (): Promise<HealthResponse> => request<HealthResponse>('/health');

export const getJobs = (): Promise<JobsResponse> => request<JobsResponse>('/api/jobs');

/**
 * 趋势：后端接受 md5 后的 project_id，也接受 "provider:name" 原文自行换算，
 * 前端没有 MD5 就走后者。注意路径段要转义，名字里可能有 `/` 或空格。
 */
export const getTrend = (provider: string, projectName: string, days = 30): Promise<FetchResult<TrendResponse>> =>
  fetchJson<TrendResponse>(`/api/history/trend/${encodeURIComponent(`${provider}:${projectName}`)}?days=${days}`);

// ---------- 写 ----------

export const refresh = (projectName?: string): Promise<RefreshResponse> =>
  request<RefreshResponse>('/api/refresh', {
    method: 'POST',
    body: JSON.stringify(projectName ? { project_name: projectName } : {}),
  });

export const runEmailScan = (days: number): Promise<EmailScanState> =>
  request<EmailScanState>('/api/email/scan', { method: 'POST', body: JSON.stringify({ days }) });

// 下面这些经由 mutate() 调用，只把路径集中在这里，载荷类型用来卡住调用方。
// docs/API.md 里的 /api/config/threshold 是只改阈值的快捷入口，页面上阈值在Project弹窗里改，用不到它。
export const ENDPOINTS = {
  saveProject: '/api/config/project',
  deleteProject: '/api/config/project/delete',
  addSubscription: '/api/subscription/add',
  updateSubscription: '/api/config/subscription',
  deleteSubscription: '/api/subscription/delete',
  markRenewed: '/api/subscription/mark_renewed',
  clearRenewed: '/api/subscription/clear_renewed',
  saveEmail: '/api/config/email',
  deleteEmail: '/api/config/email/delete',
} as const;

export type { MailboxPayload, ProjectPayload, SubscriptionPayload };
