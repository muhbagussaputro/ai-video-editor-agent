from shared.router_client import RouterClient
from shared.viral_editorial import analyze_viral_hooks
import json
import os

# Credentials come from ignored `.env` / runtime environment. Never hardcode keys here.
os.environ.setdefault("LLM_PROVIDER", "9router")
os.environ.setdefault("LLM_MODEL", "ag/gemini-pro-agent")

transcript = """
Gua itu dulu ketika mulai, ketika gua mulai mengimpor barang dari Cina, gua itu mikir berkali-kali gitu loh. Kalau ini gagal gimana? Kalau ini gagal gimana? Gua gua jarang mikir kalau ini berhasil seperti apa. Gua jarang balik ya, framework otak gua seperti itu. Karena gua kepikiran kalau gua sampai gagal waktu itu, nyokap gua enggak punya tempat tinggal dan enggak bisa makan. Jadi untuk kita memiliki drive dan kita bisa mulai ya, ini akan ada satu kata di sini ya yang gua pengen terapin ke kalian. Kata-katanya adalah diligence ya. Ini banyak yang enggak paham artinya apa. Gua tidak akan bilang kerja keras ya. Menurut gua ini kata-kata yang kurang lengkap karena banyak orang lebih kerja keras dibanding gua. Even hari ini banyak yang lebih kerja keras dari gua, tapi mereka enggak bisa jadi kaya karena ini bukanlah rahasia untuk jadi kaya ya. Tukang sapu di bawah tuh kerja keras. Semua ojol yang kalian lihat itu mungkin hari ini lebih kerja keras dari gua. Mereka dari pagi nangkring sampai siang itu cuma dapat satu orderan. Kerja keras itu bukanlah rahasia untuk jadi kaya. Rahasia untuk jadi kaya itu kata-katanya adalah diligence.
"""

client = RouterClient()
res = analyze_viral_hooks(client, transcript, target_duration=60, min_duration=30, max_duration=90, candidate_count=1)
print(json.dumps(res, indent=2))
