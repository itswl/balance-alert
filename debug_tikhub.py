import requests
import json

API_URL = "https://api.tikhub.io/api/v1/tikhub/user/get_user_info"
API_KEY = "mKMARFp0wXwRuBcc1GeOu2o61yM9t5fai6hFnDrKiXF5wkk+TtV12wK6Vw=="

def debug_tikhub():
    try:
        response = requests.get(
            API_URL,
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {API_KEY}"
            },
            timeout=10
        )
        print(f"Status Code: {response.status_code}")
        print("Response Body:")
        data = response.json()
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_tikhub()
