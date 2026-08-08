import re

with open("/home/bismillah/ai-video-clipper-vps/shared/pipeline.py", "r") as f:
    content = f.read()

content = content.replace(
    'hook_text = str(item.get("hook_text", "")).strip()',
    'hook_text = str(item.get("hook_text", "")).strip() or " ".join(quote.split()[:5])'
)

with open("/home/bismillah/ai-video-clipper-vps/shared/pipeline.py", "w") as f:
    f.write(content)

