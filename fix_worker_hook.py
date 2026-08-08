import re

with open("/home/bismillah/ai-video-clipper-vps/shared/pipeline.py", "r") as f:
    content = f.read()

# Let's ensure that hook_text is ALWAYS extracted properly and defaults to a 5-word fallback
# ONLY IF the LLM actually returns empty. The issue is that the precomputed LLM results
# are probably missing `hook_text` entirely, or we need to apply the fallback in `_llm_highlights`

