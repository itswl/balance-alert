"""
TikHub 余额查询适配器
"""
from .base import BaseProvider


class TikHubProvider(BaseProvider):
    """TikHub 服务商适配器"""
    
    API_URL = "https://api.tikhub.dev/api/v1/tikhub/user/get_user_info"
    
    def __init__(self, api_key):
        """
        初始化 TikHub 适配器
        
        Args:
            api_key: TikHub API 密钥 (Token)
        """
        super().__init__(api_key)
    
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
            # 使用基类的请求方法
            response = self._make_request(
                'GET',
                self.API_URL,
                headers={
                    "accept": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                }
            )
            
            # 使用基类的响应处理方法
            result = self._handle_response(response)
            if not result['success']:
                return result
            
            data = result['raw_data']
            
            # TikHub 返回的数据结构可能在 user_data 或 data 字段中
            # {
            #   "code": 200,
            #   "user_data": {
            #     "balance": 100.0,
            #     ...
            #   }
            # }
            
            # 兼容性处理：尝试从不同层级获取 balance
            user_data = data.get('user_data', data.get('data', data))
            balance = user_data.get('balance')
            
            # 验证必要字段是否存在
            if balance is None:
                return {
                    'success': False,
                    'credits': None,
                    'error': "无法从响应中解析 balance 字段",
                    'raw_data': data
                }
            
            result['credits'] = float(balance)
            return result
            
        except ValueError as e:
            return {
                'success': False,
                'credits': None,
                'error': f"数据解析或类型转换错误: {str(e)}",
                'raw_data': None
            }
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
        return "TikHub"
