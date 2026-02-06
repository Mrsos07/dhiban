"""
إعدادات وكيل الذكاء الاصطناعي
"""
import os
from django.conf import settings


# OpenAI Configuration
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')

# Agent Configuration
AGENT_CONFIG = {
    "model": OPENAI_MODEL,
    "api_key": OPENAI_API_KEY,
    "temperature": 0.7,
    "max_tokens": 1000,
}

# LLM Config for AutoGen
LLM_CONFIG = {
    "config_list": [
        {
            "model": OPENAI_MODEL,
            "api_key": OPENAI_API_KEY,
        }
    ],
    "temperature": 0.7,
    "timeout": 120,
}
