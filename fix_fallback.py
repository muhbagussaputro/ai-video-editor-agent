import re

with open("/home/bismillah/ai-video-clipper-vps/shared/pipeline.py", "r") as f:
    content = f.read()

# Remove the fallback `if highlight.hook_text else " ".join(highlight.quote.split()[:5])`
content = content.replace(
    'opening_hook_text=highlight.hook_text if highlight.hook_text else " ".join(highlight.quote.split()[:5]),',
    'opening_hook_text=highlight.hook_text,'
)

with open("/home/bismillah/ai-video-clipper-vps/shared/pipeline.py", "w") as f:
    f.write(content)

