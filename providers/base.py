#!/usr/bin/env python3
"""
余额监控 Provider 抽象基类
定义统一的接口规范和基础实现
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from enum import Enum
import json
import time
import threading
import requests
from logger import get_logger

logger = get_logger('provider_base')

# HTTP 连接默认常量
DEFAULT_TIMEOUT = 15
DEFAULT_POOL_CONNECTIONS = 10
DEFAULT_POOL_MAXSIZE = 100
DEFAULT_MAX_RETRIES = 3

# 熔断器常量
CIRCUIT_FAILURE_THRESHOLD = 3  # 连续失败次数阈值
CIRCUIT_OPEN_TIMEOUT = 60  # 熔断打开持续时间（秒）


class CircuitState(Enum):
    CLOSED = 'closed'
    OPEN = 'open'
    HALF_OPEN = 'half_open'


class CircuitBreaker:
    """熔断器：连续失败达到阈值后暂停请求"""

    def __init__(self, name: str, failure_threshold: int = CIRCUIT_FAILURE_THRESHOLD,
                 open_timeout: float = CIRCUIT_OPEN_TIMEOUT):
        self.name = name
        self.failure_threshold = failure_threshold
        self.open_timeout = open_timeout
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.time() - self._last_failure_time >= self.open_timeout:
                    self._state = CircuitState.HALF_OPEN
                    logger.info(f"[CircuitBreaker:{self.name}] OPEN -> HALF_OPEN")
            return self._state

    def allow_request(self) -> bool:
        """检查是否允许请求通过"""
        current = self.state
        if current == CircuitState.CLOSED:
            return True
        if current == CircuitState.HALF_OPEN:
            return True  # 允许一次试探请求
        return False

    def record_success(self) -> None:
        """记录成功请求"""
        with self._lock:
            self._failure_count = 0
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                logger.info(f"[CircuitBreaker:{self.name}] HALF_OPEN -> CLOSED")

    def record_failure(self) -> None:
        """记录失败请求"""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning(f"[CircuitBreaker:{self.name}] HALF_OPEN -> OPEN (试探失败)")
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    f"[CircuitBreaker:{self.name}] CLOSED -> OPEN "
                    f"(连续失败 {self._failure_count} 次, 熔断 {self.open_timeout}s)"
                )


# 全局熔断器注册表（按 provider name 共享）
_circuit_breakers: Dict[str, CircuitBreaker] = {}
_circuit_breakers_lock = threading.Lock()


def get_circuit_breaker(name: str) -> CircuitBreaker:
    """获取或创建指定 provider 的熔断器"""
    with _circuit_breakers_lock:
        if name not in _circuit_breakers:
            _circuit_breakers[name] = CircuitBreaker(name)
        return _circuit_breakers[name]


class BaseProvider(ABC):
    """余额监控 Provider 抽象基类"""
    
    def __init__(self, api_key: str):
        """
        初始化 Provider
        
        Args:
            api_key: API 密钥
        """
        self.api_key = api_key
        self.timeout = DEFAULT_TIMEOUT
        self.session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        """创建带连接池的 HTTP Session"""
        session = requests.Session()
        
        # 配置连接池
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=DEFAULT_POOL_CONNECTIONS,
            pool_maxsize=DEFAULT_POOL_MAXSIZE,
            max_retries=DEFAULT_MAX_RETRIES
        )
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        
        return session
    
    @abstractmethod
    def get_credits(self) -> Dict[str, Any]:
        """
        获取当前余额/积分
        
        Returns:
            dict: 包含以下字段的字典
                - success (bool): 是否成功获取
                - credits (float): 余额数值，失败时为 None
                - error (str): 错误信息，成功时为 None
                - raw_data (dict): 原始 API 响应数据
        """
        pass
    
    @classmethod
    @abstractmethod
    def get_provider_name(cls) -> str:
        """返回服务商名称"""
        pass
    
    def _make_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        发送 HTTP 请求的基础方法（带熔断器保护）

        Args:
            method: HTTP 方法 ('GET', 'POST', etc.)
            url: 请求 URL
            **kwargs: 其他 requests 参数

        Returns:
            requests.Response: 响应对象

        Raises:
            requests.RequestException: 网络请求异常
            ProviderError: 熔断器打开时
        """
        # 检查熔断器
        breaker = get_circuit_breaker(self.get_provider_name())
        if not breaker.allow_request():
            raise ProviderError(
                f"Provider [{self.get_provider_name()}] 熔断器已打开，"
                f"请求被拒绝（将在 {CIRCUIT_OPEN_TIMEOUT}s 后自动恢复）"
            )

        # 设置默认超时时间
        if 'timeout' not in kwargs:
            kwargs['timeout'] = self.timeout

        logger.debug(f"发送 {method} 请求到 {url}")
        try:
            response = self.session.request(method, url, **kwargs)

            if response.status_code != 200:
                logger.warning(f"HTTP {response.status_code}: {response.text[:200]}")

            # 成功响应（包括非 200 但连接成功的）记录成功
            breaker.record_success()
            return response
        except requests.RequestException:
            breaker.record_failure()
            raise
    
    def _handle_response(self, response: requests.Response, success_condition=None) -> Dict[str, Any]:
        """
        处理 HTTP 响应的通用方法
        
        Args:
            response: HTTP 响应对象
            success_condition: 成功条件判断函数，接受 response 参数
            
        Returns:
            dict: 标准化的响应字典
        """
        try:
            # 检查 HTTP 状态码
            if response.status_code != 200:
                return {
                    'success': False,
                    'credits': None,
                    'error': f"HTTP {response.status_code}: {response.reason}",
                    'raw_data': response.text
                }
            
            # 解析 JSON
            try:
                data = response.json()
            except ValueError:
                return {
                    'success': False,
                    'credits': None,
                    'error': "响应不是有效的 JSON 格式",
                    'raw_data': response.text
                }
            
            # 检查自定义成功条件
            if success_condition and not success_condition(response):
                return {
                    'success': False,
                    'credits': None,
                    'error': "API 返回业务错误",
                    'raw_data': data
                }
            
            return {
                'success': True,
                'credits': None,  # 子类需要设置具体值
                'error': None,
                'raw_data': data
            }
            
        except Exception as e:
            logger.error(f"处理响应时发生错误: {e}")
            return {
                'success': False,
                'credits': None,
                'error': f"处理响应错误: {str(e)}",
                'raw_data': None
            }
    
    def _extract_numeric_value(self, value: Any) -> Optional[float]:
        """
        从各种格式中提取数值
        
        Args:
            value: 原始值（可能是字符串、数字等）
            
        Returns:
            float: 数值，转换失败返回 None
        """
        if value is None:
            return None
            
        try:
            # 如果是字符串，先清理格式
            if isinstance(value, str):
                # 移除千位分隔符和货币符号
                cleaned = value.strip().replace(',', '').replace('¥', '').replace('$', '')
                return float(cleaned)
            else:
                return float(value)
        except (ValueError, TypeError):
            return None
    
    def _extract_field(self, data: Dict[str, Any], *paths: str) -> Any:
        """
        从嵌套字典中按路径提取字段，返回第一个非None的值

        Args:
            data: 数据字典
            *paths: 字段路径，支持点分隔，如 'data.balance', 'Result.AvailableBalance'

        Returns:
            找到的值，全部未找到返回 None
        """
        for path in paths:
            value = data
            try:
                for key in path.split('.'):
                    if isinstance(value, dict):
                        value = value.get(key)
                    else:
                        value = None
                        break
                if value is not None:
                    return value
            except (KeyError, TypeError, AttributeError):
                continue
        return None

    def _classify_exception(self, e: Exception) -> Dict[str, Any]:
        """
        统一异常分类，返回标准化的错误响应

        Args:
            e: 异常对象

        Returns:
            dict: 标准化错误响应
        """
        import requests as req
        error_msg = str(e)

        if isinstance(e, req.exceptions.Timeout):
            error = "请求超时"
        elif isinstance(e, req.exceptions.ConnectionError):
            error = f"网络连接错误: {error_msg}"
        elif isinstance(e, req.exceptions.HTTPError):
            error = f"HTTP错误: {error_msg}"
        elif isinstance(e, (ValueError, json.JSONDecodeError)):
            error = f"数据解析错误: {error_msg}"
        else:
            error = f"未知错误: {error_msg}"

        return {
            'success': False,
            'credits': None,
            'error': error,
            'raw_data': None
        }

    def close(self):
        """显式关闭 session"""
        if hasattr(self, 'session') and self.session:
            self.session.close()

    def __del__(self):
        """析构函数，关闭 session"""
        self.close()


# 异常类定义
class ProviderError(Exception):
    """Provider 基础异常类"""
    pass


class AuthenticationError(ProviderError):
    """认证错误"""
    pass


class APIError(ProviderError):
    """API 调用错误"""
    pass


class ParseError(ProviderError):
    """数据解析错误"""
    pass