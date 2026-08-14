#!/usr/bin/env python3
"""
余额监控 Provider 抽象基类
定义统一的接口规范和基础实现
"""
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import requests
from urllib3.util.retry import Retry

from core.logger import get_logger

logger = get_logger('provider_base')

DEFAULT_TIMEOUT = 15
DEFAULT_MAX_RETRIES = 3

_SENSITIVE_QUERY_KEYS = {
    'access_token',
    'ak',
    'api_key',
    'authorization',
    'key',
    'secret',
    'signature',
    'sk',
    'token',
}


def mask_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        path = parts.path or ''
        for marker in ('/hook/', '/token/', '/access_token/'):
            if marker in path:
                prefix, _, rest = path.partition(marker)
                token, sep, tail = rest.partition('/')
                if token:
                    masked_token = f"{token[:4]}***{token[-4:]}" if len(token) > 8 else "***"
                    path = f"{prefix}{marker}{masked_token}{sep}{tail}"
                break

        pairs = parse_qsl(parts.query, keep_blank_values=True)
        masked_pairs = []
        for k, v in pairs:
            if k.lower() in _SENSITIVE_QUERY_KEYS and v:
                masked_pairs.append((k, f"{v[:4]}***{v[-4:]}" if len(v) > 8 else "***"))
            else:
                masked_pairs.append((k, v))
        query = urlencode(masked_pairs, doseq=True)
        return urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))
    except Exception:
        return url


class BaseProvider(ABC):
    """余额监控 Provider 抽象基类"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.timeout = DEFAULT_TIMEOUT
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """创建带重试的 HTTP Session"""
        session = requests.Session()
        retry = Retry(
            total=DEFAULT_MAX_RETRIES,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({'GET', 'HEAD', 'OPTIONS'}),
            raise_on_status=False,
            respect_retry_after_header=True,
        )
        adapter = requests.adapters.HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session

    @abstractmethod
    def get_credits(self) -> Dict[str, Any]:
        """
        获取当前余额

        Returns:
            dict: success (bool) / credits (float|None) / error (str|None) / raw_data
        """

    @classmethod
    @abstractmethod
    def get_provider_name(cls) -> str:
        """返回服务商名称"""

    def _make_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """发送 HTTP 请求，失败重试由 Session 层负责"""
        kwargs.setdefault('timeout', self.timeout)
        logger.debug(f"发送 {method} 请求到 {mask_url(url)}")
        response = self.session.request(method, url, **kwargs)
        if response.status_code != 200:
            logger.warning(f"HTTP {response.status_code}: {response.text[:200]}")
        return response

    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        """把 HTTP 响应转成标准结果字典，子类在 raw_data 上继续解析 credits"""
        if response.status_code != 200:
            return {
                'success': False,
                'credits': None,
                'error': f"HTTP {response.status_code}: {response.reason}",
                'raw_data': response.text,
            }

        try:
            data = response.json()
        except ValueError:
            return {
                'success': False,
                'credits': None,
                'error': "响应不是有效的 JSON 格式",
                'raw_data': response.text,
            }

        return {'success': True, 'credits': None, 'error': None, 'raw_data': data}

    def _classify_exception(self, e: Exception) -> Dict[str, Any]:
        """统一异常分类，返回标准化的错误响应"""
        error_msg = str(e)

        if isinstance(e, requests.exceptions.Timeout):
            error = "请求超时"
        elif isinstance(e, requests.exceptions.ConnectionError):
            error = f"网络连接错误: {error_msg}"
        elif isinstance(e, requests.exceptions.HTTPError):
            error = f"HTTP错误: {error_msg}"
        elif isinstance(e, (ValueError, json.JSONDecodeError)):
            error = f"数据解析错误: {error_msg}"
        else:
            error = f"未知错误: {error_msg}"

        return {'success': False, 'credits': None, 'error': error, 'raw_data': None}

    def close(self):
        """显式关闭 session"""
        if getattr(self, 'session', None):
            self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


@dataclass(frozen=True)
class ProviderSpec:
    """声明一个「GET 一次、从 JSON 里取个数」的余额接口。

    extract: 从响应 JSON 取余额；取不到就 ``raise ValueError('说明')``
    check:   业务层成功校验，返回错误消息表示失败，返回 None 表示通过
    """
    name: str
    url: str
    extract: Callable[[Dict[str, Any]], float]
    auth: str = 'bearer'          # bearer=Authorization 头；query=拼进查询参数
    auth_param: str = 'key'       # auth='query' 时的参数名
    headers: Dict[str, str] = field(default_factory=dict)
    params: Dict[str, Any] = field(default_factory=dict)
    check: Optional[Callable[[Dict[str, Any]], Optional[str]]] = None


class SimpleHTTPProvider(BaseProvider):
    """按 ProviderSpec 声明式实现的 Provider，子类只需给出 SPEC。"""

    SPEC: ProviderSpec

    def get_credits(self) -> Dict[str, Any]:
        spec = self.SPEC
        try:
            headers = dict(spec.headers)
            params = dict(spec.params)
            if spec.auth == 'bearer':
                headers['Authorization'] = f"Bearer {self.api_key}"
            else:
                params[spec.auth_param] = self.api_key

            result = self._handle_response(
                self._make_request('GET', spec.url, headers=headers, params=params)
            )
            if not result['success']:
                return result

            data = result['raw_data']
            business_error = spec.check(data) if spec.check else None
            if business_error:
                return {'success': False, 'credits': None, 'error': business_error, 'raw_data': data}

            try:
                result['credits'] = spec.extract(data)
            except (ValueError, TypeError, AttributeError) as e:
                return {'success': False, 'credits': None, 'error': str(e), 'raw_data': data}
            return result

        except Exception as e:
            return self._classify_exception(e)

    @classmethod
    def get_provider_name(cls) -> str:
        return cls.SPEC.name
