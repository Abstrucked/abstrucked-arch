#!/BIN/BASH

# ~/load-api-keys.sh
export XAI_API_KEY=$(pass ai/xai_api_key)
export OPENAI_API_KEY=$(pass ai/openai_api_key)
export ANTHROPIC_API_KEY=$(pass ai/anthropic_api_key)
export GEMINI_API_KEY=$(pass ai/gemini_api_key)
export TAVILY_API_KEY=$(pass ai/tavily_api_key)
export CONTEXT7_API_KEY=$(pass ai/context7)
export OPENROUTER_API_KEY=$(pass ai/openrouter_api_key)
