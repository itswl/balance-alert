"""
火山云余额查询适配器
"""
from .base import BaseProvider
import datetime
import hashlib
import hmac
from urllib.parse import quote
import json


class VolcProvider(BaseProvider):
    """火山云服务适配器"""
    
    def __init__(self, api_key):
        """
        初始化火山云适配器
        
        Args:
            api_key: 格式为 "AK:SK" 的密钥对，用冒号分隔
                    例如: "AKLTxxx:TmpCa01xxx"
        """
        if ':' not in api_key:
            raise ValueError("火山云 API Key 格式错误，应为 'AK:SK' 格式")
        
        super().__init__(api_key)
        self.ak, self.sk = api_key.split(':', 1)
        self.service = 'billing'
        self.action = 'QueryBalanceAcct'
        self.version = '2022-01-01'
        self.region = 'cn-shanghai'
        self.host = 'open.volcengineapi.com'
        self.content_type = 'application/json'
    
    def get_credits(self):
        """
        获取当前余额
        
        Returns:
            dict: 包含以下字段的字典
                - success (bool): 是否成功获取
                - credits (float): 余额数值，失败时为 None
                - error (str): 错误信息，成功时为 None
                - raw_data (dict): 原始 API 响应数据
        """
        try:
            response_data = self._send_request()
            
            if not response_data:
                return {
                    'success': False,
                    'credits': None,
                    'error': "API 返回空响应",
                    'raw_data': None
                }
            
            # 检查响应中的错误
            if response_data.get('ResponseMetadata', {}).get('Error'):
                error_info = response_data['ResponseMetadata']['Error']
                return {
                    'success': False,
                    'credits': None,
                    'error': f"API 返回错误: {error_info}",
                    'raw_data': response_data
                }
            
            # 获取可用余额
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
            # 处理各种网络异常
            error_msg = str(e)
            if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                return {
                    'success': False,
                    'credits': None,
                    'error': "请求超时",
                    'raw_data': None
                }
            elif "connection" in error_msg.lower() or "connect" in error_msg.lower():
                return {
                    'success': False,
                    'credits': None,
                    'error': f"网络连接错误: {error_msg}",
                    'raw_data': None
                }
            else:
                return {
                    'success': False,
                    'credits': None,
                    'error': f"未知错误: {error_msg}",
                    'raw_data': None
                }
    
    def _send_request(self):
        """发送火山云 API 请求"""
        now = datetime.datetime.now(datetime.UTC)
        body = ''
        
        request_params = {
            'body': body,
            'host': self.host,
            'path': '/',
            'method': 'GET',
            'content_type': self.content_type,
            'date': now,
            'query': {'Action': self.action, 'Version': self.version}
        }
        
        headers = self._build_headers(request_params)
        response = self._make_volc_request(request_params, headers)
        
        if response.status_code != 200:
            raise Exception(f'HTTP请求失败，状态码：{response.status_code}\n响应内容：{response.text}')
        
        if not response.text.strip():
            return {}
        
        try:
            return response.json()
        except json.JSONDecodeError:
            raise Exception(f'响应内容不是有效的JSON格式：{response.text}')
    
    def _build_headers(self, request_params):
        """构建请求头"""
        x_date = request_params['date'].strftime('%Y%m%dT%H%M%SZ')
        short_date = x_date[:8]
        content_sha256 = self._hash_sha256(request_params['body'])
        
        headers = {
            'Host': request_params['host'],
            'X-Content-Sha256': content_sha256,
            'X-Date': x_date,
            'Content-Type': request_params['content_type']
        }
        
        signature = self._calculate_signature(request_params, x_date, short_date, content_sha256)
        headers['Authorization'] = self._build_authorization_header(short_date, signature)
        
        return headers
    
    def _calculate_signature(self, request_params, x_date, short_date, content_sha256):
        """计算签名"""
        signed_headers = ['content-type', 'host', 'x-content-sha256', 'x-date']
        signed_headers_str = ';'.join(signed_headers)
        
        canonical_request = self._build_canonical_request(
            request_params, content_sha256, x_date, signed_headers_str
        )
        hashed_canonical_request = self._hash_sha256(canonical_request)
        
        credential_scope = f"{short_date}/{self.region}/{self.service}/request"
        string_to_sign = f"HMAC-SHA256\n{x_date}\n{credential_scope}\n{hashed_canonical_request}"
        
        k_date = self._hmac_sha256(self.sk.encode('utf-8'), short_date)
        k_region = self._hmac_sha256(k_date, self.region)
        k_service = self._hmac_sha256(k_region, self.service)
        k_signing = self._hmac_sha256(k_service, 'request')
        
        return self._hmac_sha256(k_signing, string_to_sign).hex()
    
    def _build_canonical_request(self, request_params, content_sha256, x_date, signed_headers_str):
        """构建规范请求"""
        canonical_headers = [
            f"content-type:{request_params['content_type']}",
            f"host:{request_params['host']}",
            f"x-content-sha256:{content_sha256}",
            f"x-date:{x_date}"
        ]
        
        return '\n'.join([
            request_params['method'].upper(),
            request_params['path'],
            self._norm_query(request_params['query']),
            '\n'.join(canonical_headers),
            '',
            signed_headers_str,
            content_sha256
        ])
    
    def _build_authorization_header(self, short_date, signature):
        """构建授权头"""
        credential_scope = f"{short_date}/{self.region}/{self.service}/request"
        return f"HMAC-SHA256 Credential={self.ak}/{credential_scope}, SignedHeaders=content-type;host;x-content-sha256;x-date, Signature={signature}"
    
    def _make_volc_request(self, request_params, headers):
        """发起 HTTP 请求"""
        url = f"https://{request_params['host']}{request_params['path']}?{self._norm_query(request_params['query'])}"
        return self.session.request(
            method=request_params['method'],
            url=url,
            headers=headers,
            data=request_params['body'],
            timeout=self.timeout
        )
    
    @staticmethod
    def _norm_query(params):
        """规范化查询参数"""
        query_items = []
        for key in sorted(params.keys()):
            if isinstance(params[key], list):
                for item in params[key]:
                    query_items.append(f"{quote(key, safe='-_.~')}={quote(str(item), safe='-_.~')}")
            else:
                query_items.append(f"{quote(key, safe='-_.~')}={quote(str(params[key]), safe='-_.~')}")
        return '&'.join(query_items).replace('+', '%20')
    
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
