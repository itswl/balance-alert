"""
阿里云余额查询适配器
"""
from .base import BaseProvider
import datetime
import hashlib
import hmac
import base64
import json
import uuid
from urllib.parse import quote


class AliyunProvider(BaseProvider):
    """阿里云服务适配器"""
    
    def __init__(self, api_key):
        """
        初始化阿里云适配器
        
        Args:
            api_key: 格式为 "AccessKeyId:AccessKeySecret" 的密钥对，用冒号分隔
        """
        if ':' not in api_key:
            raise ValueError("阿里云 API Key 格式错误，应为 'AccessKeyId:AccessKeySecret' 格式")
        
        super().__init__(api_key)
        self.access_key_id, self.access_key_secret = api_key.split(':', 1)
        self.endpoint = 'business.aliyuncs.com'
        self.action = 'QueryAccountBalance'
        self.version = '2017-12-14'
    
    def get_credits(self):
        """获取当前余额；阿里云不同版本接口的返回结构不一，解析放在 _extract_amount 里"""
        try:
            response = self._send_request()
            if not response:
                return self._result(False, None, "API 返回空响应", None)
            amount, error = self._extract_amount(response)
            if error:
                return self._result(False, None, error, response)
            return self._result(True, amount, None, response)
        except Exception as e:
            return self._classify_exception(e)

    @staticmethod
    def _result(success, credits, error, raw_data):
        return {'success': success, 'credits': credits, 'error': error, 'raw_data': raw_data}

    @staticmethod
    def _extract_amount(response):
        """返回 (余额, 错误消息)；兼容带 Code 的标准结构与直接返回余额字段的旧结构"""
        code = response.get('Code')
        if code is not None and code not in ('Success', 200) and str(code) != '200':
            return None, f"API 返回错误: {response.get('Message', '未知错误')} (Code: {code})"

        data = response.get('Data') or {}
        candidates = (
            data.get('AvailableAmount'),
            response.get('AvailableAmount'),
            response.get('AvailableCashAmount'),
            data.get('AvailableCashAmount'),
        )
        amount = next((value for value in candidates if value is not None), None)
        if amount is None:
            return None, f"无法从响应中解析余额字段，响应内容: {response}"
        if isinstance(amount, str):
            amount = amount.replace(',', '')  # 去掉千位分隔符
        return float(amount), None

    def _send_request(self):
        """发送阿里云 API 请求"""
        # 构建请求参数
        params = {
            'Action': self.action,
            'Version': self.version,
            'AccessKeyId': self.access_key_id,
            'SignatureMethod': 'HMAC-SHA1',
            'Timestamp': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'SignatureVersion': '1.0',
            'SignatureNonce': str(uuid.uuid4()),
            'Format': 'JSON'
        }
        
        # 计算签名
        signature = self._calculate_signature(params)
        params['Signature'] = signature
        
        # 发起请求
        url = f"https://{self.endpoint}"
        
        try:
            # 使用基类的请求方法
            response = self._make_request('GET', url, params=params)
            return response.json()
        except json.JSONDecodeError:
            raise Exception(f'响应内容不是有效的JSON格式：{response.text}')
    
    def _calculate_signature(self, params):
        """计算阿里云 API 签名"""
        # 1. 对参数排序
        sorted_params = sorted(params.items())
        
        # 2. 构建规范化查询字符串
        canonicalized_query_string = '&'.join([
            f"{self._percent_encode(k)}={self._percent_encode(str(v))}"
            for k, v in sorted_params
        ])
        
        # 3. 构建待签名字符串
        string_to_sign = f"GET&{self._percent_encode('/')}&{self._percent_encode(canonicalized_query_string)}"
        
        # 4. 计算 HMAC-SHA1 签名
        h = hmac.new(
            (self.access_key_secret + '&').encode('utf-8'),
            string_to_sign.encode('utf-8'),
            hashlib.sha1
        )
        signature = base64.b64encode(h.digest()).decode('utf-8')
        
        return signature
    
    @staticmethod
    def _percent_encode(s):
        """阿里云签名要求的百分号编码变体"""
        if s is None:
            return ''
        encoded = quote(str(s), safe='')
        return encoded.replace('+', '%20').replace('*', '%2A').replace('%7E', '~')
    
    @classmethod
    def get_provider_name(cls):
        """返回服务商名称"""
        return "阿里云"
