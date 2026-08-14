"""
火山云余额查询适配器

签名算法：火山引擎 V4（HMAC-SHA256），与 AWS SigV4 同构。
"""
import datetime
import hashlib
import hmac
import json
from urllib.parse import quote

from core.logger import get_logger
from .base import BaseProvider, mask_url

logger = get_logger('volc_provider')

# 参与签名的请求头，顺序即签名顺序（规范请求与 Authorization 头共用这一处定义）
SIGNED_HEADERS = ('content-type', 'host', 'x-content-sha256', 'x-date')


class VolcProvider(BaseProvider):
    """火山云服务适配器"""

    SERVICE = 'billing'
    ACTION = 'QueryBalanceAcct'
    VERSION = '2022-01-01'
    REGION = 'cn-shanghai'
    HOST = 'open.volcengineapi.com'
    CONTENT_TYPE = 'application/json'
    PATH = '/'
    METHOD = 'GET'

    def __init__(self, api_key):
        """
        初始化火山云适配器

        Args:
            api_key: 格式为 "AK:SK" 的密钥对，用冒号分隔（例如 "AKLTxxx:TmpCa01xxx"）
        """
        if ':' not in api_key:
            raise ValueError("火山云 API Key 格式错误，应为 'AK:SK' 格式")

        super().__init__(api_key)
        self.ak, self.sk = api_key.split(':', 1)
        # 兼容旧属性名（测试与外部代码可能读取）
        self.service = self.SERVICE
        self.action = self.ACTION
        self.version = self.VERSION
        self.region = self.REGION
        self.host = self.HOST
        self.content_type = self.CONTENT_TYPE

    def get_credits(self):
        """
        获取当前余额

        Returns:
            dict: success / credits / error / raw_data
        """
        try:
            response_data = self._send_request()

            if not response_data:
                return {'success': False, 'credits': None, 'error': "API 返回空响应", 'raw_data': None}

            if response_data.get('ResponseMetadata', {}).get('Error'):
                error_info = response_data['ResponseMetadata']['Error']
                return {
                    'success': False,
                    'credits': None,
                    'error': f"API 返回错误: {error_info}",
                    'raw_data': response_data
                }

            available_balance = response_data.get('Result', {}).get('AvailableBalance')
            if available_balance is None:
                return {
                    'success': False,
                    'credits': None,
                    'error': "无法从响应中解析 AvailableBalance 字段",
                    'raw_data': response_data
                }

            return {
                'success': True,
                'credits': float(available_balance),
                'error': None,
                'raw_data': response_data
            }

        except Exception as e:
            return self._classify_exception(e)

    @property
    def _query(self):
        return {'Action': self.ACTION, 'Version': self.VERSION}

    def _send_request(self):
        """签名并发送火山云 API 请求"""
        headers = self._build_headers(datetime.datetime.now(datetime.UTC))
        url = f"https://{self.HOST}{self.PATH}?{self._norm_query(self._query)}"

        logger.debug(f"火山云请求 URL: {mask_url(url)} | 签名 {headers['Authorization'][:40]}***")
        try:
            response = self.session.request(
                method=self.METHOD, url=url, headers=headers, data='', timeout=self.timeout
            )
            logger.debug(f"火山云响应 {response.status_code}: {response.text[:200]}")
        except Exception as e:
            logger.error(f"火山云请求失败: {e}", exc_info=True)
            raise

        if response.status_code != 200:
            raise Exception(f'HTTP请求失败，状态码：{response.status_code}\n响应内容：{response.text}')

        if not response.text.strip():
            return {}

        try:
            return response.json()
        except json.JSONDecodeError:
            raise Exception(f'响应内容不是有效的JSON格式：{response.text}')

    def _build_headers(self, now, body=''):
        """构建带签名的请求头"""
        x_date = now.strftime('%Y%m%dT%H%M%SZ')
        short_date = x_date[:8]
        content_sha256 = self._hash_sha256(body)
        credential_scope = f"{short_date}/{self.REGION}/{self.SERVICE}/request"
        signed_headers_str = ';'.join(SIGNED_HEADERS)

        # 规范请求：方法 / 路径 / 查询串 / 头 / 空行 / 签名头列表 / body 摘要
        canonical_request = '\n'.join([
            self.METHOD,
            self.PATH,
            self._norm_query(self._query),
            f"content-type:{self.CONTENT_TYPE}",
            f"host:{self.HOST}",
            f"x-content-sha256:{content_sha256}",
            f"x-date:{x_date}",
            '',
            signed_headers_str,
            content_sha256,
        ])

        string_to_sign = '\n'.join([
            'HMAC-SHA256', x_date, credential_scope, self._hash_sha256(canonical_request)
        ])

        signing_key = self.sk.encode('utf-8')
        for part in (short_date, self.REGION, self.SERVICE, 'request'):
            signing_key = self._hmac_sha256(signing_key, part)
        signature = self._hmac_sha256(signing_key, string_to_sign).hex()

        return {
            'Host': self.HOST,
            'X-Content-Sha256': content_sha256,
            'X-Date': x_date,
            'Content-Type': self.CONTENT_TYPE,
            'Authorization': (
                f"HMAC-SHA256 Credential={self.ak}/{credential_scope}, "
                f"SignedHeaders={signed_headers_str}, Signature={signature}"
            ),
        }

    @staticmethod
    def _norm_query(params):
        """规范化查询参数（RFC 3986 编码，按键排序）"""
        encode = lambda v: quote(str(v), safe='-_.~') if v is not None else ''
        query_items = []
        for key in sorted(params.keys()):
            values = params[key] if isinstance(params[key], list) else [params[key]]
            for item in values:
                query_items.append(f"{encode(key)}={encode(str(item))}")
        return '&'.join(query_items)

    @staticmethod
    def _hash_sha256(content):
        """SHA256 哈希"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    @staticmethod
    def _hmac_sha256(key, content):
        """HMAC-SHA256"""
        return hmac.new(key, content.encode('utf-8'), hashlib.sha256).digest()

    @classmethod
    def get_provider_name(cls):
        """返回服务商名称"""
        return "火山云"
