#!/usr/bin/env python3
"""
Swagger/OpenAPI 配置

提供 API 文档的配置和模板
"""

SWAGGER_CONFIG = {
    "headers": [],
    "specs": [
        {
            "endpoint": 'apispec',
            "route": '/apispec.json',
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/api/docs"
}

SWAGGER_TEMPLATE = {
    "swagger": "2.0",
    "info": {
        "title": "Balance Alert API",
        "description": "余额与积分监控系统 API 文档",
        "version": "2.0.0",
        "contact": {
            "name": "Balance Alert",
            "url": "https://github.com/itswl/balance-alert"
        }
    },
    "host": "localhost:8080",
    "basePath": "/",
    "schemes": [
        "http",
        "https"
    ],
    "securityDefinitions": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": "JWT 访问令牌，格式: Bearer <token>"
        },
        "ApiKey": {
            "type": "apiKey",
            "name": "api_key",
            "in": "query",
            "description": "API Key 认证（向后兼容）"
        }
    },
    "tags": [
        {
            "name": "余额监控",
            "description": "项目余额和积分查询相关接口"
        },
        {
            "name": "订阅管理",
            "description": "订阅续费管理相关接口"
        },
        {
            "name": "邮箱管理",
            "description": "邮箱配置管理相关接口"
        },
        {
            "name": "系统",
            "description": "系统健康检查和监控相关接口"
        },
        {
            "name": "认证",
            "description": "用户认证相关接口"
        }
    ]
}

# API 响应示例
API_RESPONSES = {
    "200": {
        "description": "成功"
    },
    "400": {
        "description": "请求参数错误",
        "schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "example": "error"
                },
                "message": {
                    "type": "string",
                    "example": "请求参数验证失败"
                },
                "errors": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    }
                }
            }
        }
    },
    "401": {
        "description": "未授权",
        "schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "example": "error"
                },
                "message": {
                    "type": "string",
                    "example": "未授权访问"
                }
            }
        }
    },
    "404": {
        "description": "资源不存在"
    },
    "429": {
        "description": "请求过于频繁"
    },
    "500": {
        "description": "服务器内部错误"
    },
    "503": {
        "description": "服务不可用"
    }
}
