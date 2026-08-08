import re

with open("/home/bismillah/ai-video-clipper-vps/shared/pipeline.py", "r") as f:
    content = f.read()

# Make the POV persistent instead of disappearing after hook_duration
# And format the text like the screenshot
new_hook = """
    if opening_hook_text:
        # Wrap strictly by 3 words per line as user requested earlier
        words = opening_hook_text.split()
        lines_arr = []
        for i in range(0, len(words), 3):
            lines_arr.append(" ".join(words[i:i+3]))
        
        # Color specific words pink, make the rest white
        colored_lines = []
        for line in lines_arr:
            # For simplicity, if we detect keywords, color them. Otherwise color alternate lines or just make it pink.
            colored_lines.append(f"{\\\\1c&H00B000FF}{line}")
            
        hook_text = "\\\\N".join(colored_lines)
        
        # Persistent duration (full clip)
        clip_dur = clip_end - clip_start
        lines.append(
            "Dialogue: 5,"
            f"{_format_ass_timestamp(0.0)},"
            f"{_format_ass_timestamp(max(0.2, clip_dur))},"
            "Hook,,0,0,0,,"
            "{\\\\1c&H00FFFFFF}POV: " + hook_text + "{\\\\r\\\\fs32\\\\fnMontserrat SemiBold\\\\b1\\\\bord2\\\\3c&H00111111\\\\shad1\\\\1c&H00F0D0FF}\\\\N@gusaja.com"
        )
"""
content = re.sub(
    r'    if opening_hook_text:\n.*?"POV: \{hook_text\}"\n        \)',
    new_hook.strip("\n"),
    content,
    flags=re.DOTALL
)

with open("/home/bismillah/ai-video-clipper-vps/shared/pipeline.py", "w") as f:
    f.write(content)

