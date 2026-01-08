"""
OpenRouter 余额查询适配器
"""
import requests


class OpenRouterProvider:
    """OpenRouter 服务商适配器"""
    
    API_URL = "https://openrouter.ai/api/v1/credits"
    
    def __init__(self, api_key):
        """
        初始化 OpenRouter 适配器
        
        Args:
            api_key: OpenRouter API 密钥
        """
        self.api_key = api_key
    
    def get_credits(self):
        """
        获取当前余额
        
        OpenRouter 余额计算方式: total_credits - total_usage
        
        Returns:
            dict: 包含以下字段的字典
                - success (bool): 是否成功获取
                - credits (float): 余额数值，失败时为 None
                - error (str): 错误信息，成功时为 None
                - raw_data (dict): 原始 API 响应数据
        """
        try:
            response = requests.get(
                self.API_URL,
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
            
            # OpenRouter 返回的数据结构
            # {
            #   "data": {
            #     "total_credits": 100.5,
            #     "total_usage": 25.75
            #   }
            # }
            # 或者直接：
            # {
            #   "total_credits": 100.5,
            #   "total_usage": 25.75
            # }
            
            # 尝试从不同层级获取数据
            credits_data = data.get('data', data)
            
            total_credits = credits_data.get('total_credits')
            total_usage = credits_data.get('total_usage')
            
            # 验证必要字段是否存在
            if total_credits is None:
                return {
                    'success': False,
                    'credits': None,
                    'error': "无法从响应中解析 total_credits 字段",
                    'raw_data': data
                }
            
            if total_usage is None:
                return {
                    'success': False,
                    'credits': None,
                    'error': "无法从响应中解析 total_usage 字段",
                    'raw_data': data
                }
            
            # 计算可用余额 = 总积分 - 已使用积分
            available_credits = float(total_credits) - float(total_usage)
            
            return {
                'success': True,
                'credits': available_credits,
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
        return "OpenRouter"
