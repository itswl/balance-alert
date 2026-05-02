import requests

# Webhook 配置
WEBHOOK_URL = "http://localhost:8000/webhook"
CREDIT_THRESHOLD = 10000

# Get remaining credits (GET /credits)
response = requests.get(
  "https://openrouter.ai/api/v1/credits",
  headers={
    "Authorization": "Bearer sk-or-v1-xxx"
  },
)

data = response.json()
print(f"当前余额信息: {data}")

# 检查余额
if response.status_code == 200:
    # OpenRouter 返回的余额信息可能在 'total_credits' 或其他字段中
    # 根据实际返回的数据结构调整
    credits = data.get('data', {}).get('total_credits', 0)
    
    # 如果数据结构不同，尝试其他可能的字段
    if credits == 0:
        credits = data.get('total_credits', 0)
    if credits == 0:
        credits = data.get('credits', 0)
    
    print(f"当前余额: {credits}")
    
    # 如果余额低于阈值，发送 webhook
    if credits < CREDIT_THRESHOLD:
        print(f"⚠️  余额不足! 当前余额 {credits} 低于阈值 {CREDIT_THRESHOLD}")
        
        webhook_data = {
            "Type": "AlarmNotification",
            "RuleName": "OpenRouter余额告警",
            "Level": "critical",
            "Resources": [
                {
                    "Service": "OpenRouter",
                    "CurrentCredits": credits,
                    "Threshold": CREDIT_THRESHOLD,
                    "Message": f"余额不足，当前余额: {credits}"
                }
            ]
        }
        
        try:
            webhook_response = requests.post(
                WEBHOOK_URL,
                json=webhook_data,
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Source": "openrouter-monitor"
                }
            )
            
            if webhook_response.status_code == 200:
                print("✅ Webhook 发送成功!")
            else:
                print(f"❌ Webhook 发送失败: {webhook_response.status_code}")
                print(webhook_response.text)
        except Exception as e:
            print(f"❌ 发送 Webhook 时出错: {e}")
    else:
        print(f"✅ 余额充足: {credits} >= {CREDIT_THRESHOLD}")
else:
    print(f"❌ 获取余额失败: {response.status_code}")
    print(response.text)
