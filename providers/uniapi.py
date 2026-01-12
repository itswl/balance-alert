"""
UniAPI 积分查询适配器
"""
import requests


class UniAPIProvider:
    """UniAPI 服务商适配器"""
    
    API_URL = "https://api.uniapi.io/v1/billing/usage"
    
    def __init__(self, api_key):
        """
        初始化 UniAPI 适配器
        
        Args:
            api_key: UniAPI API 密钥
        """
        self.api_key = api_key
    
    def get_credits(self):
        """
        获取当前积分
        
        UniAPI 积分计算方式: balance (可用积分)
        
        Returns:
            dict: 包含以下字段的字典
                - success (bool): 是否成功获取
                - credits (float): 积分数值，失败时为 None
                - error (str): 错误信息，成功时为 None
                - raw_data (dict): 原始 API 响应数据
        """
        try:
            response = requests.get(
                self.API_URL,
                params={"unit": "usd"},
                headers={
                    "Authorization": f"Bearer {self.api_key}"
                },
                timeout=10
            )
            
            if response.status_code != 200:
                return {
                    'success': False,
                    'credits': None,
                    'error': f"API 请求失败: HTTP {response.status_code}",
                    'raw_data': response.text
                }
            
            data = response.json()
            
            # UniAPI 返回的数据结构
            # {
            #   "data": {
            #     "balance": 10446.054266,
            #     "used": 48280.241632,
            #     "cache_used": 0
            #   },
            #   "success": true
            # }
            
            # 检查 API 是否返回成功
            if not data.get('success'):
                return {
                    'success': False,
                    'credits': None,
                    'error': "API 返回 success=false",
                    'raw_data': data
                }
            
            # 获取积分数据
            balance_data = data.get('data', {})
            balance = balance_data.get('balance')
            
            # 验证必要字段是否存在
            if balance is None:
                return {
                    'success': False,
                    'credits': None,
                    'error': "无法从响应中解析 balance 字段",
                    'raw_data': data
                }
            
            # 返回可用积分
            return {
                'success': True,
                'credits': float(balance),
                'error': None,
                'raw_data': data
            }
            
        except requests.exceptions.Timeout:
            return {
                'success': False,
                'credits': None,
                'error': "请求超时",
                'raw_data': None
            }
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'credits': None,
                'error': f"网络请求错误: {str(e)}",
                'raw_data': None
            }
        except ValueError as e:
            return {
                'success': False,
                'credits': None,
                'error': f"数据类型转换错误: {str(e)}",
                'raw_data': None
            }
        except Exception as e:
            return {
                'success': False,
                'credits': None,
                'error': f"未知错误: {str(e)}",
                'raw_data': None
            }
    
    @staticmethod
    def get_provider_name():
        """返回服务商名称"""
        return "UniAPI"
