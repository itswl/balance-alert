"""
余额监控适配器模块
支持多个服务商的余额查询
"""

from .openrouter import OpenRouterProvider
from .wxrank import WxRankProvider
from .volc import VolcProvider
from .aliyun import AliyunProvider

# 可用的服务商适配器映射
PROVIDERS = {
    'openrouter': OpenRouterProvider,
    'wxrank': WxRankProvider,
    'volc': VolcProvider,
    'aliyun': AliyunProvider,
    # 后续添加其他服务商:
    # 'openai': OpenAIProvider,
    # 'anthropic': AnthropicProvider,
}

def get_provider(provider_name):
    """根据服务商名称获取适配器类"""
    provider_class = PROVIDERS.get(provider_name)
    if not provider_class:
        raise ValueError(f"未知的服务商: {provider_name}. 支持的服务商: {list(PROVIDERS.keys())}")
    return provider_class
