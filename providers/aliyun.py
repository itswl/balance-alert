"""
阿里云余额查询适配器
"""
from .base import BaseProvider
import datetime
import hashlib
import hmac
import base64
from urllib.parse import quote
import json
import uuid


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
            response = self._send_request()
            
            # 检查响应状态
            if not response:
                return {
                    'success': False,
                    'credits': None,
                    'error': "API 返回空响应",
                    'raw_data': None
                }
            
            # 阿里云可能返回不同的格式，尝试多种解析方式
            
            # 方式1: 检查是否有 Code 字段
            if 'Code' in response:
                # Code 可能是 'Success' 或者是 HTTP 状态码 200
                code = response.get('Code')
                if code != 'Success' and code != 200 and str(code) != '200':
                    error_msg = response.get('Message', '未知错误')
                    return {
                        'success': False,
                        'credits': None,
                        'error': f"API 返回错误: {error_msg} (Code: {response.get('Code')})",
                        'raw_data': response
                    }
                # 获取余额
                data = response.get('Data', {})
                available_amount = data.get('AvailableAmount')
            else:
                # 方式2: 直接从响应中获取 AvailableAmount
                available_amount = response.get('AvailableAmount')
                
                # 方式3: 从 Data 字段获取
                if available_amount is None:
                    data = response.get('Data', {})
                    available_amount = data.get('AvailableAmount')
                
                # 方式4: 从 AvailableCashAmount 获取
                if available_amount is None:
                    available_amount = response.get('AvailableCashAmount')
                    if available_amount is None:
                        available_amount = response.get('Data', {}).get('AvailableCashAmount')
            
            if available_amount is None:
                return {
                    'success': False,
                    'credits': None,
                    'error': f"无法从响应中解析余额字段，响应内容: {response}",
                    'raw_data': response
                }
            
            # 处理余额格式，移除千位分隔符
            if isinstance(available_amount, str):
                available_amount = available_amount.replace(',', '')
            
            return {
                'success': True,
                'credits': float(available_amount),
                'error': None,
                'raw_data': response
            }
            
        except Exception as e:
            return self._classify_exception(e)
    
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
        """URL 编码（阿里云特殊编码规则）"""
        if s is None:
            return ''
        s = str(s)
        # 先进行标准 URL 编码
        encoded = quote(s, safe='')
        # 替换特殊字符
        encoded = encoded.replace('+', '%20')
        encoded = encoded.replace('*', '%2A')
        encoded = encoded.replace('%7E', '~')
        return encoded
    
    @classmethod
    def get_provider_name(cls):
        """返回服务商名称"""
        return "阿里云"
