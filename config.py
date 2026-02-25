import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    bot_token: str
    owner_id: int

def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is missing in .env")
    owner_id = int(os.getenv("OWNER_ID", "0"))
    return Config(bot_token=token, owner_id=owner_id)
