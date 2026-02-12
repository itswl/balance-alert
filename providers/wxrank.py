"""
微信排名积分查询适配器
"""
from .base import BaseProvider
import re


class WxRankProvider(BaseProvider):
    """微信排名服务适配器"""
    
    API_URL = "http://data.wxrank.com/weixin/score"
    
    def __init__(self, api_key):
        """
        初始化 WxRank 适配器
        
        Args:
            api_key: WxRank API 密钥
        """
        super().__init__(api_key)
    
    def get_credits(self):
        """
        获取当前积分
        
        Returns:
            dict: 包含以下字段的字典
                - success (bool): 是否成功获取
                - credits (float): 积分数值，失败时为 None
                - error (str): 错误信息，成功时为 None
                - raw_data (dict): 原始 API 响应数据
        """
        try:
            # 使用基类的请求方法
            response = self._make_request(
                'GET',
                self.API_URL,
                params={'key': self.api_key}
            )
            
            # 使用基类的响应处理方法
            result = self._handle_response(response)
            if not result['success']:
                return result
            
            data = result['raw_data']
            
            # 检查返回码
            if data.get('code') != 0:
                error_msg = data.get('msg', '未知错误')
                return {
                    'success': False,
                    'credits': None,
                    'error': f"API 返回错误: {error_msg}",
                    'raw_data': data
                }
            
            # 从 msg 字段中提取积分数字
            # 格式: "剩余263419积分"
            msg = data.get('msg', '')
            
            # 尝试多种方式提取积分
            credits = None
            
            # 方法1: 正则提取数字
            match = re.search(r'(\d+)', msg)
            if match:
                credits = float(match.group(1))
            
            # 方法2: 尝试直接从 data 字段获取
            if credits is None and 'data' in data:
                if isinstance(data['data'], (int, float)):
                    credits = float(data['data'])
                elif isinstance(data['data'], dict):
                    credits = data['data'].get('score') or data['data'].get('credits')
            
            # 方法3: 尝试从 score 字段获取
            if credits is None:
                credits = data.get('score') or data.get('credits')
            
            if credits is None:
                return {
                    'success': False,
                    'credits': None,
                    'error': f"无法从响应中解析积分: {msg}",
                    'raw_data': data
                }
            
            result['credits'] = float(credits)
            return result
            
        except Exception as e:
            return {
                'success': False,
                'credits': None,
                'error': f"未知错误: {str(e)}",
                'raw_data': None
            }
    
    @classmethod
    def get_provider_name(cls):
        """返回服务商名称"""
        return "WxRank"
