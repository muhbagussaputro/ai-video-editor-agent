with open("shared/viral_editorial.py", "r") as f:
    content = f.read()

import re

# Update prompt to strictly enforce hook_text generation and use 5-word logic if missing
content = re.sub(
    r'- hook_text may be a short truthful on-screen headline, max 12 words\.',
    r'- hook_text MUST NOT BE EMPTY. Generate a short, punchy, truthful on-screen headline, max 12 words. Do NOT leave this blank. Create a strong POV or headline text that triggers curiosity.',
    content
)

with open("shared/viral_editorial.py", "w") as f:
    f.write(content)
print("Patched viral_editorial.py prompt!")
