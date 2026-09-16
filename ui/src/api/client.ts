/**
 * HTTP 客户端：API Key 管理、401 自动重试、写操作的统一提示。
 *
 * 所有 /api/* 都要带 X-API-Key。Key 存在 localStorage 里，首次打开或后端换了 key
 * 时弹窗要一次 —— 弹窗共用同一个 Promise，避免并发请求弹出五个框。
 */

import { byId } from '../dom.js';
import { readStorage, writeStorage } from '../state.js';
import { setLoading } from '../ui/loading.js';
import { showToast } from '../ui/toast.js';
import type { ApiPayload, ErrorResponse, MutationResponse } from './types.js';

export interface FetchResult<T> {
  response: Response;
  data: ApiPayload<T>;
}

const STORAGE_KEY = 'apiKey';

/** 同一时刻只允许有一个 API Key 弹窗 */
let pendingPrompt: Promise<string | null> | null = null;

export function getApiKey(): string {
  return (readStorage(STORAGE_KEY) ?? '').trim();
}

export function setApiKey(value: string | null | undefined): void {
  const key = (value ?? '').trim();
  writeStorage(STORAGE_KEY, key || null);
}

function authHeaders(): Record<string, string> {
  const key = getApiKey();
  return key ? { 'X-API-Key': key } : {};
}

/** 从任意响应体里挖出一条能给人看的错误信息 */
function errorMessage(data: unknown, fallback: string): string {
  if (data && typeof data === 'object') {
    const payload = data as Partial<ErrorResponse> & { error?: string };
    if (typeof payload.message === 'string' && payload.message) return payload.message;
    if (Array.isArray(payload.errors) && payload.errors.length) return payload.errors.join('；');
    if (typeof payload.error === 'string' && payload.error) return payload.error;
  }
  return fallback;
}

/**
 * 弹窗问 API Key。没有取消按钮是刻意的：没有 key 时页面上什么都拿不到，
 * 留一个「取消」只会让用户面对一个空看板。
 */
export function promptForApiKey(message = ''): Promise<string | null> {
  if (pendingPrompt) return pendingPrompt;

  pendingPrompt = new Promise<string | null>((resolve) => {
    const modal = byId('auth-modal');
    const form = byId<HTMLFormElement>('auth-form');
    const input = byId<HTMLInputElement>('auth-api-key');
    const error = byId('auth-error');

    // 模板被裁剪过时退回浏览器原生输入框，至少还能用
    if (!modal || !form || !input) {
      const value = window.prompt(message || '请输入 API Key', getApiKey());
      if (value !== null) setApiKey(value);
      resolve(getApiKey() || null);
      return;
    }

    if (error) {
      error.textContent = message;
      error.style.display = message ? 'block' : 'none';
    }
    input.value = getApiKey();
    modal.classList.add('active');
    input.focus();

    const onSubmit = (event: Event): void => {
      event.preventDefault();
      const value = input.value.trim();
      if (!value) {
        if (error) {
          error.textContent = '请输入 API Key';
          error.style.display = 'block';
        }
        return;
      }
      setApiKey(value);
      modal.classList.remove('active');
      form.removeEventListener('submit', onSubmit);
      resolve(value);
    };

    form.addEventListener('submit', onSubmit);
  });

  // 无论成功失败都要把共享 Promise 清掉，否则后续请求会一直等这个已结束的弹窗
  return pendingPrompt.finally(() => {
    pendingPrompt = null;
  });
}

async function ensureApiKey(): Promise<string | null> {
  const current = getApiKey();
  if (current) return current;
  return promptForApiKey();
}

/**
 * 发一次请求并尽力把响应体解析成 JSON。
 * 解析不出来时 data 是 null —— 代理返回 HTML 错误页时就是这种情况，调用方必须容忍。
 */
export async function fetchJson<T>(
  endpoint: string,
  options: RequestInit = {},
  retried = false,
): Promise<FetchResult<T>> {
  const isApi = endpoint.startsWith('/api/');
  if (isApi) await ensureApiKey();

  const url = endpoint.startsWith('http') ? endpoint : `${window.location.origin}${endpoint}`;
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
      ...(options.headers as Record<string, string> | undefined),
    },
  });

  let data: ApiPayload<T> = null;
  try {
    data = (await response.json()) as ApiPayload<T>;
  } catch {
    data = null;
  }

  if (response.status === 401 && isApi && !retried) {
    const key = await promptForApiKey(errorMessage(data, 'API Key 无效，请更新后继续'));
    if (key) return fetchJson<T>(endpoint, options, true);
  }

  return { response, data };
}

/** 读操作：失败就抛，由调用方决定怎么提示 */
export async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const { response, data } = await fetchJson<T>(endpoint, options);
  if (!response.ok) {
    throw new Error(errorMessage(data, response.statusText || `HTTP ${response.status}`));
  }
  if (data === null) {
    throw new Error('服务端返回的不是合法 JSON');
  }
  return data as T;
}

export interface MutateOptions {
  success?: string;
  fail?: string;
}

/**
 * 写操作：POST JSON，成功 / 失败各弹一次提示，失败返回 null。
 * 统一在这里弹提示，各个 manager 里就不会出现「有的提示有的不提示」。
 */
export async function mutate(
  endpoint: string,
  body: unknown,
  { success = '', fail = '操作失败' }: MutateOptions = {},
): Promise<MutationResponse | null> {
  setLoading(true);
  try {
    const { response, data } = await fetchJson<MutationResponse>(endpoint, {
      method: 'POST',
      body: JSON.stringify(body),
    });
    if (response.ok && data && (data as MutationResponse).status === 'success') {
      if (success) showToast(success, 'success');
      return data as MutationResponse;
    }
    showToast(errorMessage(data, fail), 'error');
    return null;
  } catch (error) {
    console.error(`${fail}:`, error);
    showToast(`${fail}，请稍后重试`, 'error');
    return null;
  } finally {
    setLoading(false);
  }
}
