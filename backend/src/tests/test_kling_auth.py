import time
import jwt
import os
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file
ak = os.getenv("KLING_ACCESS_KEY")
sk = os.getenv("KLING_SECRET_KEY")


def encode_jwt_token(ak, sk):
    headers = {
        "alg": "HS256",
        "typ": "JWT"
    }
    payload = {
        "iss": ak,
        # The valid time, in this example, represents the current time+1800s(30min)
        "exp": int(time.time()) + 1800,
        # The time when it starts to take effect, in this example, represents the current time -5s
        "nbf": int(time.time()) - 5
    }
    token = jwt.encode(payload, sk, headers=headers)
    return token


authorization = encode_jwt_token(ak, sk)
print(authorization)  # Printing the generated API_TOKEN
