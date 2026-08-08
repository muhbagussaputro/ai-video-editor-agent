import re

with open("/home/bismillah/ai-video-clipper-vps/shared/pipeline.py", "r") as f:
    content = f.read()

# Update the prompt in _llm_highlights
new_prompt = """
    prompt = (
        f"Pilih {int(highlight_count)} highlight paling kuat dari transkrip berikut. "
        "Balas HANYA JSON valid tanpa markdown, dengan key utama highlights yang berisi array object. "
        "Setiap object wajib punya key: highlight_quote, hook_text, reason, score. "
        "- hook_text MUST NOT BE EMPTY. Generate a short, punchy, truthful on-screen headline, max 12 words. Do NOT leave this blank. Create a strong POV or headline text that triggers curiosity.\\n"
        f"Pilih highlight viral dengan durasi final fleksibel, bisa pendek bila memang sudah kuat, dan boleh sampai {int(max_duration)} detik, dengan durasi ideal sekitar {int(target_duration)} detik. "
        "Pilih kutipan yang benar-benar ada di transkrip dan jangan ubah kata-katanya. "
        "Setiap highlight harus berbeda, tidak tumpang tindih idenya, dan urutkan dari yang paling viral.\\n\\n"
        f"TRANSKRIP:\\n{transcript_text}"
    )
"""

content = re.sub(
    r'prompt = \(\s*f"Pilih \{int\(highlight_count\)\} highlight paling kuat dari transkrip berikut\..*?f"TRANSKRIP:\\n\{transcript_text\}"\s*\)',
    new_prompt.strip(),
    content,
    flags=re.DOTALL
)

# Put back the fallback
content = content.replace(
    'opening_hook_text=highlight.hook_text,',
    'opening_hook_text=highlight.hook_text if highlight.hook_text else " ".join(highlight.quote.split()[:5]),'
)

with open("/home/bismillah/ai-video-clipper-vps/shared/pipeline.py", "w") as f:
    f.write(content)

