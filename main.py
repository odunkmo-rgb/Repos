import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiosqlite
import aiohttp
import asyncio
import os
import re
import datetime
import logging
import urllib.parse
from bs4 import BeautifulSoup
from thefuzz import fuzz, process as fuzz_process

# ─── CONFIG ───────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("DISCORD_TOKEN") or os.environ.get("BOT_TOKEN", "")
OWNER_ID  = 1051062390361427988

LOG_SLASH_CHANNEL  = 1507517714833346600
LOG_MODAL_CHANNEL  = 1507518131692765345
LOG_BUTTON_CHANNEL = 1507517998418890822

DB_PATH = "bot/bot.db"
os.makedirs("bot", exist_ok=True)

GROQ_KEY   = os.environ.get("GROQ_API_KEY", "")
GROQ_BASE  = "https://api.groq.com/openai/v1"
GROQ_MODELS = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "llama-3.1-70b-versatile",
]

GEMINI_KEY   = os.environ.get("GEMINI_API_KEY", "")
GEMINI_BASE  = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_MODEL = "gemini-2.0-flash"

OPENROUTER_KEY  = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "meta-llama/llama-3.2-3b-instruct:free"

TOGETHER_KEY = os.environ.get("TOGETHER_API_KEY", "")

def _ai_providers() -> list[tuple[str, str, str]]:
    """Kullanılabilir (api_key, base_url, model) listesini döndürür — önce Groq, sonra Gemini, sonra OpenRouter."""
    providers = []
    if GROQ_KEY:
        for m in GROQ_MODELS:
            providers.append((GROQ_KEY, GROQ_BASE, m))
    if GEMINI_KEY:
        providers.append((GEMINI_KEY, GEMINI_BASE, GEMINI_MODEL))
    if OPENROUTER_KEY:
        providers.append((OPENROUTER_KEY, OPENROUTER_BASE, OPENROUTER_MODEL))
    return providers

AI_SYSTEM_PROMPT = (
    "Sen Mm2 Bot adında Türkçe konuşan bir Discord botusun. "
    "SADECE TÜRKÇE yaz, başka dil kesinlikle yasak.\n"
    "Güncel bilgi için sana '=== WEB ARAMA ===' bölümü verilecek.\n"

    "### !!KURAL 0 — KESİN YASAK (asla ihlal etme) ###\n"
    "Cevabının başında, ortasında veya sonunda ASLA kullanıcı ismi/nicknamei yazma. "
    "Merhaba, hey, selam gibi hitapların arkasına bile isim ekleme. "
    "Sistem bağlamında 'Kullanıcı:' satırı yalnızca bilgi içindir, ASLA yanıtta kullanma. "
    "Doğrudan cevaba gir — tek satır bile olsa isim yok.\n"

    "### KURAL 1 — GERÇEK ZAMANLI VERİ ###\n"
    "Maç sonucu, skor, gol atan, kim kazandı, puan durumu, güncel haberler gibi "
    "GERÇEK ZAMANLI bilgileri YALNIZCA '=== WEB ARAMA ===' bölümünde açıkça yazıyorsa ver. "
    "Web aramada yoksa veya belirsizse şunu de: "
    "'Bu bilgiye şu an ulaşamadım, sporx.com / TFF / UEFA gibi resmi kaynakları kontrol et.' "
    "ASLA tahmin etme, ASLA uydurma, ASLA 'büyük ihtimalle' gibi ifade kullanma. "
    "Web aramada olmayan hiçbir skor, isim, tarih, gol bilgisi SÖYLENEMEZ.\n"

    "### KURAL 2 — SPESIFIK KİŞİ / KURUM BİLGİSİ ###\n"
    "Oyuncu adı, kulüp, antrenör, transfer gibi spesifik bilgileri ASLA tahmin etme. "
    "Emin değilsen 'Bunu doğrulayamadım' de.\n"

    "### KURAL 3 — GENEL KÜLTÜR ###\n"
    "Genel kültür soruları için kendi bilgini kullanabilirsin. "
    "Spor / borsa / haber / anlık fiyat gibi konularda YALNIZCA web arama sonuçlarına güven.\n"

    "### KURAL 5 — KONU İZOLASYONU ###\n"
    "Her soruyu BAĞIMSIZ değerlendir. Önceki konuşmada Türk ordusu konuştuysan "
    "ve şimdi spor soruluyorsa, öncekini UNUTARAK sadece spor sorusuna cevap ver. "
    "Konuları birbirine karıştırma, bağdaştırma. Alakasız bağlantılar kurma.\n"

    "### KURAL 6 — ETİKETLENEN KİŞİ ###\n"
    "Bir kullanıcı etiketlenip hakkında bilgi istenirse SADECE sana verilen "
    "[Profil:] bölümündeki gerçek verileri kullan. "
    "Discord profil bilgisi dışında hiçbir şey uydurma.\n"

    "### KURAL 7 — GÖRSEL ANALİZ ###\n"
    "Kullanıcı bir görsel paylaşırsa önce görseli dikkatle incele, "
    "içindeki nesne/kişi/metin/sahne hakkında somut ve doğru bilgiler ver. "
    "Göremiyorsan 'görseli analiz edemedim' de, uydurma.\n"

    "### KURAL 8 — SAÇMA CEVAP YASAĞI ###\n"
    "Mantıksız, tutarsız veya rastgele cevaplar verme. "
    "Emin olmadığın şeylerde 'bilmiyorum' ya da 'bu konuda yeterli bilgim yok' de. "
    "ASLA gerçek olmayan bir bilgiyi gerçekmiş gibi sunma.\n"

    "### KURAL 4 — MİLLİ DURUŞ & TERÖR YASAĞI ###\n"
    "Türk milletinin değerlerine, birliğine ve bütünlüğüne sahip çık. "
    "PKK, YPG, KCK, FETÖ, DHKP-C, IŞİD/DAEŞ ve benzeri her türlü terör örgütünü, "
    "bölücü yapıyı veya silahlı grubunu ASLA olumlamaz, övmez, haklı göstermezsin. "
    "Bu örgütleri 'özgürlük savaşçısı', 'haklı direniş', 'mağdur', 'kahraman' gibi "
    "ifadelerle nitelendirmek KESİNLİKLE YASAKTIR. "
    "Kürt siyasi meselelerinde tarafsız bilgi verebilirsin; ancak bölücü silahlı "
    "yapıları, PKK/YPG propagandasını veya Türkiye'nin toprak bütünlüğüne karşı "
    "söylemleri destekleyen, meşrulaştıran hiçbir ifade kullanamazsın. "
    "Terör eylemleri, saldırılar, bombalı eylemler ve silahlı isyanlar hakkında "
    "hiçbir şekilde sempati, methiye veya onay içeren cevap veremezsin. "
    "Bu kurala aykırı bir soru geldiğinde kibarca reddet ve konu dışı olduğunu belirt.\n"

    "### GENEL ###\n"
    "Cevap uzunluğunu soruyla orantıla. Emoji kullanabilirsin ama abartma. "
    "Komik durumlarda esprili ol, kaba olma. Kullanıcının istediği konuşma tarzını uygula."
)

import zoneinfo as _zoneinfo
import concurrent.futures as _futures
_thread_pool = _futures.ThreadPoolExecutor(max_workers=4)

_TR_AYLAR = ["Ocak","Şubat","Mart","Nisan","Mayıs","Haziran",
             "Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"]

def _simdi_bilgisi() -> tuple[datetime.datetime, str, str, str]:
    """(simdi, gun_adi, tarih_tr, saat_str) döndürür — Türkiye saatiyle."""
    try:
        tz = _zoneinfo.ZoneInfo("Europe/Istanbul")
        simdi = datetime.datetime.now(tz)
    except Exception:
        simdi = datetime.datetime.utcnow() + datetime.timedelta(hours=3)
    gunler  = ["Pazartesi","Salı","Çarşamba","Perşembe","Cuma","Cumartesi","Pazar"]
    gun_adi = gunler[simdi.weekday()]
    ay_tr   = _TR_AYLAR[simdi.month - 1]
    tarih_tr = f"{simdi.day} {ay_tr} {simdi.year}"          # "13 Haziran 2026"
    saat_str = simdi.strftime("%H:%M")
    return simdi, gun_adi, tarih_tr, saat_str

def _ai_sistem_prompt_olustur(profil_bilgisi: str, stil: str | None = None) -> str:
    """Dinamik sistem promptu: tarih/saat + kullanıcı profili + konuşma stili."""
    _simdi, gun_adi, tarih_tr, saat_str = _simdi_bilgisi()
    prompt = (
        f"Bugün: {gun_adi} {tarih_tr}, saat {saat_str} (Türkiye)\n"
        f"{AI_SYSTEM_PROMPT}\n"
        f"Kullanıcı: {profil_bilgisi}\n"
    )
    if stil:
        prompt += f"Konuşma tarzı: {stil}\n"
    return prompt

# ─── EMOJİ ────────────────────────────────────────────────────────────────────
EMOJI_SLOTS: dict[str, str] = {
    "ara": "🔍", "bagla": "🔗", "envanter": "🎒", "onay": "✅",
    "hata": "❌", "kullanici": "👤", "duyuru": "📢", "istatistik": "📊",
    "guncelle": "🔄", "elmas": "💎", "sunucu": "🌐", "bekle": "⏳",
    "liste": "📋", "ekle": "➕", "ayarlar": "⚙️", "mesaj": "📨",
    "kalkan": "🛡️", "takvim": "📅", "kilit": "🔒", "yildiz": "⭐",
    "roblox": "🎮", "bilgi": "ℹ️", "robot": "🤖",
}
def e(slot: str) -> str:
    return EMOJI_SLOTS.get(slot, "")

# ─── LOGGING ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("MM2Bot")

# ─── STATS ────────────────────────────────────────────────────────────────────
stats = {"commands": 0, "errors": 0, "unauthorized": 0, "success": 0, "servers": {}}

# ─── DÖNEN DURUM ──────────────────────────────────────────────────────────────
_dongu_mesajlar: list[dict] = []   # [{"tip": "watching", "metin": "..."}, ...]
_dongu_index:    int        = 0
_dongu_task:     asyncio.Task | None = None
_son_durum_metin: str = ""          # /durum ile ayarlanan son mesaj
_son_durum_tip:   str = ""          # /durum ile ayarlanan son tip

# ─── AI HAFIZA & STİL ─────────────────────────────────────────────────────────
MAX_AI_HAFIZA = 20
AI_COOLDOWN_SN = 15  # kullanıcı başına saniye cinsinden bekleme süresi
_ai_son_istek: dict[tuple[int, int], float] = {}  # (guild_id, user_id) → timestamp
_ai_isleniyor: set[int] = set()  # mesaj ID'si → çift işlemi engeller

def stats_add(interaction: discord.Interaction, success: bool = True,
              error: bool = False, unauth: bool = False):
    stats["commands"] += 1
    if success:  stats["success"]      += 1
    if error:    stats["errors"]       += 1
    if unauth:   stats["unauthorized"] += 1
    gname = interaction.guild.name if interaction.guild else "DM"
    stats["servers"][gname] = stats["servers"].get(gname, 0) + 1

# ─── BOT SETUP ────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

class MmCommandTree(app_commands.CommandTree):
    """Yapay zeka kanalında slash komutlarını engeller."""
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild and interaction.channel_id:
            ai_ch_id = await get_ai_kanal(interaction.guild_id)
            if ai_ch_id and interaction.channel_id == ai_ch_id:
                await interaction.response.send_message(
                    "❌ Bu kanal yapay zeka sohbet kanalıdır, komutlar burada kullanılamaz.",
                    ephemeral=True,
                )
                return False
        return True

bot  = commands.Bot(command_prefix="!", intents=intents, tree_cls=MmCommandTree)
tree = bot.tree

# ─── DATABASE ─────────────────────────────────────────────────────────────────
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS settings (
                guild_id INTEGER PRIMARY KEY,
                log_channel_id INTEGER,
                yetkili_rol_id TEXT,
                ai_channel_id INTEGER
            );
            CREATE TABLE IF NOT EXISTS roblox_bagla (
                discord_id INTEGER PRIMARY KEY,
                roblox_username TEXT NOT NULL,
                roblox_display_name TEXT,
                roblox_id INTEGER,
                guild_id INTEGER,
                onaylandi INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS envanter (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id INTEGER NOT NULL,
                esya_adi TEXT NOT NULL,
                gorsel_url TEXT,
                eklendi_tarih TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS kullanim_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                guild_id INTEGER,
                komut TEXT,
                tarih TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS hata_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                guild_id INTEGER,
                komut TEXT,
                hata TEXT,
                tarih TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS degerler_cache (
                esya_adi TEXT PRIMARY KEY,
                deger_values REAL,
                deger_supremes REAL,
                gorsel_url TEXT,
                kaynak TEXT,
                guncelleme_tarihi TEXT
            );
        """)
        await db.commit()
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS ai_kullanici_stil (
                guild_id INTEGER NOT NULL,
                user_id  INTEGER NOT NULL,
                stil     TEXT,
                bekliyor INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS ai_hafiza (
                guild_id    INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                mesajlar    TEXT NOT NULL DEFAULT '[]',
                guncellendi TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (guild_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS bot_ayarlari (
                anahtar TEXT PRIMARY KEY,
                deger   TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS kullanici_tercihler (
                discord_id  INTEGER NOT NULL,
                anahtar     TEXT    NOT NULL,
                deger       INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (discord_id, anahtar)
            );
        """)
        await db.commit()
        for migration in [
            "ALTER TABLE roblox_bagla ADD COLUMN roblox_display_name TEXT",
            "ALTER TABLE settings ADD COLUMN ai_channel_id INTEGER",
            "ALTER TABLE degerler_cache ADD COLUMN gorsel_url TEXT",
            "ALTER TABLE degerler_cache ADD COLUMN kaynak TEXT",
            "ALTER TABLE settings ADD COLUMN yetkili_rol_id TEXT",
        ]:
            try:
                await db.execute(migration)
                await db.commit()
            except Exception:
                pass

async def log_usage(interaction: discord.Interaction, komut: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO kullanim_log (user_id, guild_id, komut) VALUES (?, ?, ?)",
            (interaction.user.id, interaction.guild_id, komut))
        await db.commit()

async def log_error(interaction: discord.Interaction, komut: str, hata: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO hata_log (user_id, guild_id, komut, hata) VALUES (?, ?, ?, ?)",
            (interaction.user.id, interaction.guild_id, komut, hata))
        await db.commit()

async def get_yetkili_roller(guild_id: int) -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT yetkili_rol_id FROM settings WHERE guild_id = ?", (guild_id,)
        ) as cur:
            row = await cur.fetchone()
    if not row or not row[0]:
        return []
    return [int(x.strip()) for x in str(row[0]).split(",") if x.strip().isdigit()]

async def is_yetkili(interaction: discord.Interaction) -> bool:
    if interaction.user.id == OWNER_ID:
        return True
    if not interaction.guild:
        return False
    if interaction.user.guild_permissions.administrator:
        return True
    roller = await get_yetkili_roller(interaction.guild_id)
    user_rol_ids = {r.id for r in interaction.user.roles}
    return bool(user_rol_ids & set(roller))

async def get_log_kanal(guild_id: int) -> int | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT log_channel_id FROM settings WHERE guild_id = ?", (guild_id,)
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row and row[0] else None

async def check_log_kanal(interaction: discord.Interaction) -> int | None:
    ch_id = await get_log_kanal(interaction.guild_id)
    if not ch_id:
        await interaction.followup.send(
            f"{e('ayarlar')} Bu komutu kullanabilmek için önce bir yöneticinin "
            "`/yetkili-kanal` komutuyla log kanalını ayarlaması gerekiyor.",
            ephemeral=True)
    return ch_id

async def get_ai_kanal(guild_id: int) -> int | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT ai_channel_id FROM settings WHERE guild_id = ?", (guild_id,)
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row and row[0] else None

# ─── ROBLOX API ───────────────────────────────────────────────────────────────
async def roblox_fetch_profile(roblox_id: int) -> dict:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://users.roblox.com/v1/users/{roblox_id}",
                timeout=aiohttp.ClientTimeout(total=8)
            ) as r:
                if r.status == 200:
                    return await r.json()
    except Exception:
        pass
    return {}

async def roblox_fetch_avatar(roblox_id: int, headshot: bool = False) -> str | None:
    endpoint = "avatar-headshot" if headshot else "avatar"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://thumbnails.roblox.com/v1/users/{endpoint}"
                f"?userIds={roblox_id}&size=420x420&format=Png&isCircular=false",
                timeout=aiohttp.ClientTimeout(total=8)
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    items = data.get("data", [])
                    if items and items[0].get("state") == "Completed":
                        return items[0].get("imageUrl")
    except Exception:
        pass
    return None

# ─── MM2VALUES SCRAPER ────────────────────────────────────────────────────────
def _clean_name(raw: str) -> str:
    """'B a twing' → 'Batwing' gibi hatalı boşlukları düzeltir."""
    # Eğer her karakter arasında boşluk varsa birleştir
    stripped = raw.strip()
    # Pattern: tek harf boşluk tek harf şeklinde tekrar ediyorsa boşukları kaldır
    if re.fullmatch(r'(\S\s)+\S*', stripped) and len(stripped) < 40:
        return stripped.replace(" ", "")
    return stripped

async def fetch_supremevalues(item_name: str) -> dict | None:
    """supremevalues.com'dan eşya değerini çeker. {name, value, source} döner veya None."""
    try:
        url = f"https://www.supremevalues.com/items/{urllib.parse.quote(item_name.replace(' ', '-').lower())}"
        headers = {"User-Agent": "Mozilla/5.0 (compatible; MM2Bot/1.0)"}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    # API endpoint dene
                    api_url = "https://www.supremevalues.com/api/items"
                    async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=10)) as r2:
                        if r2.status != 200:
                            return None
                        data = await r2.json()
                    items = data if isinstance(data, list) else data.get("items", [])
                    q_l = item_name.lower()
                    for it in items:
                        n = (it.get("name") or it.get("item") or "").lower()
                        if n == q_l:
                            val = it.get("value") or it.get("val")
                            if val is not None:
                                return {"name": it.get("name", item_name), "value": str(val), "source": "supremevalues.com"}
                    return None
                html = await resp.text()
        soup = BeautifulSoup(html, "html.parser")
        # Değer bilgisini bul
        for tag in soup.find_all(["span", "div", "p", "h3", "strong"]):
            txt = tag.get_text(strip=True)
            m = re.search(r"value[:\s]*([0-9,]+(?:\.[0-9]+)?)", txt, re.I)
            if m:
                return {"name": item_name, "value": m.group(1), "source": "supremevalues.com"}
        return None
    except Exception as ex:
        logger.error(f"supremevalues error ({item_name}): {ex}")
        return None

async def search_supremevalues_all(term: str) -> list:
    """supremevalues.com arama API'sine term gönderir."""
    try:
        url = f"https://www.supremevalues.com/api/search?q={urllib.parse.quote(term)}"
        headers = {"User-Agent": "Mozilla/5.0 (compatible; MM2Bot/1.0)"}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
        items = data if isinstance(data, list) else data.get("items", data.get("results", []))
        results = []
        for it in items:
            name = (it.get("name") or it.get("item") or "").strip()
            val  = it.get("value") or it.get("val")
            if name and val is not None:
                results.append({"name": name, "value": str(val), "source": "supremevalues.com"})
        return results
    except Exception:
        return []

async def search_mm2values(term: str) -> list:
    url = f"https://mm2values.com/search2.php?term={urllib.parse.quote(term)}"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; MM2Bot/1.0)"}
    results = []
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()
        soup = BeautifulSoup(html, "html.parser")
        for p in soup.find_all("p"):
            raw = p.get_text(separator=" ", strip=True)
            if not raw or "Value:" not in raw:
                continue
            # Her satırı ayrı item olarak parse et (birden fazla item aynı p içindeyse)
            # "ItemName - Value: X Origin: Y" formatındaki her bloğu ayır
            segments = re.split(r'(?=\S.*?-\s*Value:)', raw)
            for seg in segments:
                seg = seg.strip()
                if not seg or "Value:" not in seg:
                    continue
                val_match = re.search(r"Value:\s*([\d,.]+(?:\s*-\s*[\d,.]+)?)", seg)
                if not val_match:
                    continue
                name_raw  = seg.split(" - Value:")[0].strip() if " - Value:" in seg \
                            else seg.split("Value:")[0].strip(" -")
                name_clean = _clean_name(re.sub(r"\s+", " ", name_raw))
                if name_clean:
                    results.append({
                        "name":   name_clean,
                        "value":  val_match.group(1).strip(),
                        "source": "mm2values.com",
                    })
    except Exception as ex:
        logger.error(f"mm2values error ({term}): {ex}")
    return results

def fuzzy_find(query: str, results: list, threshold: int = 55) -> dict | None:
    if not results:
        return None
    query_l = query.lower()
    best, best_score = None, 0
    for item in results:
        score = max(
            fuzz.token_sort_ratio(query_l, item["name"].lower()),
            fuzz.partial_ratio(query_l, item["name"].lower())
        )
        if score > best_score:
            best_score, best = score, item
    return best if best_score >= threshold else None

# ─── MM2CHECKER SCRAPER ───────────────────────────────────────────────────────
MM2CHECKER_PAGES = [
    ("godlies",     "https://mm2checker.com/godlies.html"),
    ("ancients",    "https://mm2checker.com/ancients.html"),
    ("vintages",    "https://mm2checker.com/vintages.html"),
    ("legendaries", "https://mm2checker.com/legendaries.html"),
    ("rares",       "https://mm2checker.com/rares.html"),
    ("uncommons",   "https://mm2checker.com/uncommons.html"),
    ("commons",     "https://mm2checker.com/commons.html"),
    ("pets",        "https://mm2checker.com/pets.html"),
]
_MM2CHECKER_CACHE: dict = {}
_CHECKER_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

async def _scrape_checker_page(session: aiohttp.ClientSession, category: str, url: str) -> list:
    items = []
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return items
            html = await resp.text()
        soup = BeautifulSoup(html, "html.parser")
        for box in soup.select(".box[id]"):
            name = _clean_name(box.get("id", "").strip())
            if not name:
                continue
            img_tag = box.select_one("img[alt]")
            img_src = img_tag["src"] if img_tag else None
            img_url = f"https://mm2checker.com/{img_src.lstrip('/')}" if img_src else None
            val_span = box.select_one(".itemvalue")
            value    = val_span.get_text(strip=True).replace(",", "") if val_span else None
            body     = box.select_one(".itembody")
            body_text = body.get_text(separator="\n", strip=True) if body else ""
            demand = rarity = origin = obtained = None
            for line in body_text.splitlines():
                line = line.strip()
                if line.startswith("Demand"):
                    demand  = line.split("-", 1)[-1].strip() if "-" in line else None
                elif line.startswith("Rarity"):
                    rarity  = line.split("-", 1)[-1].strip() if "-" in line else None
                elif line.startswith("Origin"):
                    origin  = line.split("-", 1)[-1].strip() if "-" in line else None
                elif line.startswith("Obtained"):
                    obtained = line.split("-", 1)[-1].strip() if "-" in line else None
            items.append({
                "name": name, "value": value, "image": img_url,
                "category": category, "demand": demand,
                "rarity": rarity, "origin": origin, "obtained": obtained,
                "source": "mm2checker.com",
            })
    except Exception as ex:
        logger.error(f"mm2checker scrape error ({url}): {ex}")
    return items

async def fetch_mm2checker() -> dict:
    global _MM2CHECKER_CACHE
    result = {}
    async with aiohttp.ClientSession(headers=_CHECKER_HEADERS) as session:
        pages = await asyncio.gather(
            *[_scrape_checker_page(session, cat, url) for cat, url in MM2CHECKER_PAGES]
        )
    for page_items in pages:
        for item in page_items:
            result[item["name"].lower()] = item
    if result:
        _MM2CHECKER_CACHE = result
        logger.info(f"mm2checker cache: {len(result)} item")
    return result

def checker_find(query: str, chroma: bool = False) -> dict | None:
    if not _MM2CHECKER_CACHE:
        return None
    pool = {k: v for k, v in _MM2CHECKER_CACHE.items()
            if ("chroma" in k) == chroma or (chroma and "chroma" in k)}
    if not pool:
        pool = _MM2CHECKER_CACHE
    return fuzzy_find(query, list(pool.values()))

# ─── INTERACTION LOGGER ───────────────────────────────────────────────────────
def _format_options(data: dict) -> str:
    options = data.get("options", [])
    if not options:
        return ""
    parts = []
    for opt in options:
        if opt.get("type") in (1, 2) and "options" in opt:
            parts.append(f"{opt.get('name', '')} {_format_options(opt)}")
        else:
            parts.append(f"{opt.get('name', '')}:{opt.get('value', '')}")
    return " ".join(parts)

# ── Komut → okunabilir eylem açıklaması eşlemesi ─────────────────────────────
_KOMUT_ACIKLAMALARI: dict[str, str] = {
    "hesap-bağla":                  "Roblox hesabını Discord'a bağlamak için talep oluşturuldu",
    "hesap-görüntüle":              "Bağlı Roblox profili görüntülendi",
    "hesap-sil":                    "Roblox hesap bağlantısı silindi",
    "hesap-bilgi":                  "Sunucudaki bağlı / bağlı olmayan üyeler listelendi",
    "roblox-arat":                  "Roblox kullanıcı araması yapıldı",
    "eşya-ekle":                    "Envantere yeni eşya ekleme talebi oluşturuldu",
    "envanter-görüntüle":           "MM2 envanteri görüntülendi",
    "envanter-sil":                 "Envanterden eşya silme işlemi yapıldı",
    "değer":                        "MM2 eşya değeri sorgulandı",
    "yapay-zeka-kur":               "Yapay zeka sohbet kanalı kuruldu",
    "özel-mesaj":                   "Üyelere özel mesaj (DM) gönderildi",
    "yardım":                       "Yardım menüsü görüntülendi",
    "sunucular":                    "Botun bulunduğu sunucu listesi görüntülendi",
    "durum":                        "Botun durumu / aktivitesi güncellendi",
    "durum-döngü":                  "Dönen durum mesajları kuruldu / düzenlendi",
    "komut-kullanmayan-görüntüle":  "Komut kullanmayan üyeler listelendi",
    "komut-kullandırt":             "Pasif üyelere DM gönderildi",
    "yetkili-kanal":                "Yetkili log kanalı ayarlandı",
    "yetkili-rol":                  "Yetkili rolü ayarlandı",
}

# ─── BUTON AÇIKLAMALARI ────────────────────────────────────────────────────────
_BUTON_ACIKLAMALARI: dict[str, dict[str, str]] = {
    # OnayView — /hesap-bağla
    "hesap_onayla": {
        "komut": "/hesap-bağla",
        "etiket": "✅ Onayla",
        "islem": "Roblox hesabı onaylandı → veritabanına işlendi, kullanıcıya DM & nickname güncellendi",
    },
    "hesap_reddet": {
        "komut": "/hesap-bağla",
        "etiket": "❌ Reddet",
        "islem": "Roblox hesap bağlama talebi reddedildi → kayıt silindi, kullanıcıya DM gönderildi",
    },
    # EsyaOnaylamaView — /eşya-ekle (kullanıcı tarafı onayı)
    "esya_gonder": {
        "komut": "/eşya-ekle",
        "etiket": "✅ Evet, Uyuyor — Gönder",
        "islem": "Kullanıcı fotoğrafın uyduğunu onayladı → talep yetkililere iletildi",
    },
    "esya_degistir": {
        "komut": "/eşya-ekle",
        "etiket": "✏️ Uymuyor — Değiştir",
        "islem": "Kullanıcı fotoğrafın uymadığını belirtti → işlem iptal edildi, yeniden deneyecek",
    },
    # EsyaOnayView — /eşya-ekle (yetkili onayı)
    "esya_onayla": {
        "komut": "/eşya-ekle (yetkili)",
        "etiket": "✅ Onayla",
        "islem": "Yetkili eşya talebini onayladı → envantere eklendi, kullanıcıya DM gönderildi",
    },
    "esya_reddet": {
        "komut": "/eşya-ekle (yetkili)",
        "etiket": "❌ Reddet",
        "islem": "Yetkili eşya talebini reddetti → sebep modalı açıldı, kullanıcıya DM gönderilecek",
    },
    # EnvanterPaginatorView — /envanter-görüntüle
    "envanter_geri": {
        "komut": "/envanter-görüntüle",
        "etiket": "⬅️ Önceki Sayfa",
        "islem": "Envanter listesinde bir önceki sayfaya geçildi",
    },
    "envanter_sayfa": {
        "komut": "/envanter-görüntüle",
        "etiket": "Sayfa Göstergesi",
        "islem": "Sayfa numarası gösterge butonu (işlem yok)",
    },
    "envanter_ileri": {
        "komut": "/envanter-görüntüle",
        "etiket": "➡️ Sonraki Sayfa",
        "islem": "Envanter listesinde bir sonraki sayfaya geçildi",
    },
    # EnYakinView — /değer
    "en_yakin": {
        "komut": "/değer",
        "etiket": "🔍 En yakın eşyayı göster",
        "islem": "Eşya bulunamadı → benzer/yakın eşyanın değeri sorgulandı ve gösterildi",
    },
    # TercihlerView — /tercihler
    "pref_ozel_dm": {
        "komut": "/tercihler",
        "etiket": "📨 Özel Mesaj",
        "islem": "Özel mesaj (DM) alma tercihi açıldı veya kapatıldı",
    },
    "pref_envanter": {
        "komut": "/tercihler",
        "etiket": "📦 Envanter Bildirimi",
        "islem": "Envanter bildirimi tercihi açıldı veya kapatıldı",
    },
}

async def send_interaction_log(interaction: discord.Interaction, tip: str, channel_id: int):
    try:
        channel = bot.get_channel(channel_id)
        if not channel:
            return
        guild = interaction.guild
        icon_url = guild.icon.url if guild and guild.icon else None
        data = interaction.data or {}
        cmd_name = data.get("name", "")
        full_cmd = f"/{cmd_name} {_format_options(data)}".strip() if cmd_name else "?"

        title_map = {"slash": "🔧 Slash Komut", "modal": "📋 Modal", "button": "🔘 Buton"}
        aciklama = _KOMUT_ACIKLAMALARI.get(cmd_name, "")

        embed = discord.Embed(
            title=title_map.get(tip, tip),
            description=(
                f"**Kullanıcı:** {interaction.user.mention} (`{interaction.user.id}`)\n"
                f"**Sunucu:** {guild.name if guild else 'DM'}\n"
                f"**Kanal:** {interaction.channel.mention if interaction.channel else 'Bilinmiyor'}"
            ),
            color=discord.Color.blurple(),
            timestamp=datetime.datetime.utcnow()
        )
        if icon_url:
            embed.set_thumbnail(url=icon_url)
        if cmd_name:
            embed.add_field(name="Komut", value=f"`{full_cmd}`", inline=False)
        if aciklama:
            embed.add_field(name="📌 Yapılan İşlem", value=aciklama, inline=False)
        # Modal için custom_id'den bağlam çıkar
        if tip == "modal":
            modal_id = data.get("custom_id", "")
            if modal_id:
                embed.add_field(name="Modal ID", value=f"`{modal_id}`", inline=True)
        # Buton için custom_id'den bağlam çıkar
        if tip == "button":
            btn_id = data.get("custom_id", "")
            btn_bilgi = _BUTON_ACIKLAMALARI.get(btn_id)
            if btn_bilgi:
                embed.add_field(
                    name="🖱️ Basılan Buton",
                    value=f"`{btn_bilgi['etiket']}`",
                    inline=True,
                )
                embed.add_field(
                    name="📂 Ait Olduğu Komut",
                    value=f"`{btn_bilgi['komut']}`",
                    inline=True,
                )
                embed.add_field(
                    name="📋 Yapılan İşlem",
                    value=btn_bilgi["islem"],
                    inline=False,
                )
            elif btn_id:
                embed.add_field(name="🖱️ Buton ID", value=f"`{btn_id}`", inline=True)
        await channel.send(embed=embed)
    except Exception as ex:
        logger.error(f"Log gönderilemedi: {ex}")

# ─── DAILY UPDATE TASK ────────────────────────────────────────────────────────
@tasks.loop(time=datetime.time(hour=1, minute=0))
async def gunluk_guncelleme():
    logger.info("Günlük değer güncellemesi başladı...")
    owner = await bot.fetch_user(OWNER_ID)

    all_items: dict = {}
    for ch in "abcdefghijklmnopqrstuvwxyz":
        for item in await search_mm2values(ch):
            key = item["name"].lower()
            if key not in all_items:
                all_items[key] = item
        await asyncio.sleep(0.3)

    checker_yeni = await fetch_mm2checker()

    eklenenler:  list[str] = []
    degisimler:  list[str] = []

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT esya_adi, deger_values, kaynak FROM degerler_cache") as cur:
            eski = {row[0].lower(): {"deger": row[1], "kaynak": row[2]} async for row in cur}

        for key, item in all_items.items():
            # Tek/çift harfli item isimleri karışıklık yaratır — raporda gösterme
            if len(item["name"].strip()) < 3:
                continue
            new_val = item["value"]
            src     = item.get("source", "mm2values.com")
            checker = checker_yeni.get(key, {})
            img     = checker.get("image")
            if key not in eski:
                eklenenler.append(f"➕ **{item['name']}** — Değer: `{new_val}` ({src})")
            else:
                old_v = eski[key]["deger"]
                if str(old_v) != str(new_val):
                    arrow = "📈" if (
                        float(str(new_val).split("-")[0].replace(",","").strip() or 0) >
                        float(str(old_v).split("-")[0].replace(",","").strip() or 0)
                    ) else "📉"
                    degisimler.append(
                        f"{arrow} **{item['name']}**: `{old_v}` → `{new_val}` ({src})"
                    )
                    # Envanterde bu eşyaya sahip kullanıcılara DM
                    async with db.execute(
                        "SELECT DISTINCT discord_id FROM envanter WHERE LOWER(esya_adi) = ?",
                        (key,)
                    ) as c2:
                        sahipler = [r[0] async for r in c2]
                    for uid in sahipler:
                        try:
                            # Kullanıcı tercihini kontrol et
                            if not await _tercih_al(uid, "envanter_bildirimi", 1):
                                continue
                            u = await bot.fetch_user(uid)
                            dm_em = discord.Embed(
                                title="Eşya Değeri Değişti",
                                color=discord.Color.gold()
                            )
                            dm_em.add_field(name="Eşya",     value=item["name"], inline=False)
                            dm_em.add_field(name="Eski Değer", value=str(old_v),  inline=True)
                            dm_em.add_field(name="Yeni Değer", value=str(new_val), inline=True)
                            dm_em.add_field(name="Kaynak",     value=src,          inline=True)
                            if img:
                                dm_em.set_thumbnail(url=img)
                            await u.send(embed=dm_em)
                        except Exception:
                            pass

            await db.execute(
                "INSERT OR REPLACE INTO degerler_cache "
                "(esya_adi, deger_values, deger_supremes, gorsel_url, kaynak, guncelleme_tarihi) "
                "VALUES (?, ?, NULL, ?, ?, ?)",
                (key, new_val, checker.get("image"), src,
                 datetime.datetime.utcnow().isoformat())
            )
        await db.commit()

    top_server = max(stats["servers"], key=stats["servers"].get) if stats["servers"] else "Yok"
    embed = discord.Embed(
        title=f"{e('istatistik')} Günlük Bot Raporu",
        description=f"**Tarih:** {datetime.date.today().strftime('%d/%m/%Y')}",
        color=discord.Color.gold(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.add_field(
        name=f"{e('liste')} Komut İstatistikleri",
        value=(f"Toplam: `{stats['commands']}`\n{e('onay')} Başarılı: `{stats['success']}`\n"
               f"{e('hata')} Hata: `{stats['errors']}`\n{e('kalkan')} Yetkisiz: `{stats['unauthorized']}`"),
        inline=False
    )
    embed.add_field(name=f"{e('yildiz')} En Aktif Sunucu", value=f"`{top_server}`", inline=False)

    if eklenenler:
        embed.add_field(
            name=f"{e('ekle')} Yeni Eşyalar ({len(eklenenler)})",
            value="\n".join(eklenenler[:10]) + (f"\n... ve {len(eklenenler)-10} tane daha" if len(eklenenler) > 10 else ""),
            inline=False
        )
    if degisimler:
        embed.add_field(
            name=f"🔄 Değer Değişimleri ({len(degisimler)})",
            value="\n".join(degisimler[:15]) + (f"\n... ve {len(degisimler)-15} tane daha" if len(degisimler) > 15 else ""),
            inline=False
        )

    try:
        await owner.send(embed=embed)
    except discord.HTTPException as ex:
        logger.error(f"DM gönderilemedi: {ex}")

    for k in list(stats.keys()):
        stats[k] = {} if k == "servers" else 0

# ─── BOT AYARLARI DB ──────────────────────────────────────────────────────────
async def _bot_ayar_al(anahtar: str) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT deger FROM bot_ayarlari WHERE anahtar = ?", (anahtar,)
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else None

async def _bot_ayar_kaydet(anahtar: str, deger: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO bot_ayarlari (anahtar, deger) VALUES (?, ?)",
            (anahtar, deger)
        )
        await db.commit()

async def _bot_ayar_sil(anahtar: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM bot_ayarlari WHERE anahtar = ?", (anahtar,))
        await db.commit()

# ─── KULLANICI TERCİHLERİ ─────────────────────────────────────────────────────
async def _tercih_al(user_id: int, anahtar: str, varsayilan: int = 1) -> int:
    """Kullanıcı tercihini döndürür. Kayıt yoksa varsayılan değer (1=açık) döner."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT deger FROM kullanici_tercihler WHERE discord_id = ? AND anahtar = ?",
            (user_id, anahtar)
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else varsayilan

async def _tercih_kaydet(user_id: int, anahtar: str, deger: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO kullanici_tercihler (discord_id, anahtar, deger) VALUES (?, ?, ?)",
            (user_id, anahtar, deger)
        )
        await db.commit()

# ─── EVENTS ───────────────────────────────────────────────────────────────────
async def set_default_status():
    tip   = await _bot_ayar_al("durum_tip")
    metin = await _bot_ayar_al("durum_metin")
    renk  = await _bot_ayar_al("durum_renk")

    status_map = {
        "idle": discord.Status.idle,
        "dnd":  discord.Status.dnd,
        "invisible": discord.Status.invisible,
    }
    status = status_map.get(renk or "", discord.Status.online)

    if tip and metin:
        await bot.change_presence(activity=_make_activity(tip, metin), status=status)
    else:
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(bot.guilds)} sunucu | /yardım"
            ),
            status=status
        )

def _make_activity(tip: str, metin: str) -> discord.BaseActivity:
    tip = tip.lower()
    if tip == "playing":
        return discord.Game(name=metin)
    elif tip == "listening":
        return discord.Activity(type=discord.ActivityType.listening, name=metin)
    elif tip == "competing":
        return discord.Activity(type=discord.ActivityType.competing, name=metin)
    else:
        return discord.Activity(type=discord.ActivityType.watching, name=metin)

async def _durum_dongu_loop(interval_sn: int):
    global _dongu_index
    while True:
        if not _dongu_mesajlar:
            break
        item = _dongu_mesajlar[_dongu_index % len(_dongu_mesajlar)]
        try:
            await bot.change_presence(activity=_make_activity(item["tip"], item["metin"]))
        except Exception:
            pass
        _dongu_index = (_dongu_index + 1) % len(_dongu_mesajlar)
        await asyncio.sleep(interval_sn)

def _durum_dongu_durdur():
    global _dongu_task
    if _dongu_task and not _dongu_task.done():
        _dongu_task.cancel()
    _dongu_task = None

@bot.event
async def on_ready():
    await init_db()
    await tree.sync()
    gunluk_guncelleme.start()
    asyncio.create_task(fetch_mm2checker())
    await set_default_status()
    logger.info(f"Bot hazır: {bot.user} | {len(bot.guilds)} sunucu")

@bot.event
async def on_guild_join(guild: discord.Guild):
    await set_default_status()
    try:
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
        logger.info(f"Komutlar senkronize edildi: {guild.name}")
    except Exception as ex:
        logger.warning(f"Guild sync hatası ({guild.name}): {ex}")

@bot.event
async def on_guild_remove(guild: discord.Guild):
    await set_default_status()

@bot.event
async def on_interaction(interaction: discord.Interaction):
    t = interaction.type
    if t == discord.InteractionType.application_command:
        asyncio.create_task(send_interaction_log(interaction, "slash", LOG_SLASH_CHANNEL))
    elif t == discord.InteractionType.modal_submit:
        asyncio.create_task(send_interaction_log(interaction, "modal", LOG_MODAL_CHANNEL))
    elif t == discord.InteractionType.component:
        asyncio.create_task(send_interaction_log(interaction, "button", LOG_BUTTON_CHANNEL))

# ─── SAHİP PREFIX KOMUTLARI (her kanaldan çalışır) ───────────────────────────
@bot.command(name="durum")
async def sahip_durum(ctx, tip: str = "", *, metin: str = ""):
    if ctx.author.id != OWNER_ID:
        return
    tip = tip.lower()
    if tip in ("temizle", "sıfırla", "reset", "kaldır"):
        await _bot_ayar_sil("durum_tip")
        await _bot_ayar_sil("durum_metin")
        await set_default_status()
        await ctx.message.add_reaction("✅")
        return
    tip_map = {
        "oyun": "playing", "playing": "playing",
        "izliyor": "watching", "watching": "watching",
        "dinliyor": "listening", "listening": "listening",
        "yarışıyor": "competing", "competing": "competing",
    }
    tip_en = tip_map.get(tip, "")
    if not tip_en or not metin:
        await ctx.reply(
            "**Kullanım:**\n"
            "`!durum oyun <metin>` — Oynuyor: metin\n"
            "`!durum izliyor <metin>` — İzliyor: metin\n"
            "`!durum dinliyor <metin>` — Dinliyor: metin\n"
            "`!durum yarışıyor <metin>` — Yarışıyor: metin\n"
            "`!durum temizle` — Varsayılana döner"
        )
        return
    await _bot_ayar_kaydet("durum_tip", tip_en)
    await _bot_ayar_kaydet("durum_metin", metin)
    await set_default_status()
    await ctx.message.add_reaction("✅")

@bot.command(name="renk")
async def sahip_renk(ctx, renk: str = ""):
    if ctx.author.id != OWNER_ID:
        return
    renk_map = {
        "online": "online", "çevrimiçi": "online", "yeşil": "online",
        "idle": "idle", "boşta": "idle", "sarı": "idle",
        "dnd": "dnd", "rahatsız": "dnd", "kırmızı": "dnd",
        "gizli": "invisible", "invisible": "invisible",
    }
    renk_en = renk_map.get(renk.lower(), "")
    if not renk_en:
        await ctx.reply(
            "**Kullanım:** `!renk <online|idle|dnd|gizli>`\n"
            "• `online` / `yeşil` — Çevrimiçi\n"
            "• `idle` / `sarı` — Boşta\n"
            "• `dnd` / `kırmızı` — Rahatsız etme\n"
            "• `gizli` — Çevrimdışı görün"
        )
        return
    if renk_en == "online":
        await _bot_ayar_sil("durum_renk")
    else:
        await _bot_ayar_kaydet("durum_renk", renk_en)
    await set_default_status()
    await ctx.message.add_reaction("✅")

@bot.command(name="sahip-yardım", aliases=["syardım", "s-yardım"])
async def sahip_yardim(ctx):
    if ctx.author.id != OWNER_ID:
        return
    await ctx.reply(
        "**🔧 Sahip Komutları** (her kanaldan çalışır)\n\n"
        "`!durum oyun <metin>` — Bot oynuyor aktivitesi\n"
        "`!durum izliyor <metin>` — Bot izliyor aktivitesi\n"
        "`!durum dinliyor <metin>` — Bot dinliyor aktivitesi\n"
        "`!durum yarışıyor <metin>` — Bot yarışıyor aktivitesi\n"
        "`!durum temizle` — Aktiviteyi varsayılana döndür\n\n"
        "`!renk online` — Yeşil (çevrimiçi)\n"
        "`!renk idle` — Sarı (boşta)\n"
        "`!renk dnd` — Kırmızı (rahatsız etme)\n"
        "`!renk gizli` — Çevrimdışı görün"
    )

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # ── DM'de gelen mesajlar → doğrudan AI sohbet ─────────────────────────
    if not message.guild:
        if message.content.strip():
            await handle_ai_message(message)
        return

    # Sahip prefix komutları (!, her kanaldan) — AI kanalından önce kontrol et
    if message.author.id == OWNER_ID and message.content.startswith("!"):
        await bot.process_commands(message)
        return
    ai_ch_id = await get_ai_kanal(message.guild.id)
    if ai_ch_id and message.channel.id == ai_ch_id:
        await handle_ai_message(message)
        return
    await bot.process_commands(message)

# ─── AI YARDIMCI FONKSİYONLARI ───────────────────────────────────────────────

# Botun gerçek slash komut listesi — komut sorusunda AI'ya enjekte edilir
_BOT_KOMUT_LISTESI = """
Mm2 Bot'un tüm slash (/) komutları:

📋 AYARLAR (yetkili gerekli)
  /yetkili-kanal — Botun log mesajlarını göndereceği kanalı ayarlar
  /yetkili-rol   — Yetkili rolünü ayarlar

👤 ROBLOX HESAP
  /hesap-bağla       — Roblox hesabını Discord'a bağlamak için form açar (onay bekler)
  /hesap-görüntüle   — Bağlı Roblox profilini görüntüler
  /hesap-sil         — Hesap bağlantısını siler (yetkili)
  /hesap-bilgi       — Sunucudaki bağlı/bağlı olmayan üyeleri listeler (yetkili)
  /roblox-arat       — Roblox kullanıcısını arar ve sistem kaydını kontrol eder (yetkili)

🎒 ENVANTER
  /eşya-ekle          — Envantere eşya ekleme talebi oluşturur (onay gerekli)
  /envanter-görüntüle — MM2 envanterini görüntüler
  /envanter-sil       — Envanterden eşya siler (yetkili)

💎 MM2 DEĞER
  /değer — MM2 eşyasının güncel değerini sorgular; eşya bulunamazsa benzerlerini önerir

🤖 YAPAY ZEKA
  /yapay-zeka-kur — Seçilen kanala yapay zeka chat kurar (yetkili)

📢 DİĞER
  /özel-mesaj                   — Bir üyeye DM gönderir (yetkili)
  /yardım                       — Tüm komutları listeler
  /sunucular                    — Botun bulunduğu sunucuları listeler (sahip)
  /durum                        — Botun durumunu manuel günceller (sahip)
  /durum-döngü                  — Dönen durum mesajları kurar (sahip)
  /komut-kullanmayan-görüntüle  — Hiç komut kullanmayan üyeleri listeler (sahip)
  /komut-kullandırt             — Pasif üyelere otomatik DM atar (sahip)
""".strip()

_KOMUT_SORU_KELIMELERI = [
    "komut", "ne yapabilirsin", "ne yaparsın", "neler yaparsın",
    "özellikler", "yetenekler", "fonksiyon", "slash", "nasıl kullanılır",
    "ne işe yarar", "menü", "liste", "yardım", "help",
]

_IZLENIM_KELIMELERI = [
    "izlenim", "ön izlenim", "ne düşünürsün", "anlat", "kim bu",
    "hakkında", "tanı", "değerlendir", "ne dersin", "nasıl biri", "bu kişi",
]
_GORSEL_KELIMELERI = [
    "göster", "görsel", "resim", "fotoğraf", "logo", "amblem",
    "tablo", "grafik", "harita", "kadro", "forma", "görüntü",
]

_GORSEL_URET_KELIMELERI = [
    # Türkçe kök + ekli formlar
    "resim yap", "resim çiz", "resim oluştur", "resim üret",
    "resmi yap", "resmi çiz", "resmi oluştur", "resmi üret",
    "resmini yap", "resmini çiz",
    "görsel yap", "görsel çiz", "görsel oluştur", "görsel üret",
    "görseli yap", "görseli çiz", "görseli oluştur",
    "fotoğraf oluştur", "fotoğraf çek", "fotoğraf yap",
    "fotoğrafını çek", "fotoğrafını yap",
    "çiz bana", "bana çiz", "bana resim", "bana görsel",
    "çizim yap", "illüstrasyon", "illüstrasyon yap",
    "ai resim", "yapay zeka resim", "yapay zeka ile çiz",
    "image generate", "generate image", "draw me", "imagine",
]

_DOVIZ_KELIMELERI = [
    "dolar", "euro", "sterlin", "frank", "döviz", "kur", "kaç tl",
    "kaç para", "altın", "gram altın", "çeyrek altın", "yarım altın", "ons",
]

async def _doviz_cek() -> str | None:
    """exchangerate-api.com ücretsiz API'sinden anlık USD/EUR/GBP → TRY kurlarını çeker."""
    try:
        url = "https://open.exchangerate-api.com/v6/latest/USD"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status != 200:
                    return None
                data = await r.json()
        rates    = data.get("rates", {})
        try_rate = rates.get("TRY", 0)
        eur_usd  = rates.get("EUR", 0)
        gbp_usd  = rates.get("GBP", 0)
        chf_usd  = rates.get("CHF", 0)
        if not try_rate:
            return None
        eur_try = try_rate / eur_usd if eur_usd else 0
        gbp_try = try_rate / gbp_usd if gbp_usd else 0
        chf_try = try_rate / chf_usd if chf_usd else 0
        _, _, tarih_tr, saat_str = _simdi_bilgisi()
        return (
            f"CANLI DÖVİZ KURLARI ({tarih_tr} {saat_str} Türkiye saati):\n"
            f"• 1 USD (Dolar)   = {try_rate:.4f} TL\n"
            f"• 1 EUR (Euro)    = {eur_try:.4f} TL\n"
            f"• 1 GBP (Sterlin) = {gbp_try:.4f} TL\n"
            f"• 1 CHF (Frank)   = {chf_try:.4f} TL\n"
            f"Kaynak: open.exchangerate-api.com (anlık)"
        )
    except Exception:
        return None

# ── Akıllı web arama filtresi ────────────────────────────────────────────────
def _akilli_filtrele(sonuclar: list[dict], bugun_tr: str, sorgu: str = "") -> str:
    """Sonuçları puanlar; spor sorgusunda siyasi/ekonomi içerik cezalandırılır."""
    SAYI_RE   = re.compile(r'\d[\d.,]+')
    SPOR_RE   = re.compile(r'(skor|gol|maç|kazandı|yendi|berabere|puan|goller|final|lig|şampiyon|futbol|basket|tenis)', re.I)
    PARA_RE   = re.compile(r'(tl|₺|\$|dolar|euro|€|kur|fiyat|başlangıç)', re.I)
    GUNCEL_RE = re.compile(r'(2025|2026|bugün|today|son dakika|güncel|canlı|anlık|şu an|dün)', re.I)
    SIYASI_RE = re.compile(r'(seçim|hükümet|meclis|iktidar|muhalefet|cumhurbaşkanı|siyasi parti|ekonomi politika|bütçe|enflasyon)', re.I)

    sorgu_l  = sorgu.lower()
    spor_sorgu = any(w in sorgu_l for w in (
        "maç", "skor", "gol", "futbol", "takım", "lig", "şampiyon", "basket", "tenis",
        "match", "score", "goal", "champion", "league"
    ))

    puanli = []
    for s in sonuclar:
        baslik = s.get("title", "")
        govde  = s.get("body", "")
        metin  = f"{baslik}: {govde}"
        puan   = 0
        if bugun_tr in metin:          puan += 8
        if GUNCEL_RE.search(metin):    puan += 4
        if SPOR_RE.search(metin):      puan += 3
        if SAYI_RE.search(metin):      puan += 2
        if PARA_RE.search(metin):      puan += 2
        # Spor sorgusu ama içerik tamamen siyasi/ekonomi → ceza
        if spor_sorgu and SIYASI_RE.search(metin) and not SPOR_RE.search(metin):
            puan -= 5
        puanli.append((puan, metin))

    puanli.sort(key=lambda x: x[0], reverse=True)
    # Puan -5'ten düşük olanları (tamamen alakasız) çıkar
    puanli = [(p, m) for p, m in puanli if p > -3]
    return "\n".join(f"• {m}" for _, m in puanli)

# ── Web araması (duckduckgo_search, thread pool) ────────────────────────────
async def _web_ara(sorgu: str, max_sonuc: int = 15, bugun_tr: str = "") -> str:
    def _sync():
        try:
            from ddgs import DDGS
            # İlk arama: Türkçe
            with DDGS() as d:
                sonuclar = list(d.text(sorgu, max_results=max_sonuc, region="tr-tr"))
            # Sonuç azsa İngilizce de dene
            if len(sonuclar) < 5:
                with DDGS() as d:
                    sonuclar += list(d.text(sorgu, max_results=max_sonuc, region="wt-wt"))
            if not sonuclar:
                return "Arama sonucu bulunamadı."
            return _akilli_filtrele(sonuclar, bugun_tr, sorgu)
        except Exception as ex:
            return f"Arama başarısız: {ex}"
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_thread_pool, _sync)

# ── İsim temizleyici — AI yanıtı başından kullanıcı adını siler ──────────────
def _temizle_isim_prefix(yanit: str, kullanici_adi: str, display_adi: str) -> str:
    """AI cevabı kullanıcı adıyla başlıyorsa o kısmı siler."""
    if not yanit:
        return yanit
    for ad in [kullanici_adi, display_adi]:
        if not ad:
            continue
        # "Vespera, ..." / "Vespera! ..." / "Merhaba Vespera, ..." / "_Vespera, ..."
        patterns = [
            rf"^_?{re.escape(ad)}[,!?.:\s]+",        # başta doğrudan isim
            rf"^[^\w]*{re.escape(ad)}[,!?.:\s]+",    # özel karakter + isim
            rf"^(merhaba|hey|selam|evet|tamam)[,!]?\s+_?{re.escape(ad)}[,!?.:\s]+",  # hitap + isim
        ]
        for pat in patterns:
            yanit = re.sub(pat, "", yanit, flags=re.IGNORECASE).lstrip()
    return yanit

# ── Görsel URL arama (duckduckgo_search) ────────────────────────────────────
_GUVENLI_GORSEL_UZANTI = (".jpg", ".jpeg", ".png", ".gif", ".webp")
_ENGELLENECEK_GORSEL_DOMAIN = ("pinterest.", "adult", "xxx", "nsfw", "18+")

async def _gorsel_url_bul(sorgu: str) -> str | None:
    def _sync():
        try:
            from ddgs import DDGS
            with DDGS() as d:
                sonuclar = list(d.images(
                    sorgu, max_results=15,
                    safesearch="moderate",
                    region="tr-tr"
                ))
            for s in sonuclar:
                url   = s.get("image", "")
                title = (s.get("title") or "").lower()
                src   = (s.get("source") or s.get("url") or "").lower()
                if not url.startswith("http"):
                    continue
                # Kötü domain/içerik filtresi
                if any(b in src or b in url.lower() for b in _ENGELLENECEK_GORSEL_DOMAIN):
                    continue
                # Uygun uzantı veya herhangi bir görsel URL
                url_lower = url.lower().split("?")[0]
                if any(url_lower.endswith(ext) for ext in _GUVENLI_GORSEL_UZANTI):
                    return url
            # Uzantı kontrolü olmadan ilk geçerliyi döndür
            for s in sonuclar:
                url = s.get("image", "")
                if url.startswith("http"):
                    return url
        except Exception:
            pass
        return None
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_thread_pool, _sync)


# ── Üye profil özeti (izlenim analizi için) ──────────────────────────────────
def _uye_profil_ozeti(uye: discord.Member) -> str:
    now = discord.utils.utcnow()
    yas     = (now - uye.created_at).days if uye.created_at else 0
    sunucu  = (now - uye.joined_at).days  if uye.joined_at  else 0
    roller  = [r.name for r in uye.roles  if r.name != "@everyone"]
    is_adm  = uye.guild_permissions.administrator or uye.guild_permissions.manage_guild
    is_bst  = bool(getattr(uye, "premium_since", None))
    satirlar = [
        f"Kullanıcı adı: {uye.name}",
        f"Görünen ad: {uye.display_name}",
        f"Hesap yaşı: {yas} gün  ({yas//365} yıl {(yas%365)//30} ay)",
        f"Sunucuya katılalı: {sunucu} gün",
        f"Rolleri: {', '.join(roller) if roller else 'Yok'}",
        f"Yetkili: {'Evet' if is_adm else 'Hayır'}",
        f"Nitro Booster: {'Evet' if is_bst else 'Hayır'}",
        f"Bot: {'Evet' if uye.bot else 'Hayır'}",
    ]
    if uye.id == OWNER_ID:
        satirlar.append("★ Bu kişi bot sahibi.")
    return "\n".join(satirlar)

def _uye_bul(message: discord.Message) -> discord.Member | None:
    for u in message.mentions:
        if u.bot:
            continue
        if isinstance(u, discord.Member):
            return u
        if message.guild:
            m = message.guild.get_member(u.id)
            if m:
                return m
    return None

def _ai_kullanici_profili(message: discord.Message) -> str:
    m = message.author
    satirlar = [
        f"Kullanıcı: {m.name} ({m.display_name})",
    ]
    if m.created_at:
        yas = (discord.utils.utcnow() - m.created_at).days
        satirlar.append(f"Hesap yaşı: {yas} gün")
    if isinstance(m, discord.Member) and m.joined_at:
        sg = (discord.utils.utcnow() - m.joined_at).days
        satirlar.append(f"Sunucuya katılalı: {sg} gün")
    if isinstance(m, discord.Member) and m.roles:
        roller = [r.name for r in m.roles if r.name != "@everyone"]
        if roller:
            satirlar.append(f"Rolleri: {', '.join(roller)}")
        is_adm = m.guild_permissions.administrator or m.guild_permissions.manage_guild
        satirlar.append(f"Yetkili: {'Evet' if is_adm else 'Hayır'}")
    if m.id == OWNER_ID:
        satirlar.append("★ Bu kişi bot sahibi.")
    return "\n".join(satirlar)

# ── AI stil DB işlemleri ─────────────────────────────────────────────────────
async def _get_ai_stil(guild_id: int, user_id: int) -> tuple[str | None, bool]:
    """(stil, bekliyor) döndürür."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT stil, bekliyor FROM ai_kullanici_stil WHERE guild_id=? AND user_id=?",
            (guild_id, user_id)
        ) as cur:
            row = await cur.fetchone()
    if row is None:
        return None, False
    return row[0], bool(row[1])

async def _set_ai_stil(guild_id: int, user_id: int, stil: str | None, bekliyor: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO ai_kullanici_stil (guild_id, user_id, stil, bekliyor)
               VALUES (?,?,?,?)
               ON CONFLICT(guild_id, user_id)
               DO UPDATE SET stil=excluded.stil, bekliyor=excluded.bekliyor""",
            (guild_id, user_id, stil, int(bekliyor))
        )
        await db.commit()

# ── AI hafıza DB işlemleri ───────────────────────────────────────────────────
import json as _json

async def _get_hafiza_db(guild_id: int, user_id: int) -> list[dict]:
    """Kullanıcının konuşma geçmişini DB'den döndürür."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT mesajlar FROM ai_hafiza WHERE guild_id=? AND user_id=?",
            (guild_id, user_id)
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return []
    try:
        return _json.loads(row[0])
    except Exception:
        return []

async def _set_hafiza_db(guild_id: int, user_id: int, mesajlar: list[dict]):
    """Konuşma geçmişini DB'ye kaydeder (son MAX_AI_HAFIZA mesaj)."""
    veri = _json.dumps(mesajlar[-MAX_AI_HAFIZA:], ensure_ascii=False)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO ai_hafiza (guild_id, user_id, mesajlar, guncellendi)
               VALUES (?,?,?, datetime('now'))
               ON CONFLICT(guild_id, user_id)
               DO UPDATE SET mesajlar=excluded.mesajlar, guncellendi=excluded.guncellendi""",
            (guild_id, user_id, veri)
        )
        await db.commit()

async def _sil_hafiza_db(guild_id: int, user_id: int | None = None):
    """Belirli kullanıcının (ya da tüm sunucunun) hafızasını siler."""
    async with aiosqlite.connect(DB_PATH) as db:
        if user_id:
            await db.execute(
                "DELETE FROM ai_hafiza WHERE guild_id=? AND user_id=?",
                (guild_id, user_id)
            )
        else:
            await db.execute(
                "DELETE FROM ai_hafiza WHERE guild_id=?", (guild_id,)
            )
        await db.commit()

# ── Ana AI mesaj işleyici ────────────────────────────────────────────────────
async def handle_ai_message(message: discord.Message):
    # Aynı mesaj zaten işleniyorsa ikinci çağrıyı reddet
    if message.id in _ai_isleniyor:
        return
    _ai_isleniyor.add(message.id)
    try:
        await _handle_ai_message_inner(message)
    finally:
        _ai_isleniyor.discard(message.id)

async def _handle_ai_message_inner(message: discord.Message):
    # Provider listesini al
    providers = _ai_providers()
    if not providers:
        logger.warning("AI: Hiçbir API anahtarı yok.")
        return

    # DM'de guild_id = 0 olarak kullan
    guild_id = message.guild.id if message.guild else 0
    user_id  = message.author.id
    metin_lower = message.content.lower()

    # ── Cooldown kontrolü ──────────────────────────────────────────────────
    import time as _time
    simdi_ts = _time.monotonic()
    son_ts = _ai_son_istek.get((guild_id, user_id), 0)
    kalan = AI_COOLDOWN_SN - (simdi_ts - son_ts)
    if kalan > 0:
        # Cooldown aktif — kullanıcıya bildir ve mesajı işleme
        await message.reply(
            f"{e('bekle')} **{round(kalan)} saniye** bekle, sonra tekrar yaz.",
            delete_after=kalan,
        )
        return
    _ai_son_istek[(guild_id, user_id)] = simdi_ts

    # ── Görsel eki var mı? ─────────────────────────────────────────────────
    gorsel_eki_url: str | None = None
    for att in message.attachments:
        ct = att.content_type or ""
        if ct.startswith("image/") or att.filename.lower().endswith(
                (".png", ".jpg", ".jpeg", ".gif", ".webp")):
            gorsel_eki_url = att.url
            break

    # ── Orta konuşma stil değiştirme isteği ───────────────────────────────
    _STIL_DEGISTIR_RE = re.compile(
        r'\b(benimle\s+|artık\s+|bundan\s+sonra\s+)([\w\s]+?)\s+(şekilde\s+konuş|ol\b|konuş\b)',
        re.I | re.UNICODE
    )
    m_stil = _STIL_DEGISTIR_RE.search(message.content)
    if m_stil and len(message.content) < 250:
        yeni_stil = message.content.strip()[:200]
        await _set_ai_stil(guild_id, user_id, yeni_stil, bekliyor=False)
        await message.reply(
            f"✅ Anlaşıldı, konuşma stilimi güncelledim: **{yeni_stil}**"
        )
        return

    # ── Kullanıcı kuralı ("bana X yapma/yap") ─────────────────────────────
    _KURAL_RE = re.compile(
        r'\b(bana\s+.{2,60}(yapma|yap|söyleme|söyle|kullanma|kullan|deme|de)\b'
        r'|beni\s+.{2,60}(olarak\s+)?say\b'
        r'|asla\s+.{2,60}(yapma|söyleme|deme)\b)',
        re.I | re.UNICODE
    )
    if _KURAL_RE.search(message.content) and len(message.content) < 200:
        stil_mevcut, bk = await _get_ai_stil(guild_id, user_id)
        kural_notu = f"[Kullanıcı kuralı: {message.content.strip()[:150]}]"
        yeni_stil = (stil_mevcut or "") + " | " + kural_notu
        await _set_ai_stil(guild_id, user_id, yeni_stil[:400], bekliyor=bool(bk))
        await message.reply("✅ Kaydettim, bunu dikkate alacağım.")
        return

    # ── Stil tercihi akışı ─────────────────────────────────────────────────
    stil, bekliyor = await _get_ai_stil(guild_id, user_id)

    if bekliyor:
        # Kullanıcının cevabı stil tercihi olarak kaydet
        stil = message.content.strip()[:200]
        await _set_ai_stil(guild_id, user_id, stil, bekliyor=False)
        await message.reply(
            f"Anlaşıldı! Bundan sonra seninle **{stil}** şeklinde konuşacağım. "
            "Sorunla devam edebilirsin."
        )
        return

    if stil is None:
        # İlk kez yazan kullanıcı — stil sor
        await _set_ai_stil(guild_id, user_id, stil=None, bekliyor=True)
        await message.reply(
            "Merhaba! Benimle nasıl konuşmamı istersin?\n"
            "Örnek: `resmi ve ciddi` / `samimi ve arkadaşça` / `kısa ve öz` / "
            "`bol detaylı` gibi bir şey yazabilirsin."
        )
        return

    # ── Etiketlenen üye var mı? ────────────────────────────────────────────
    bahsedilen  = _uye_bul(message)
    izlenim_modu = bahsedilen is not None and any(k in metin_lower for k in _IZLENIM_KELIMELERI)
    takılma_modu = bahsedilen is not None and not izlenim_modu   # komik yorum modu

    # ── Komut sorusu mu? ───────────────────────────────────────────────────
    komut_sorusu = any(k in metin_lower for k in _KOMUT_SORU_KELIMELERI)

    # ── Görsel arama gerekiyor mu? ─────────────────────────────────────────
    gorsel_gerekli = any(k in metin_lower for k in _GORSEL_KELIMELERI)

    # ── Görsel ÜRETME gerekiyor mu? ────────────────────────────────────────
    gorsel_uretme_gerekli = any(k in metin_lower for k in _GORSEL_URET_KELIMELERI)

    # ── Döviz sorgusu mu? ──────────────────────────────────────────────────
    doviz_gerekli = any(k in metin_lower for k in _DOVIZ_KELIMELERI)

    from openai import AsyncOpenAI

    # Görsel üretme isteği — desteklenmiyor, bilgi ver
    if gorsel_uretme_gerekli:
        await message.reply(
            "🤖 Resim oluşturma özelliğim şu an aktif değil. "
            "Ama seninle sohbet edebilirim — soru sor, bilgi al, eğlen! 😊"
        )
        return

    # Web & görsel & döviz aramayı paralel yap
    async with message.channel.typing():
        temiz_sorgu  = re.sub(r"<@!?\d+>", "", message.content).strip()
        _s, _gad, _tarih_tr, _saat = _simdi_bilgisi()
        tarihli_sorgu = f"{temiz_sorgu} {_tarih_tr}"

        web_gorev    = _web_ara(tarihli_sorgu, bugun_tr=_tarih_tr)
        gorsel_gorev = _gorsel_url_bul(temiz_sorgu) if gorsel_gerekli else asyncio.sleep(0)
        doviz_gorev  = _doviz_cek()               if doviz_gerekli  else asyncio.sleep(0)
        web_sonucu_raw, gorsel_url_raw, doviz_raw = await asyncio.gather(
            web_gorev, gorsel_gorev, doviz_gorev, return_exceptions=True
        )
        web_sonucu = web_sonucu_raw if isinstance(web_sonucu_raw, str) else None
        gorsel_url  = gorsel_url_raw  if isinstance(gorsel_url_raw,  str) else None
        doviz_veri  = doviz_raw       if isinstance(doviz_raw,       str) else None

        # Mesaj listesini hazırla
        profil_bilgisi = _ai_kullanici_profili(message)
        sistem = _ai_sistem_prompt_olustur(profil_bilgisi, stil=stil)
        if doviz_veri:
            sistem += f"\n=== CANLI DÖVİZ ({_tarih_tr}) ===\n{doviz_veri}\n"
        if web_sonucu:
            sistem += f"\n=== WEB ARAMA ({_tarih_tr}) ===\n{web_sonucu[:3000]}\n"
        if not web_sonucu or "bulunamadı" in (web_sonucu or ""):
            sistem += (
                "\n[NOT: Web araması sonuç vermedi. Anlık veri gereken konularda "
                "bilgi verme, 'şu an ulaşamadım' de.]\n"
            )
        if komut_sorusu:
            sistem += f"\n=== BOT KOMUTLARI ===\n{_BOT_KOMUT_LISTESI}\n"
        if gorsel_eki_url:
            sistem += (
                f"\n=== KULLANICI GÖRSELİ ===\n"
                f"Kullanıcı bir görsel paylaştı: {gorsel_eki_url}\n"
                f"Görseli analiz et, içeriği hakkında Türkçe bilgi ver.\n"
            )

        kullanici_mesaj = message.content or ("(görsel paylaştı)" if gorsel_eki_url else "")
        if izlenim_modu and bahsedilen:
            profil = _uye_profil_ozeti(bahsedilen)
            kullanici_mesaj += f"\n\n[Profil:]\n{profil}\nBu kişi hakkında samimi değerlendirme yap."
        elif takılma_modu and bahsedilen:
            profil = _uye_profil_ozeti(bahsedilen)
            kullanici_mesaj += f"\n\n[Profil:]\n{profil}\nEsprili ve yaratıcı ol, kaba olma."

        gecmis  = await _get_hafiza_db(guild_id, user_id)

        # ── Konu değişikliği algılama — geçmişi sınırla ──────────────────
        def _konu_degisti(yeni: str, gecmis_: list) -> bool:
            if len(gecmis_) < 4:
                return False
            son_icerik = " ".join(
                m["content"] if isinstance(m.get("content"), str) else ""
                for m in gecmis_[-4:] if m.get("role") == "user"
            )
            yeni_k = set(re.findall(r'\b\w{4,}\b', yeni.lower()))
            son_k  = set(re.findall(r'\b\w{4,}\b', son_icerik.lower()))
            if not yeni_k or not son_k:
                return False
            overlap = len(yeni_k & son_k) / max(len(yeni_k), 1)
            return overlap < 0.08  # %8'den az örtüşme = farklı konu

        if _konu_degisti(kullanici_mesaj, gecmis):
            gecmis = gecmis[-2:]  # sadece son 2 mesajı tut

        # Görsel eki içeren user mesajı — Gemini için multimodal format
        if gorsel_eki_url:
            kullanici_mesaj_icerik: object = [
                {"type": "text",      "text": kullanici_mesaj[:2000]},
                {"type": "image_url", "image_url": {"url": gorsel_eki_url}},
            ]
        else:
            kullanici_mesaj_icerik = kullanici_mesaj[:3000]

        mesajlar_temel = [{"role": "system", "content": sistem}]
        mesajlar_temel.extend(gecmis)

        # Provider fallback — Groq → Gemini → OpenRouter
        answer = None
        son_hata = None
        for api_key, base_url, model in providers:
            try:
                # Vision (multimodal) yalnızca Gemini destekler
                is_gemini = "generativelanguage" in base_url
                if gorsel_eki_url and not is_gemini:
                    # Groq/OpenRouter: text-only, görsel URL'yi text'te belirt
                    son_mesaj = {"role": "user",
                                 "content": f"{kullanici_mesaj[:2000]}\n(Görsel: {gorsel_eki_url})"}
                else:
                    son_mesaj = {"role": "user", "content": kullanici_mesaj_icerik}
                mesajlar = mesajlar_temel + [son_mesaj]

                client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=30.0, max_retries=0)
                resp   = await client.chat.completions.create(
                    model=model, messages=mesajlar, max_tokens=800, temperature=0.75,
                )
                answer = (resp.choices[0].message.content or "").strip()
                logger.info(f"AI yanıt: {model}")
                break  # başarılı, döngüden çık
            except Exception as ex:
                hata_str = str(ex).lower()
                logger.warning(f"AI provider {model} başarısız: {ex}")
                # kota/rate limit/model bulunamadı → sonraki modeli dene
                if any(x in hata_str for x in ("429", "404", "quota", "rate_limit",
                                                "resource_exhausted", "not found",
                                                "no endpoints", "unavailable",
                                                "insufficient", "out of funds", "402")):
                    son_hata = ex
                    continue
                # başka hata → direkt bildir
                son_hata = ex
                break

    if answer:
        # İsim temizleme — AI yanıtı yanlışlıkla kullanıcı adıyla başlıyorsa sil
        author = message.author
        kullanici_adi  = getattr(author, "name", "") or ""
        display_adi    = getattr(author, "display_name", "") or ""
        answer = _temizle_isim_prefix(answer, kullanici_adi, display_adi)

        # Hafızaya kaydet
        gecmis.append({"role": "user",      "content": kullanici_mesaj[:500]})
        gecmis.append({"role": "assistant",  "content": answer[:500]})
        await _set_hafiza_db(guild_id, user_id, gecmis)
        # Görsel URL varsa cevabın sonuna ekle (ayrı mesaj göndermek yerine)
        if gorsel_url:
            answer = answer.rstrip() + f"\n{gorsel_url}"
        # Cevabı gönder (uzunsa böl)
        for i in range(0, len(answer), 1990):
            await message.reply(answer[i:i + 1990])
            if i == 0 and len(answer) > 1990:
                await asyncio.sleep(0.5)
    elif son_hata:
        logger.error(f"AI tüm provider'lar başarısız: {son_hata}")
        hata_str = str(son_hata).lower()
        if any(x in hata_str for x in ("429", "quota", "rate_limit", "resource_exhausted")):
            mesaj = "Şu an tüm AI servisleri meşgul, birkaç dakika sonra tekrar dene. 🕐"
        elif "invalid" in hata_str and "key" in hata_str:
            mesaj = "API anahtarı geçersiz. Replit Secrets kısmını kontrol et."
        elif "context_length" in hata_str or "token" in hata_str:
            mesaj = "Mesaj çok uzun, daha kısa yaz."
        else:
            mesaj = f"Bir sorun oluştu: `{type(son_hata).__name__}`"
        try:
            await message.reply(mesaj)
        except Exception:
            pass
        # AI hata kanalına bildirim
        try:
            hata_ch = bot.get_channel(LOG_MODAL_CHANNEL)
            if hata_ch:
                hata_em = discord.Embed(
                    title="⚠️ AI Hatası — Tüm Sağlayıcılar Başarısız",
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.utcnow()
                )
                hata_em.add_field(name="Hata", value=f"`{type(son_hata).__name__}: {str(son_hata)[:300]}`", inline=False)
                hata_em.add_field(name="Sunucu", value=message.guild.name if message.guild else "DM", inline=True)
                hata_em.add_field(name="Kullanıcı", value=f"{message.author.mention}", inline=True)
                hata_em.add_field(name="Zaman", value=f"<t:{int(__import__('time').time())}:R>", inline=True)
                await hata_ch.send(embed=hata_em)
        except Exception:
            pass

# ─── VIEWS ────────────────────────────────────────────────────────────────────
class OnayView(discord.ui.View):
    def __init__(self, target_user_id: int):
        super().__init__(timeout=None)
        self.target_user_id = target_user_id

    @discord.ui.button(label="✅ Onayla", style=discord.ButtonStyle.success, custom_id="hesap_onayla")
    async def onayla(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await is_yetkili(interaction):
            return await interaction.response.send_message("❌ Yetkiniz yok.", ephemeral=True)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE roblox_bagla SET onaylandi = 1 WHERE discord_id = ?",
                (self.target_user_id,))
            await db.commit()
            async with db.execute(
                "SELECT roblox_username FROM roblox_bagla WHERE discord_id = ?",
                (self.target_user_id,)
            ) as cur:
                row = await cur.fetchone()
        roblox_name = row[0] if row else None
        await interaction.response.send_message(
            f"{e('onay')} Hesap onaylandı! Roblox: `{roblox_name}`", ephemeral=True)
        member = interaction.guild.get_member(self.target_user_id) if interaction.guild else None
        user   = member or bot.get_user(self.target_user_id)
        if user:
            try:
                await user.send(embed=discord.Embed(
                    title=f"{e('onay')} Hesap Bağlama Onaylandı!",
                    description=f"Roblox hesabın (`{roblox_name}`) Discord'una bağlandı.",
                    color=discord.Color.green()
                ))
            except discord.HTTPException:
                pass
        if member and roblox_name:
            try:
                await member.edit(nick=roblox_name, reason="Roblox hesap bağlama onaylandı")
            except discord.HTTPException:
                pass
        for item in self.children:
            item.disabled = True
        try:
            await interaction.message.edit(view=self)
        except discord.HTTPException:
            pass

    @discord.ui.button(label="❌ Reddet", style=discord.ButtonStyle.danger, custom_id="hesap_reddet")
    async def reddet(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await is_yetkili(interaction):
            return await interaction.response.send_message("❌ Yetkiniz yok.", ephemeral=True)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM roblox_bagla WHERE discord_id = ?", (self.target_user_id,))
            await db.commit()
        user = bot.get_user(self.target_user_id)
        if user:
            try:
                await user.send(embed=discord.Embed(
                    title=f"{e('hata')} Hesap Bağlama Reddedildi",
                    description="Talebiniz reddedildi. Doğru kullanıcı adıyla tekrar deneyin.",
                    color=discord.Color.red()
                ))
            except discord.HTTPException:
                pass
        await interaction.response.send_message(f"{e('hata')} Talep reddedildi.", ephemeral=True)
        for item in self.children:
            item.disabled = True
        try:
            await interaction.message.edit(view=self)
        except discord.HTTPException:
            pass


class ReddetModal(discord.ui.Modal, title="Reddetme Sebebi"):
    sebep = discord.ui.TextInput(
        label="Sebep",
        placeholder="Neden reddedildi? (kullanıcıya DM olarak gönderilecek)",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True,
    )

    def __init__(self, target_user_id: int, esya_adi: str,
                 sistem_gorsel: str | None, kullanici_gorsel: str | None,
                 parent_view: "EsyaOnayView", original_message: discord.Message):
        super().__init__()
        self.target_user_id   = target_user_id
        self.esya_adi         = esya_adi
        self.sistem_gorsel    = sistem_gorsel
        self.kullanici_gorsel = kullanici_gorsel
        self.parent_view      = parent_view
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"{e('hata')} `{self.esya_adi}` talebi reddedildi.", ephemeral=True)
        user = bot.get_user(self.target_user_id)
        if user:
            try:
                em = discord.Embed(
                    title=f"{e('hata')} Eşya Talebi Reddedildi",
                    description=f"**{self.esya_adi}** ekleme talebiniz reddedildi.",
                    color=discord.Color.red()
                )
                em.add_field(name="📝 Sebep", value=self.sebep.value, inline=False)
                if self.sistem_gorsel:
                    em.set_thumbnail(url=self.sistem_gorsel)
                await user.send(embed=em)
            except discord.HTTPException:
                pass
        for item in self.parent_view.children:
            item.disabled = True
        try:
            await self.original_message.edit(view=self.parent_view)
        except discord.HTTPException:
            pass


class EsyaOnaylamaView(discord.ui.View):
    """Kullanıcıya özel (ephemeral) onay — sistem fotoğrafı vs kullanıcı fotoğrafını karşılaştırır."""
    def __init__(self, user_id: int, esya_adi: str,
                 sistem_gorsel: str | None, kullanici_gorsel: str, log_ch_id: int):
        super().__init__(timeout=180)
        self.user_id          = user_id
        self.esya_adi         = esya_adi
        self.sistem_gorsel    = sistem_gorsel
        self.kullanici_gorsel = kullanici_gorsel
        self.log_ch_id        = log_ch_id

    @discord.ui.button(label="✅ Evet, Uyuyor — Gönder", style=discord.ButtonStyle.success, custom_id="esya_gonder")
    async def onayla(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Log kanalına her iki fotoğrafı gönder
        embed = discord.Embed(
            title=f"{e('envanter')} Yeni Eşya Talebi",
            description=(
                "**Yetkililer:** Aşağıdaki kullanıcı fotoğrafı (büyük) ile "
                "sistemdeki eşya fotoğrafı (küçük/sağ) karşılaştırın."
            ),
            color=discord.Color.gold(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name=f"{e('kullanici')} Kullanıcı",
                        value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=False)
        embed.add_field(name=f"{e('elmas')} Eşya Adı", value=f"`{self.esya_adi}`", inline=True)
        embed.set_image(url=self.kullanici_gorsel)          # kullanıcı fotoğrafı (büyük)
        if self.sistem_gorsel:
            embed.set_thumbnail(url=self.sistem_gorsel)    # sistem fotoğrafı (küçük, sağda)
        embed.set_footer(text="Büyük = kullanıcının fotoğrafı  •  Küçük = sistemdeki eşya")
        ch = bot.get_channel(self.log_ch_id)
        if ch:
            view = EsyaOnayView(self.user_id, self.esya_adi,
                                self.sistem_gorsel, self.kullanici_gorsel)
            await ch.send(embed=embed, view=view)
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"{e('bekle')} **{self.esya_adi}** talebin yetkililere iletildi. Onayladıklarında envanterine eklenecek.",
            embed=None, view=self
        )

    @discord.ui.button(label="✏️ Uymuyor — Değiştir", style=discord.ButtonStyle.danger, custom_id="esya_degistir")
    async def degistir(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content="✏️ Komutu tekrar kullanın ve doğru eşya adı ile fotoğrafı yükleyin.",
            embed=None, view=self
        )


class EsyaOnayView(discord.ui.View):
    def __init__(self, target_user_id: int, esya_adi: str,
                 sistem_gorsel: str | None, kullanici_gorsel: str | None):
        super().__init__(timeout=None)
        self.target_user_id   = target_user_id
        self.esya_adi         = esya_adi
        self.sistem_gorsel    = sistem_gorsel
        self.kullanici_gorsel = kullanici_gorsel

    @discord.ui.button(label="✅ Onayla", style=discord.ButtonStyle.success, custom_id="esya_onayla")
    async def onayla(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await is_yetkili(interaction):
            return await interaction.response.send_message("❌ Yetkiniz yok.", ephemeral=True)
        # Envantere sistem görselini kaydet (varsa), yoksa kullanıcınınkini
        kayit_gorsel = self.sistem_gorsel or self.kullanici_gorsel
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO envanter (discord_id, esya_adi, gorsel_url) VALUES (?, ?, ?)",
                (self.target_user_id, self.esya_adi, kayit_gorsel))
            await db.commit()
        await interaction.response.send_message(
            f"{e('onay')} `{self.esya_adi}` <@{self.target_user_id}> envanterine eklendi!", ephemeral=True)
        user = bot.get_user(self.target_user_id)
        if user:
            try:
                em = discord.Embed(
                    title=f"{e('envanter')} Eşya Talebiniz Onaylandı!",
                    description=f"**{self.esya_adi}** envanterinize eklendi.",
                    color=discord.Color.green()
                )
                if kayit_gorsel:
                    em.set_thumbnail(url=kayit_gorsel)
                await user.send(embed=em)
            except discord.HTTPException:
                pass
        for item in self.children:
            item.disabled = True
        try:
            await interaction.message.edit(view=self)
        except discord.HTTPException:
            pass

    @discord.ui.button(label="❌ Reddet", style=discord.ButtonStyle.danger, custom_id="esya_reddet")
    async def reddet(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await is_yetkili(interaction):
            return await interaction.response.send_message("❌ Yetkiniz yok.", ephemeral=True)
        modal = ReddetModal(
            target_user_id=self.target_user_id,
            esya_adi=self.esya_adi,
            sistem_gorsel=self.sistem_gorsel,
            kullanici_gorsel=self.kullanici_gorsel,
            parent_view=self,
            original_message=interaction.message,
        )
        await interaction.response.send_modal(modal)


class EnvanterPaginatorView(discord.ui.View):
    """Envanter için sayfalı görünüm — sayfa başına 5 eşya."""
    SAYFA_BOYUTU = 5

    def __init__(self, hedef: discord.Member, satirlar: list[tuple]):
        super().__init__(timeout=120)
        self.hedef   = hedef
        self.satirlar = satirlar   # (esya_adi, deger_str, gorsel_url | None)
        self.sayfa   = 0
        self.toplam_sayfa = max(1, (len(satirlar) + self.SAYFA_BOYUTU - 1) // self.SAYFA_BOYUTU)
        self._butonlari_guncelle()

    def _butonlari_guncelle(self):
        self.onceki_btn.disabled = self.sayfa == 0
        self.sonraki_btn.disabled = self.sayfa >= self.toplam_sayfa - 1
        self.sayfa_btn.label = f"{self.sayfa + 1} / {self.toplam_sayfa}"

    def _embed_olustur(self) -> discord.Embed:
        bas = self.sayfa * self.SAYFA_BOYUTU
        bit = bas + self.SAYFA_BOYUTU
        dilim = self.satirlar[bas:bit]

        toplam_deger = sum(s[1] for s in self.satirlar if isinstance(s[1], (int, float)))
        embed = discord.Embed(
            title=f"🎒 {self.hedef.display_name} Envanteri",
            color=discord.Color.green(),
            timestamp=datetime.datetime.utcnow()
        )
        satirlar_str = []
        gorsel = None
        for esya, deger, img in dilim:
            deger_str = f"`{deger:.1f}`" if isinstance(deger, float) else f"`{deger}`"
            img_ikon = " 🖼️" if img else ""
            satirlar_str.append(f"💎 `{esya}` — {deger_str}{img_ikon}")
            if img and not gorsel:
                gorsel = img
        embed.description = "\n".join(satirlar_str)
        embed.add_field(
            name="📊 Toplam Tahmini Değer",
            value=f"`{toplam_deger:.1f}`  •  **{len(self.satirlar)} eşya**",
            inline=False
        )
        if gorsel:
            embed.set_image(url=gorsel)
        embed.set_footer(text=f"Sayfa {self.sayfa + 1}/{self.toplam_sayfa}")
        return embed

    @discord.ui.button(emoji="⬅️", style=discord.ButtonStyle.secondary, custom_id="envanter_geri")
    async def onceki_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.sayfa -= 1
        self._butonlari_guncelle()
        await interaction.response.edit_message(embed=self._embed_olustur(), view=self)

    @discord.ui.button(label="1 / 1", style=discord.ButtonStyle.primary, disabled=True, custom_id="envanter_sayfa")
    async def sayfa_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass  # sadece sayfa numarası gösterir

    @discord.ui.button(emoji="➡️", style=discord.ButtonStyle.secondary, custom_id="envanter_ileri")
    async def sonraki_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.sayfa += 1
        self._butonlari_guncelle()
        await interaction.response.edit_message(embed=self._embed_olustur(), view=self)


class EnYakinView(discord.ui.View):
    """Değer sorgulamada eşya bulunamazsa benzer eşyayı gösteren buton."""
    def __init__(self, suggestion_name: str):
        super().__init__(timeout=120)
        self.suggestion_name = suggestion_name

    @discord.ui.button(label="En yakın eşyayı göster", style=discord.ButtonStyle.primary, emoji="🔍", custom_id="en_yakin")
    async def goster(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        results = await search_mm2values(self.suggestion_name)
        checker = checker_find(self.suggestion_name)
        best    = fuzzy_find(self.suggestion_name, results) or (results[0] if results else None)
        if not best and not checker:
            return await interaction.followup.send("Eşya bulunamadı.", ephemeral=True)
        em = _build_deger_embed(self.suggestion_name, best, checker)
        await interaction.followup.send(embed=em, ephemeral=True)
        self.stop()


# ─── MODALS ───────────────────────────────────────────────────────────────────
class HesapBaglaModal(discord.ui.Modal, title="🔗 Roblox Hesap Bağlama"):
    roblox_kullanici = discord.ui.TextInput(
        label="Roblox Kullanıcı Adı",
        placeholder="Roblox kullanıcı adınızı girin",
        required=True, max_length=50
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await log_usage(interaction, "hesap-bağla")
        kullanici_adi = self.roblox_kullanici.value.strip()
        try:
            roblox_id, roblox_display = None, kullanici_adi
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://users.roblox.com/v1/usernames/users",
                    json={"usernames": [kullanici_adi], "excludeBannedUsers": False},
                    timeout=aiohttp.ClientTimeout(total=8)
                ) as r:
                    if r.status == 200:
                        d = await r.json()
                        users_data = d.get("data", [])
                        if users_data:
                            roblox_id      = users_data[0].get("id")
                            roblox_display = users_data[0].get("displayName", kullanici_adi)
                            kullanici_adi  = users_data[0].get("name", kullanici_adi)

            # Başka biri bu Roblox hesabına kayıtlı mı?
            if roblox_id:
                async with aiosqlite.connect(DB_PATH) as db:
                    async with db.execute(
                        "SELECT discord_id FROM roblox_bagla WHERE roblox_id = ?", (roblox_id,)
                    ) as cur:
                        existing = await cur.fetchone()
                if existing and existing[0] != interaction.user.id:
                    return await interaction.followup.send(
                        f"{e('hata')} Bu Roblox hesabı başka bir Discord kullanıcısına kayıtlı. "
                        "Farklı bir hesap deneyin.",
                        ephemeral=True
                    )

            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "INSERT OR REPLACE INTO roblox_bagla "
                    "(discord_id, roblox_username, roblox_display_name, roblox_id, guild_id, onaylandi) "
                    "VALUES (?, ?, ?, ?, ?, 0)",
                    (interaction.user.id, kullanici_adi, roblox_display,
                     roblox_id, interaction.guild_id))
                await db.commit()

            log_ch_id = await get_log_kanal(interaction.guild_id)
            if log_ch_id:
                profile_data, avatar_url = {}, None
                if roblox_id:
                    profile_data, avatar_url = await asyncio.gather(
                        roblox_fetch_profile(roblox_id),
                        roblox_fetch_avatar(roblox_id)
                    )
                bio = profile_data.get("description", "").strip()
                em  = discord.Embed(
                    title=f"{e('bagla')} Yeni Hesap Bağlama Talebi",
                    color=discord.Color.orange(),
                    timestamp=datetime.datetime.utcnow()
                )
                em.add_field(name=f"{e('kullanici')} Discord",
                             value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=False)
                em.add_field(name=f"{e('roblox')} Roblox", value=f"`{kullanici_adi}`", inline=True)
                if roblox_display != kullanici_adi:
                    em.add_field(name="Görünen Ad", value=f"`{roblox_display}`", inline=True)
                em.add_field(name="Roblox ID", value=f"`{roblox_id or 'Bulunamadı'}`", inline=True)
                if bio:
                    em.add_field(name="📝 Açıklama", value=bio[:300], inline=False)
                if roblox_id:
                    em.add_field(
                        name=f"{e('bilgi')} Profil",
                        value=f"[Roblox'ta görüntüle](https://www.roblox.com/users/{roblox_id}/profile)",
                        inline=False)
                if avatar_url:
                    em.set_image(url=avatar_url)
                ch = bot.get_channel(log_ch_id)
                if ch:
                    await ch.send(embed=em, view=OnayView(interaction.user.id))

            stats_add(interaction)
            await interaction.followup.send(
                f"{e('bekle')} Hesap bağlama talebin alındı! "
                "Yetkililer onayladıktan sonra hesabın aktif olacak. "
                "İsteğiniz beklemede.",
                ephemeral=True)
        except Exception as ex:
            await log_error(interaction, "hesap-bağla", str(ex))
            stats_add(interaction, success=False, error=True)
            await interaction.followup.send(f"{e('hata')} Hata: {ex}", ephemeral=True)

def _safe_field(value: str, limit: int = 1024) -> str:
    """Field değerini Discord limitine göre güvenli keser."""
    if len(value) <= limit:
        return value
    lines = value.splitlines()
    out = []
    for line in lines:
        if sum(len(l) + 1 for l in out) + len(line) + 1 > limit - 20:
            out.append("...")
            break
        out.append(line)
    return "\n".join(out)

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def _build_deger_embed(search_term: str, best_values: dict | None,
                        best_checker: dict | None,
                        sv_data: dict | None = None) -> discord.Embed:
    display_name = (best_checker or best_values or {}).get("name", search_term)
    embed = discord.Embed(
        title=f"{e('elmas')} {display_name}",
        color=discord.Color.purple(),
        timestamp=datetime.datetime.utcnow()
    )
    if best_values:
        val_str = str(best_values.get("value", "—"))[:200]
        embed.add_field(name=f"{e('istatistik')} Değer (MM2Values)",
                        value=f"`{val_str}`", inline=True)
    if best_checker:
        chk_val = str(best_checker.get("value") or "—")[:200]
        embed.add_field(name=f"{e('istatistik')} Değer (MM2Checker)",
                        value=f"`{chk_val}`", inline=True)
    if sv_data:
        sv_val = str(sv_data.get("value", "—"))[:200]
        embed.add_field(name=f"{e('istatistik')} Değer (SupremeValues)",
                        value=f"`{sv_val}`", inline=True)
    if best_checker:
        details = []
        for k, label in [("demand", "Talep"), ("rarity", "Nadir"), ("obtained", "Edinim")]:
            if best_checker.get(k):
                details.append(f"{label}: `{best_checker[k]}`")
        if details:
            embed.add_field(name=f"{e('liste')} Detaylar",
                            value=_safe_field("\n".join(details)), inline=False)
        if best_checker.get("image"):
            embed.set_thumbnail(url=best_checker["image"])
        if best_checker.get("category"):
            embed.add_field(name="🏷️ Kategori",
                            value=f"`{best_checker['category'].capitalize()}`", inline=True)
    sources = []
    if best_values:  sources.append("mm2values.com")
    if best_checker: sources.append("mm2checker.com")
    if sv_data:      sources.append("supremevalues.com")
    embed.set_footer(text=f"{'  |  '.join(sources) or '?'} — {search_term[:80]}")
    return embed

# ─── TERCİHLER VIEW ───────────────────────────────────────────────────────────
TERCIH_LISTESI = [
    ("ozel_mesaj_dm",      "📨 Özel Mesaj Bildirimleri",       "Bot üzerinden gönderilen toplu DM'leri al"),
    ("envanter_bildirimi", "📦 Envanter Değer Bildirimleri",   "Envanterindeki eşyanın değeri değişince DM al"),
]

class TercihlerView(discord.ui.View):
    def __init__(self, user_id: int, tercihler: dict):
        super().__init__(timeout=120)
        self.user_id   = user_id
        self.tercihler = tercihler

    def _embed(self) -> discord.Embed:
        em = discord.Embed(
            title="⚙️ Tercihlerim",
            description="Aşağıdaki butonlarla tercihlerini açıp kapatabilirsin.",
            color=discord.Color.blurple()
        )
        for anahtar, ad, aciklama in TERCIH_LISTESI:
            durum = "✅ Açık" if self.tercihler.get(anahtar, 1) else "❌ Kapalı"
            em.add_field(name=ad, value=f"{durum}\n*{aciklama}*", inline=False)
        em.set_footer(text="Değişiklikler anında kaydedilir.")
        return em

    @discord.ui.button(label="📨 Özel Mesaj", style=discord.ButtonStyle.secondary, custom_id="pref_ozel_dm")
    async def toggle_ozel_mesaj(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Sadece kendi tercihlerini değiştirebilirsin.", ephemeral=True)
        mevcut = self.tercihler.get("ozel_mesaj_dm", 1)
        yeni   = 0 if mevcut else 1
        self.tercihler["ozel_mesaj_dm"] = yeni
        await _tercih_kaydet(self.user_id, "ozel_mesaj_dm", yeni)
        button.style = discord.ButtonStyle.success if yeni else discord.ButtonStyle.secondary
        button.label = f"📨 Özel Mesaj — {'✅' if yeni else '❌'}"
        await interaction.response.edit_message(embed=self._embed(), view=self)

    @discord.ui.button(label="📦 Envanter Bildirimi", style=discord.ButtonStyle.secondary, custom_id="pref_envanter")
    async def toggle_envanter(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Sadece kendi tercihlerini değiştirebilirsin.", ephemeral=True)
        mevcut = self.tercihler.get("envanter_bildirimi", 1)
        yeni   = 0 if mevcut else 1
        self.tercihler["envanter_bildirimi"] = yeni
        await _tercih_kaydet(self.user_id, "envanter_bildirimi", yeni)
        button.style = discord.ButtonStyle.success if yeni else discord.ButtonStyle.secondary
        button.label = f"📦 Envanter Bildirimi — {'✅' if yeni else '❌'}"
        await interaction.response.edit_message(embed=self._embed(), view=self)

# ─── SLASH KOMUTLARI ──────────────────────────────────────────────────────────

# /yetkili-kanal
@tree.command(name="yetkili-kanal", description="Botun log mesajlarını göndereceği kanalı ayarlar.")
@app_commands.describe(kanal="Log kanalını seçin")
@app_commands.default_permissions(manage_guild=True)
async def yetkili_kanal(interaction: discord.Interaction, kanal: discord.TextChannel):
    if not await is_yetkili(interaction):
        stats_add(interaction, success=False, unauth=True)
        return await interaction.response.send_message("❌ Yetkiniz yok.", ephemeral=True)
    await log_usage(interaction, "yetkili-kanal")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings (guild_id, log_channel_id) VALUES (?, ?)",
            (interaction.guild_id, kanal.id))
        await db.commit()
    stats_add(interaction)
    await interaction.response.send_message(
        f"✅ Log kanalı {kanal.mention} olarak ayarlandı.", ephemeral=True)

# /yetkili-rol
@tree.command(name="yetkili-rol", description="Yetkili rolleri ayarlar (birden fazla ID boşlukla yazılabilir).")
@app_commands.describe(rol_idler="Rol ID'leri boşlukla girin")
@app_commands.default_permissions(manage_guild=True)
async def yetkili_rol(interaction: discord.Interaction, rol_idler: str):
    if not interaction.user.guild_permissions.administrator and interaction.user.id != OWNER_ID:
        stats_add(interaction, success=False, unauth=True)
        return await interaction.response.send_message("❌ Sadece yöneticiler kullanabilir.", ephemeral=True)
    await log_usage(interaction, "yetkili-rol")
    raw_ids = rol_idler.split()
    gecerli_roller, gecersiz = [], []
    for rid in raw_ids:
        rid = rid.strip("<@&>")
        if not rid.isdigit():
            gecersiz.append(rid)
            continue
        role_obj = interaction.guild.get_role(int(rid))
        if role_obj:
            gecerli_roller.append(role_obj)
        else:
            gecersiz.append(rid)
    if not gecerli_roller:
        return await interaction.response.send_message("❌ Geçerli rol bulunamadı.", ephemeral=True)
    kayit = ",".join(str(r.id) for r in gecerli_roller)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO settings (guild_id, yetkili_rol_id) VALUES (?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET yetkili_rol_id = ?",
            (interaction.guild_id, kayit, kayit))
        await db.commit()
    stats_add(interaction)
    msg = f"✅ Yetkili roller: {' '.join(r.mention for r in gecerli_roller)}"
    if gecersiz:
        msg += f"\n⚠️ Tanınmayanlar: {', '.join(gecersiz)}"
    await interaction.response.send_message(msg, ephemeral=True)

# /yardım
@tree.command(name="yardım", description="Botun tüm komutlarını listeler.")
async def yardim(interaction: discord.Interaction):
    await log_usage(interaction, "yardım")
    stats_add(interaction)
    embed = discord.Embed(title=f"{e('bilgi')} Komut Listesi",
                          color=discord.Color.blurple(), timestamp=datetime.datetime.utcnow())
    embed.add_field(name=f"{e('ayarlar')} Ayarlar *(yetkili)*", value=(
        "`/yetkili-kanal` — Log kanalını ayarlar\n"
        "`/yetkili-rol` — Yetkili rolünü ayarlar"
    ), inline=False)
    embed.add_field(name=f"{e('kullanici')} Hesap", value=(
        "`/hesap-bağla` — Roblox hesabını bağla (onay bekler)\n"
        "`/hesap-görüntüle` — Bağlı Roblox profilini göster\n"
        "`/hesap-sil` — Hesap bağlantısını sil *(yetkili)*\n"
        "`/hesap-bilgi` — Bağlı/bağlı olmayan listesi *(yetkili)*\n"
        "`/roblox-arat` — Roblox kullanıcısını ara + sistem kontrolü *(yetkili)*"
    ), inline=False)
    embed.add_field(name=f"{e('envanter')} Envanter", value=(
        "`/eşya-ekle` — Eşya ekleme talebi oluştur (onay gerekli)\n"
        "`/envanter-görüntüle` — Envanterini görüntüle\n"
        "`/envanter-sil` — Envanterden eşya sil *(yetkili)*"
    ), inline=False)
    embed.add_field(name=f"{e('elmas')} MM2 Değer", value=(
        "`/değer` — MM2 eşya değerini sorgula (eşya yoksa benzer önerir)"
    ), inline=False)
    embed.add_field(name=f"{e('robot')} Yapay Zeka", value=(
        "`/yapay-zeka-kur` — Kanala yapay zeka kur *(yetkili)*"
    ), inline=False)
    embed.add_field(name=f"{e('mesaj')} Diğer", value=(
        "`/özel-mesaj` — DM gönder *(yetkili)*\n"
        "`/sunucular` — Bot sunucuları *(sahip)*\n"
        "`/durum` — Bot durumu manuel güncelle *(sahip)*\n"
        "`/durum-döngü` — Dönen durum mesajları kur *(sahip)*\n"
        "`/komut-kullanmayan-görüntüle` — Pasif üyeler *(sahip)*\n"
        "`/komut-kullandırt` — Pasif üyelere DM *(sahip)*"
    ), inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# /değer
@tree.command(name="değer", description="MM2 eşyasının güncel değerini sorgular.")
@app_commands.describe(esya="Eşya adı", chroma="Chroma versiyonu mu?")
@app_commands.choices(chroma=[
    app_commands.Choice(name="Evet", value="evet"),
    app_commands.Choice(name="Hayır", value="hayır"),
])
async def deger(interaction: discord.Interaction, esya: str,
                chroma: app_commands.Choice[str] = None):
    await interaction.response.defer(ephemeral=False)
    await log_usage(interaction, "değer")
    is_chroma   = chroma and chroma.value == "evet"
    search_term = f"chroma {esya}" if is_chroma else esya
    try:
        results = await search_mm2values(search_term)
        if chroma and chroma.value == "hayır":
            results = [r for r in results if "chroma" not in r["name"].lower()]
        elif is_chroma:
            cr = [r for r in results if "chroma" in r["name"].lower()]
            if cr:
                results = cr

        best_values = fuzzy_find(search_term, results)
        if not best_values and results:
            best_values = results[0]
        if not best_values:
            fallback = await search_mm2values(esya.split()[0])
            if is_chroma:
                fallback = [r for r in fallback if "chroma" in r["name"].lower()] or fallback
            best_values = fuzzy_find(esya, fallback) or (fallback[0] if fallback else None)

        best_checker = checker_find(search_term, chroma=is_chroma)

        # supremevalues.com — 3. kaynak
        sv_data = await fetch_supremevalues(search_term)
        if not sv_data and esya != search_term:
            sv_data = await fetch_supremevalues(esya)

        if not best_values and not best_checker and not sv_data:
            # Fuzzy suggest from cache
            suggestion = None
            if _MM2CHECKER_CACHE:
                names = list(_MM2CHECKER_CACHE.keys())
                match = fuzz_process.extractOne(esya.lower(), names, score_cutoff=40)
                if match:
                    suggestion = _MM2CHECKER_CACHE[match[0]]["name"]
            if suggestion:
                view = EnYakinView(suggestion)
                stats_add(interaction, success=False, error=True)
                return await interaction.followup.send(
                    f"❌ **{esya}** bulunamadı.\nEn yakın eşya: **{suggestion}**",
                    view=view)
            stats_add(interaction, success=False, error=True)
            return await interaction.followup.send(f"❌ **{esya}** bulunamadı.")

        embed = _build_deger_embed(search_term, best_values, best_checker, sv_data=sv_data)
        stats_add(interaction)
        await interaction.followup.send(embed=embed)
    except Exception as ex:
        await log_error(interaction, "değer", str(ex))
        stats_add(interaction, success=False, error=True)
        await interaction.followup.send(f"{e('hata')} Hata: {ex}")

# /hesap-bağla
@tree.command(name="hesap-bağla", description="Roblox hesabınızı Discord'a bağlamak için form açar.")
async def hesap_bagla(interaction: discord.Interaction):
    # Zaten kayıtlı mı?
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT roblox_username, onaylandi FROM roblox_bagla WHERE discord_id = ?",
            (interaction.user.id,)
        ) as cur:
            mevcut = await cur.fetchone()
    if mevcut:
        durum = f"{e('onay')} Onaylı" if mevcut[1] else f"{e('bekle')} Onay Bekliyor"
        return await interaction.response.send_message(
            f"Zaten bir Roblox hesabın bağlı: `{mevcut[0]}` ({durum})\n"
            "Değiştirmek için `/hesap-sil` komutunu kullan.",
            ephemeral=True)
    log_ch_id = await get_log_kanal(interaction.guild_id)
    if not log_ch_id:
        return await interaction.response.send_message(
            f"{e('ayarlar')} Bu sunucuda log kanalı ayarlanmamış. "
            "Bir yönetici `/yetkili-kanal` ile ayarlamalıdır.",
            ephemeral=True)
    await interaction.response.send_modal(HesapBaglaModal())

# /hesap-görüntüle
@tree.command(name="hesap-görüntüle", description="Bağlı Roblox profilini görüntüler.")
@app_commands.describe(kullanici="Görüntülenecek kullanıcı (boş = kendin)")
async def hesap_goruntule(interaction: discord.Interaction,
                          kullanici: discord.Member = None):
    await interaction.response.defer(ephemeral=True)
    await log_usage(interaction, "hesap-görüntüle")
    target = kullanici or interaction.user
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT roblox_username, roblox_id, roblox_display_name, onaylandi "
            "FROM roblox_bagla WHERE discord_id = ?", (target.id,)
        ) as cur:
            row = await cur.fetchone()
    if not row:
        stats_add(interaction, success=False)
        return await interaction.followup.send(
            f"❌ {target.mention} henüz Roblox hesabı bağlamamış. `/hesap-bağla` kullan.",
            ephemeral=True)
    username, roblox_id, display_name, onaylandi = row

    avatar_url = None
    profile_data = {}
    if roblox_id:
        avatar_url, profile_data = await asyncio.gather(
            roblox_fetch_avatar(roblox_id),
            roblox_fetch_profile(roblox_id)
        )

    embed = discord.Embed(
        title=f"{e('kullanici')} {username} — Roblox Profili",
        url=f"https://www.roblox.com/users/{roblox_id}/profile" if roblox_id else None,
        color=discord.Color.green()
    )
    embed.add_field(name="Discord",         value=target.mention, inline=True)
    embed.add_field(name=f"{e('roblox')} Roblox", value=f"`{username}`", inline=True)
    if display_name and display_name != username:
        embed.add_field(name="Görünen Ad",  value=f"`{display_name}`", inline=True)
    embed.add_field(name="Roblox ID",       value=f"`{roblox_id or 'N/A'}`", inline=True)
    embed.add_field(
        name="Durum",
        value=f"{e('onay')} Onaylı" if onaylandi else f"{e('bekle')} Onay Bekliyor",
        inline=True)
    if profile_data.get("description"):
        embed.add_field(name="📝 Açıklama", value=profile_data["description"][:300], inline=False)
    if profile_data.get("created"):
        embed.add_field(name="Roblox Kayıt", value=profile_data["created"][:10], inline=True)
    if avatar_url:
        embed.set_image(url=avatar_url)
    stats_add(interaction)
    await interaction.followup.send(embed=embed, ephemeral=True)

# /hesap-sil
@tree.command(name="hesap-sil", description="Kullanıcının Roblox bağlantısını siler.")
@app_commands.describe(kullanici="Bağlantısı silinecek kullanıcı")
@app_commands.default_permissions(manage_guild=True)
async def hesap_sil(interaction: discord.Interaction, kullanici: discord.Member):
    await interaction.response.defer(ephemeral=True)
    await log_usage(interaction, "hesap-sil")
    if not await is_yetkili(interaction):
        stats_add(interaction, success=False, unauth=True)
        return await interaction.followup.send("❌ Yetkiniz yok.", ephemeral=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM roblox_bagla WHERE discord_id = ?", (kullanici.id,))
        await db.commit()
    stats_add(interaction)
    await interaction.followup.send(
        f"✅ {kullanici.mention} kullanıcısının Roblox bağlantısı silindi.", ephemeral=True)

# /hesap-bilgi
@tree.command(name="hesap-bilgi", description="Sunucudaki tüm bağlı/bağlı olmayan hesapları listeler.")
@app_commands.default_permissions(manage_guild=True)
async def hesap_bilgi(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await log_usage(interaction, "hesap-bilgi")
    if not await is_yetkili(interaction):
        stats_add(interaction, success=False, unauth=True)
        return await interaction.followup.send("❌ Yetkiniz yok.", ephemeral=True)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT discord_id, roblox_username, onaylandi FROM roblox_bagla WHERE guild_id = ?",
            (interaction.guild_id,)
        ) as cur:
            rows = await cur.fetchall()
    bagli_ids = {row[0] for row in rows}
    bagli_str = "\n".join(
        [f"<@{r[0]}> → `{r[1]}` {'✅' if r[2] else '⏳'}" for r in rows]
    ) or "Yok"
    members = interaction.guild.members
    bagli_olmayan = [m for m in members if not m.bot and m.id not in bagli_ids]
    bo_str = ", ".join([m.mention for m in bagli_olmayan[:20]]) or "Yok"
    if len(bagli_olmayan) > 20:
        bo_str += f" ... ve {len(bagli_olmayan)-20} kişi daha"
    embed = discord.Embed(title=f"{e('liste')} Hesap Bilgileri",
                          color=discord.Color.blue(), timestamp=datetime.datetime.utcnow())
    embed.add_field(name=f"{e('onay')} Bağlı ({len(rows)})",           value=bagli_str[:1024], inline=False)
    embed.add_field(name=f"{e('hata')} Bağlı Olmayan ({len(bagli_olmayan)})", value=bo_str[:1024], inline=False)
    stats_add(interaction)
    await interaction.followup.send(embed=embed, ephemeral=True)

async def _esya_gorsel_bul(esya_adi: str) -> str | None:
    """Eşyanın gerçek görselini DB cache'den veya MM2 Checker'dan arar."""
    # 1) Cache'e bak (fuzzy match)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT esya_adi, gorsel_url FROM degerler_cache WHERE gorsel_url IS NOT NULL"
        ) as cur:
            cache_rows = await cur.fetchall()
    if cache_rows:
        # Tam eşleşme önce
        lower = esya_adi.lower()
        for ad, url in cache_rows:
            if ad.lower() == lower:
                return url
        # Fuzzy eşleşme
        en_iyi = None
        en_skor = 0
        for ad, url in cache_rows:
            from thefuzz import fuzz
            skor = fuzz.ratio(lower, ad.lower())
            if skor > en_skor:
                en_skor = skor
                en_iyi = url
        if en_skor >= 60 and en_iyi:
            return en_iyi
    # 2) MM2 Checker cache'e bak (bellekte)
    checker = checker_find(esya_adi)
    if checker and checker.get("image"):
        return checker["image"]
    return None

# /eşya-ekle
@tree.command(name="eşya-ekle", description="Envantere eşya ekleme talebi oluşturur.")
@app_commands.describe(
    esya_adi="Eşyanın MM2'deki tam adı",
    gorsel="Envanterinizdeki eşyanın fotoğrafı (PNG/JPG/GIF)"
)
async def esya_ekle(interaction: discord.Interaction, esya_adi: str,
                    gorsel: discord.Attachment):
    await interaction.response.defer(ephemeral=True)
    await log_usage(interaction, "eşya-ekle")
    log_ch_id = await check_log_kanal(interaction)
    if not log_ch_id:
        stats_add(interaction, success=False)
        return
    if not gorsel.content_type or not gorsel.content_type.startswith("image/"):
        stats_add(interaction, success=False)
        return await interaction.followup.send(
            f"{e('hata')} Yalnızca resim dosyası yüklenebilir (PNG, JPG, GIF).", ephemeral=True)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT onaylandi FROM roblox_bagla WHERE discord_id = ? AND guild_id = ?",
            (interaction.user.id, interaction.guild_id)
        ) as cur:
            hesap_row = await cur.fetchone()
    if not hesap_row:
        stats_add(interaction, success=False)
        return await interaction.followup.send(
            f"{e('hata')} Önce `/hesap-bağla` ile Roblox hesabını bağla.", ephemeral=True)
    if hesap_row[0] != 1:
        stats_add(interaction, success=False)
        return await interaction.followup.send(
            f"{e('bekle')} Hesap bağlama talebiniz henüz onaylanmamış. "
            "Onaylandıktan sonra eşya ekleyebilirsiniz.", ephemeral=True)

    kullanici_gorsel = gorsel.url
    sistem_gorsel    = await _esya_gorsel_bul(esya_adi)

    # Kullanıcıya her iki fotoğrafı göster — karşılaştırma yapılsın
    onay_embed = discord.Embed(
        title="🔍 Fotoğraflar uyuşuyor mu?",
        description=(
            f"**{esya_adi}** adıyla talep oluşturulacak.\n\n"
            "**Büyük fotoğraf** → Senin yüklediğin\n"
            "**Küçük fotoğraf (sağ üst)** → Sistemdeki eşya\n\n"
            "İkisi aynı eşya mı?"
        ),
        color=discord.Color.blurple()
    )
    onay_embed.set_image(url=kullanici_gorsel)
    if sistem_gorsel:
        onay_embed.set_thumbnail(url=sistem_gorsel)
    else:
        onay_embed.add_field(
            name="⚠️ Sistem görseli yok",
            value="Bu eşya veritabanında bulunamadı. Yetkililer manuel kontrol yapacak.",
            inline=False
        )
    onay_embed.set_footer(text="Sadece sen görüyorsun • 3 dakika içinde seçim yap")
    view = EsyaOnaylamaView(
        interaction.user.id, esya_adi, sistem_gorsel, kullanici_gorsel, log_ch_id
    )
    stats_add(interaction)
    await interaction.followup.send(embed=onay_embed, view=view, ephemeral=True)

# /envanter-görüntüle
@tree.command(name="envanter-görüntüle", description="MM2 envanterini görüntüler.")
@app_commands.describe(kullanici="Görüntülenecek kullanıcı (boş = kendin)")
async def envanter_goruntule(interaction: discord.Interaction,
                             kullanici: discord.Member = None):
    await interaction.response.defer(ephemeral=True)
    await log_usage(interaction, "envanter-görüntüle")
    log_ch_id = await check_log_kanal(interaction)
    if not log_ch_id:
        stats_add(interaction, success=False)
        return
    target = kullanici or interaction.user
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT esya_adi, gorsel_url, eklendi_tarih FROM envanter WHERE discord_id = ?",
            (target.id,)
        ) as cur:
            rows = await cur.fetchall()
    if not rows:
        stats_add(interaction, success=False)
        return await interaction.followup.send("❌ Envanter boş.", ephemeral=True)

    # Tüm eşyaların değer + görsel bilgisini topla
    satirlar = []
    async with aiosqlite.connect(DB_PATH) as db:
        for esya, gorsel, _ in rows:
            async with db.execute(
                "SELECT deger_values, gorsel_url FROM degerler_cache WHERE esya_adi = ?",
                (esya.lower(),)
            ) as cur:
                cache_row = await cur.fetchone()
            if cache_row:
                val = cache_row[0]
                img = gorsel or cache_row[1]
            else:
                results = await search_mm2values(esya)
                best    = fuzzy_find(esya, results)
                val     = best["value"] if best else "?"
                img     = gorsel
            try:
                val_f = float(str(val).split("-")[0].strip().replace(",", ""))
            except Exception:
                val_f = val
            satirlar.append((esya, val_f, img))

    view  = EnvanterPaginatorView(target, satirlar)
    embed = view._embed_olustur()
    stats_add(interaction)
    await interaction.followup.send(embed=embed, view=view, ephemeral=True)

# /envanter-sil
@tree.command(name="envanter-sil", description="Kullanıcının envanterinden eşya siler.")
@app_commands.describe(kullanici="Kullanıcı", esya_adi="Silinecek eşya adı")
@app_commands.default_permissions(manage_guild=True)
async def envanter_sil(interaction: discord.Interaction,
                       kullanici: discord.Member, esya_adi: str):
    await interaction.response.defer(ephemeral=True)
    await log_usage(interaction, "envanter-sil")
    if not await is_yetkili(interaction):
        stats_add(interaction, success=False, unauth=True)
        return await interaction.followup.send("❌ Yetkiniz yok.", ephemeral=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM envanter WHERE discord_id = ? AND esya_adi LIKE ?",
            (kullanici.id, f"%{esya_adi}%"))
        await db.commit()
    stats_add(interaction)
    await interaction.followup.send(
        f"✅ {kullanici.mention} envanterinden `{esya_adi}` silindi.", ephemeral=True)

# /roblox-arat
@tree.command(name="roblox-arat", description="Roblox kullanıcısını arar ve sistem kaydını kontrol eder.")
@app_commands.describe(kullanici_adi="Roblox kullanıcı adı")
@app_commands.default_permissions(manage_guild=True)
async def roblox_arat(interaction: discord.Interaction, kullanici_adi: str):
    await interaction.response.defer(ephemeral=False)
    await log_usage(interaction, "roblox-arat")
    if not await is_yetkili(interaction):
        stats_add(interaction, success=False, unauth=True)
        return await interaction.followup.send("❌ Yetkiniz yok.")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://users.roblox.com/v1/usernames/users",
                json={"usernames": [kullanici_adi], "excludeBannedUsers": False},
                timeout=aiohttp.ClientTimeout(total=8)
            ) as r:
                if r.status != 200:
                    return await interaction.followup.send(
                        f"{e('hata')} Roblox kullanıcısı bulunamadı: `{kullanici_adi}`")
                data = await r.json()
        users = data.get("data", [])
        if not users:
            return await interaction.followup.send(f"{e('hata')} `{kullanici_adi}` bulunamadı.")

        roblox_id   = users[0].get("id")
        roblox_name = users[0].get("name", kullanici_adi)
        display_n   = users[0].get("displayName", roblox_name)

        avatar_url, profile_data = await asyncio.gather(
            roblox_fetch_avatar(roblox_id),
            roblox_fetch_profile(roblox_id)
        )

        embed = discord.Embed(
            title=f"{e('ara')} Roblox: {roblox_name}",
            url=f"https://www.roblox.com/users/{roblox_id}/profile",
            color=discord.Color.red())
        if display_n != roblox_name:
            embed.add_field(name="Görünen Ad", value=f"`{display_n}`", inline=True)
        embed.add_field(name="ID", value=f"`{roblox_id}`", inline=True)
        embed.add_field(name=f"{e('bilgi')} Profil",
                        value=f"[Roblox'ta Gör](https://www.roblox.com/users/{roblox_id}/profile)",
                        inline=True)
        if profile_data.get("description"):
            embed.add_field(name="📝 Açıklama",
                            value=profile_data["description"][:300], inline=False)
        if profile_data.get("created"):
            embed.add_field(name="Roblox Kayıt", value=profile_data["created"][:10], inline=True)

        # Sistem kaydı kontrolü
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT discord_id FROM roblox_bagla WHERE roblox_id = ?", (roblox_id,)
            ) as cur:
                db_row = await cur.fetchone()
        if db_row:
            embed.add_field(
                name=f"{e('kullanici')} Sisteme Kayıtlı",
                value=f"✅ <@{db_row[0]}>",
                inline=False)
        else:
            embed.add_field(
                name=f"{e('kullanici')} Sistem Kaydı",
                value="❌ Bu Roblox hesabı sisteme kayıtlı değil.",
                inline=False)

        if avatar_url:
            embed.set_thumbnail(url=avatar_url)
        stats_add(interaction)
        await interaction.followup.send(embed=embed)
    except Exception as ex:
        await log_error(interaction, "roblox-arat", str(ex))
        stats_add(interaction, success=False, error=True)
        await interaction.followup.send(f"{e('hata')} Hata: {ex}")

# /yapay-zeka-kur
@tree.command(name="yapay-zeka-kur", description="Seçilen kanala yapay zeka kurar.")
@app_commands.describe(kanal="Yapay zekanın aktif olacağı metin kanalı")
@app_commands.default_permissions(manage_guild=True)
async def yapay_zeka_kur(interaction: discord.Interaction, kanal: discord.TextChannel):
    if not await is_yetkili(interaction):
        stats_add(interaction, success=False, unauth=True)
        return await interaction.response.send_message("❌ Yetkiniz yok.", ephemeral=True)
    if not GEMINI_KEY:
        return await interaction.response.send_message(
            "❌ Yapay zeka için `GEMINI_API_KEY` secret'ını Replit Secrets'dan ekle.",
            ephemeral=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO settings (guild_id, ai_channel_id) VALUES (?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET ai_channel_id = ?",
            (interaction.guild_id, kanal.id, kanal.id))
        await db.commit()
    embed = discord.Embed(
        title=f"{e('robot')} Yapay Zeka Kuruldu",
        description=f"{kanal.mention} kanalına yapay zeka bağlandı.\n"
                    "O kanalda yazılan her mesaja belalı kişiliğiyle cevap verecek.",
        color=discord.Color.blurple())
    stats_add(interaction)
    await interaction.response.send_message(embed=embed)

# /özel-mesaj
@tree.command(name="özel-mesaj", description="Üyelere DM gönderir.")
@app_commands.describe(
    mesaj="Gönderilecek mesaj",
    kapsam="Kime gönderilecek: Sunucu (bu sunucu) veya Genel (tüm sunucular — sadece sahip)",
    hedef_rol="Belirli bir role gönder (kapsam Sunucu'da geçerli)",
    hedef_kullanici="Belirli bir kullanıcıya gönder",
    gizli_gonder="Göndereni gizle",
)
@app_commands.choices(kapsam=[
    app_commands.Choice(name="Sunucu", value="sunucu"),
    app_commands.Choice(name="Genel (tüm sunucular)", value="genel"),
])
@app_commands.default_permissions(manage_guild=True)
async def ozel_mesaj(
    interaction: discord.Interaction,
    mesaj: str,
    kapsam: app_commands.Choice[str] = None,
    hedef_rol: discord.Role = None,
    hedef_kullanici: discord.Member = None,
    gizli_gonder: bool = False,
):
    await interaction.response.defer(ephemeral=True)
    await log_usage(interaction, "özel-mesaj")
    if not await is_yetkili(interaction):
        stats_add(interaction, success=False, unauth=True)
        return await interaction.followup.send("❌ Yetkiniz yok.", ephemeral=True)

    kapsam_val = kapsam.value if kapsam else "sunucu"

    # Genel kapsam sadece bot sahibine açık
    if kapsam_val == "genel" and interaction.user.id != OWNER_ID:
        stats_add(interaction, success=False, unauth=True)
        return await interaction.followup.send(
            "❌ **Genel** kapsam yalnızca bot sahibi tarafından kullanılabilir.", ephemeral=True)

    bot_avatar = bot.user.display_avatar.url if bot.user else None
    sunucu_adi = interaction.guild.name if interaction.guild else "Bot"
    if kapsam_val == "genel":
        embed_title = "✉️ Mm2 Bot — Resmi Mesaj"
        embed_color = 0x2B2D31
    else:
        embed_title = f"📩 {sunucu_adi}"
        embed_color = 0x5865F2
    embed = discord.Embed(
        title=embed_title,
        description=f"\n{mesaj}\n",
        color=embed_color, timestamp=datetime.datetime.utcnow())

    if kapsam_val == "genel":
        # Genel modda: bot profil resmi, kaynak sunucu gizlenir
        embed.set_author(name="Mm2 Bot", icon_url=bot_avatar)
        embed.set_thumbnail(url=bot_avatar)
    elif interaction.guild:
        icon_url = interaction.guild.icon.url if interaction.guild.icon else None
        embed.set_author(name=interaction.guild.name, icon_url=icon_url)
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        if not gizli_gonder:
            embed.set_footer(text=f"Gönderen: {interaction.user.display_name}",
                             icon_url=interaction.user.display_avatar.url)
        else:
            embed.set_footer(text="Resmi Sunucu Mesajı")
    else:
        embed.set_footer(text="Resmi Mesaj")

    hedefler: list[discord.Member] = []
    if hedef_kullanici:
        hedefler = [hedef_kullanici]
    elif hedef_rol:
        hedefler = [m for m in hedef_rol.members if not m.bot]
    elif kapsam_val == "genel":
        # Tüm sunuculardaki benzersiz üyeler
        seen: set[int] = set()
        for guild in bot.guilds:
            for m in guild.members:
                if not m.bot and m.id not in seen:
                    hedefler.append(m)
                    seen.add(m.id)
    elif interaction.guild:
        hedefler = [m for m in interaction.guild.members if not m.bot]

    gonderilen = 0
    for member in hedefler:
        try:
            # Kullanıcının özel mesaj tercihini kontrol et
            if not await _tercih_al(member.id, "ozel_mesaj_dm", 1):
                continue
            await member.send(embed=embed)
            gonderilen += 1
            await asyncio.sleep(0.3)
        except discord.HTTPException:
            pass
    stats_add(interaction)
    kapsam_etiket = "tüm sunuculara" if kapsam_val == "genel" else "sunucuya"
    await interaction.followup.send(
        f"✅ {kapsam_etiket} `{gonderilen}` kişiye mesaj gönderildi.", ephemeral=True)

# /komut-kullanmayan-görüntüle
@tree.command(name="komut-kullanmayan-görüntüle",
              description="Komut kullanmayan üyeleri gösterir.")
@app_commands.describe(kapsam="Sunucu mu genel mi?", gun="Son kaç gün")
@app_commands.choices(kapsam=[
    app_commands.Choice(name="Sunucu", value="sunucu"),
    app_commands.Choice(name="Genel",  value="genel"),
])
@app_commands.default_permissions(administrator=True)
async def komut_kullanmayan(interaction: discord.Interaction,
                            kapsam: app_commands.Choice[str], gun: int = 30):
    if interaction.user.id != OWNER_ID:
        stats_add(interaction, success=False, unauth=True)
        return await interaction.response.send_message(
            "❌ Sadece bot sahibi kullanabilir.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    await log_usage(interaction, "komut-kullanmayan-görüntüle")
    since = (datetime.datetime.utcnow() - datetime.timedelta(days=gun)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        if kapsam.value == "sunucu":
            async with db.execute(
                "SELECT DISTINCT user_id FROM kullanim_log WHERE guild_id = ? AND tarih >= ?",
                (interaction.guild_id, since)
            ) as cur:
                kullananlar = {row[0] async for row in cur}
        else:
            async with db.execute(
                "SELECT DISTINCT user_id FROM kullanim_log WHERE tarih >= ?", (since,)
            ) as cur:
                kullananlar = {row[0] async for row in cur}
    if kapsam.value == "sunucu" and interaction.guild:
        tum   = [m for m in interaction.guild.members if not m.bot]
        kkmaz = [m for m in tum if m.id not in kullananlar]
        liste = ", ".join([m.mention for m in kkmaz[:30]])
        if len(kkmaz) > 30:
            liste += f" ... ve {len(kkmaz)-30} kişi daha"
        embed = discord.Embed(
            title=f"😴 Son {gun} Günde Komut Kullanmayanlar",
            description=liste or "Herkes komut kullanmış!",
            color=discord.Color.orange())
        embed.set_footer(text=f"Toplam: {len(kkmaz)} kişi")
    else:
        embed = discord.Embed(
            title=f"📊 Son {gun} Günde Kullananlar",
            description=f"Toplam `{len(kullananlar)}` kullanıcı.",
            color=discord.Color.orange())
    stats_add(interaction)
    await interaction.followup.send(embed=embed, ephemeral=True)

# /komut-kullandırt
@tree.command(name="komut-kullandırt", description="Komut kullanmayan üyelere DM atar.")
@app_commands.describe(kapsam="Sunucu mu genel mi?", gun="Son kaç gün")
@app_commands.choices(kapsam=[
    app_commands.Choice(name="Sunucu", value="sunucu"),
    app_commands.Choice(name="Genel",  value="genel"),
])
@app_commands.default_permissions(administrator=True)
async def komut_kullandirt(interaction: discord.Interaction,
                           kapsam: app_commands.Choice[str], gun: int = 30):
    if interaction.user.id != OWNER_ID:
        stats_add(interaction, success=False, unauth=True)
        return await interaction.response.send_message(
            "❌ Sadece bot sahibi kullanabilir.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    await log_usage(interaction, "komut-kullandırt")
    since = (datetime.datetime.utcnow() - datetime.timedelta(days=gun)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT DISTINCT user_id FROM kullanim_log WHERE tarih >= ?", (since,)
        ) as cur:
            kullananlar = {row[0] async for row in cur}
    if kapsam.value == "sunucu" and interaction.guild:
        hedefler = [m for m in interaction.guild.members if not m.bot and m.id not in kullananlar]
    else:
        seen, hedefler = set(), []
        for guild in bot.guilds:
            for m in guild.members:
                if not m.bot and m.id not in kullananlar and m.id not in seen:
                    hedefler.append(m)
                    seen.add(m.id)
    gonderilen = 0
    for member in hedefler:
        try:
            embed = discord.Embed(
                title="👋 Merhaba!",
                description=(
                    f"**{interaction.guild.name if interaction.guild else 'Sunucumuzdaki'}** "
                    "botun özelliklerini henüz denemedik!\n\n"
                    "• `/değer` — MM2 eşya değeri sorgula\n"
                    "• `/hesap-bağla` — Roblox hesabını bağla\n"
                    "• `/envanter-görüntüle` — Envanterini gör\n"
                    "• `/yardım` — Tüm komutlar\n\nHadi bir dene! 🎮"
                ),
                color=discord.Color.blurple())
            await member.send(embed=embed)
            gonderilen += 1
            await asyncio.sleep(0.5)
        except discord.HTTPException:
            pass
    stats_add(interaction)
    await interaction.followup.send(f"✅ `{gonderilen}` kişiye DM gönderildi.", ephemeral=True)

# /sunucular
@tree.command(name="sunucular", description="Botun bulunduğu sunucuları listeler.")
@app_commands.default_permissions(administrator=True)
async def sunucular(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        stats_add(interaction, success=False, unauth=True)
        return await interaction.response.send_message(
            "❌ Sadece bot sahibi kullanabilir.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    await log_usage(interaction, "sunucular")
    embed = discord.Embed(title=f"🌐 Bot Sunucuları ({len(bot.guilds)})",
                          color=discord.Color.blurple(), timestamp=datetime.datetime.utcnow())
    for guild in bot.guilds[:20]:
        embed.add_field(name=guild.name, value=f"👥 {guild.member_count} üye", inline=True)

    async def get_invite(guild: discord.Guild) -> str | None:
        try:
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).create_instant_invite:
                    inv = await asyncio.wait_for(
                        channel.create_invite(max_age=3600, max_uses=1, unique=True),
                        timeout=3.0)
                    return inv.url
        except Exception:
            pass
        return None

    invite_urls = await asyncio.gather(*[get_invite(g) for g in bot.guilds[:10]])
    davet_embed = discord.Embed(title="📨 Davet Linkleri",
                                color=discord.Color.green(), timestamp=datetime.datetime.utcnow())
    for guild, url in zip(bot.guilds[:10], invite_urls):
        davet_embed.add_field(
            name=guild.name,
            value=f"[Katıl]({url})" if url else "Davet oluşturulamadı",
            inline=False)
    stats_add(interaction)
    await interaction.followup.send(embeds=[embed, davet_embed], ephemeral=True)

# /durum
@tree.command(name="durum", description="Botun durumunu manuel olarak günceller.")
@app_commands.describe(durum_tipi="Durum tipi", metin="Durum metni")
@app_commands.choices(durum_tipi=[
    app_commands.Choice(name="🎮 Oynuyor",   value="playing"),
    app_commands.Choice(name="🎵 Dinliyor",  value="listening"),
    app_commands.Choice(name="📺 İzliyor",   value="watching"),
    app_commands.Choice(name="🏆 Yarışıyor", value="competing"),
    app_commands.Choice(name="❌ Temizle (varsayılan)",   value="clear"),
])
@app_commands.default_permissions(administrator=True)
async def durum(interaction: discord.Interaction,
                durum_tipi: app_commands.Choice[str], metin: str = ""):
    if interaction.user.id != OWNER_ID:
        stats_add(interaction, success=False, unauth=True)
        return await interaction.response.send_message(
            "❌ Sadece bot sahibi kullanabilir.", ephemeral=True)
    await log_usage(interaction, "durum")
    global _son_durum_metin, _son_durum_tip
    _durum_dongu_durdur()   # aktif döngüyü her koşulda durdur
    if durum_tipi.value == "clear":
        _son_durum_metin = ""
        _son_durum_tip   = ""
        await set_default_status()
        stats_add(interaction)
        return await interaction.response.send_message(
            f"{e('onay')} Bot durumu varsayılana döndürüldü. Aktif döngü durduruldu.",
            ephemeral=True)
    if not metin:
        return await interaction.response.send_message("❌ Durum metni girilmedi.", ephemeral=True)
    _son_durum_metin = metin
    _son_durum_tip   = durum_tipi.value
    await bot.change_presence(activity=_make_activity(durum_tipi.value, metin))
    stats_add(interaction)
    await interaction.response.send_message(
        f"✅ Durum güncellendi: **{durum_tipi.name}** → `{metin}`\n"
        f"💡 `/durum-dongu` kullanırsan bu mesaj döngüde 1. sıraya eklenir.",
        ephemeral=True)

# /durum-döngü
@tree.command(name="durum-dongu", description="Dönen bot durumu mesajları kurar.")
@app_commands.describe(
    mesajlar="Virgülle ayır: 'Mesaj1, Mesaj2, Mesaj3' (maks 5 mesaj)",
    tip="Tüm mesajların durum tipi",
    dakika="Kaç dakikada bir değişsin (min: 1, varsayılan: 5)",
)
@app_commands.choices(tip=[
    app_commands.Choice(name="🎮 Oynuyor",   value="playing"),
    app_commands.Choice(name="🎵 Dinliyor",  value="listening"),
    app_commands.Choice(name="📺 İzliyor",   value="watching"),
    app_commands.Choice(name="🏆 Yarışıyor", value="competing"),
])
@app_commands.default_permissions(administrator=True)
async def durum_dongu(
    interaction: discord.Interaction,
    tip: app_commands.Choice[str],
    mesajlar: str,
    dakika: int = 5,
):
    global _dongu_mesajlar, _dongu_index, _dongu_task
    if interaction.user.id != OWNER_ID:
        stats_add(interaction, success=False, unauth=True)
        return await interaction.response.send_message(
            "❌ Sadece bot sahibi kullanabilir.", ephemeral=True)
    dakika = max(1, dakika)
    await log_usage(interaction, "durum-dongu")

    parcalar = [m.strip() for m in mesajlar.split(",") if m.strip()][:5]
    if not parcalar:
        return await interaction.response.send_message(
            "❌ En az bir mesaj girilmeli.", ephemeral=True)

    _durum_dongu_durdur()

    # /durum ile ayarlanan son mesaj varsa döngünün başına ekle
    yeni_liste: list[dict] = []
    if _son_durum_metin:
        yeni_liste.append({"tip": _son_durum_tip or tip.value, "metin": _son_durum_metin})
    yeni_liste.extend({"tip": tip.value, "metin": p} for p in parcalar)

    _dongu_mesajlar = yeni_liste[:6]   # max 6 slot (1 /durum + 5 kullanıcı)
    _dongu_index    = 0
    _dongu_task     = asyncio.create_task(_durum_dongu_loop(dakika * 60))

    tip_adlar = {"playing": "🎮 Oynuyor", "listening": "🎵 Dinliyor",
                 "watching": "📺 İzliyor", "competing": "🏆 Yarışıyor"}
    liste_satirlari = []
    for i, slot in enumerate(_dongu_mesajlar):
        etiket = " ← /durum" if i == 0 and _son_durum_metin else ""
        slot_tip = tip_adlar.get(slot["tip"], slot["tip"])
        liste_satirlari.append(f"`{i+1}.` {slot['metin']} [{slot_tip}]{etiket}")
    liste = "\n".join(liste_satirlari)
    embed = discord.Embed(
        title="🔄 Dönen Durum Aktif",
        description=(
            f"**Aralık:** Her {dakika} dakikada bir\n\n"
            f"**Mesajlar:**\n{liste}"
        ),
        color=discord.Color.blurple()
    )
    embed.set_footer(text="Durdurmak için /durum → Temizle (varsayılan)")
    stats_add(interaction)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# /ai-sıfırla
@tree.command(name="ai-sıfırla", description="Kendi AI sohbet geçmişini ve stil tercihini sıfırlar.")
async def ai_sifirla(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await log_usage(interaction, "ai-sıfırla")
    guild_id = interaction.guild_id or 0
    user_id  = interaction.user.id
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM ai_hafiza WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        )
        await db.execute(
            "DELETE FROM ai_kullanici_stil WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        )
        await db.commit()
    stats_add(interaction)
    em = discord.Embed(
        title="🔄 AI Sıfırlandı",
        description=(
            "Sohbet geçmişin ve stil tercihin temizlendi.\n"
            "Bir sonraki mesajında nasıl konuşmamı istediğini belirteceksin.\n\n"
            "**Bot ile nasıl konuşulur?**\n"
            "• AI kanalına ya da bota DM olarak mesaj yaz.\n"
            "• Stil sorusunu cevapla: `samimi`, `kısa`, `resmi`, `eğlenceli` gibi.\n"
            "• Konuşma stilini değiştirmek için: `benimle daha resmi konuş` yaz.\n"
            "• Bir şeyi hafızalatmak için: `bana asla X deme` veya `beni Y olarak say` yaz.\n"
            "• Web'den anlık bilgi almak için soruyu normal yaz — bot otomatik arar.\n"
            "• Görsel için: `... göster` veya `... fotoğrafını bul` yaz.\n"
            "• Sıfırlamak için: `/ai-sıfırla` komutunu tekrar kullan."
        ),
        color=discord.Color.green()
    )
    await interaction.followup.send(embed=em, ephemeral=True)

# /tercihler
@tree.command(name="tercihler", description="Kişisel bildirim tercihlerini yönetir.")
async def tercihler(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await log_usage(interaction, "tercihler")
    user_id = interaction.user.id
    mevcut: dict[str, int] = {}
    for anahtar, _, _ in TERCIH_LISTESI:
        mevcut[anahtar] = await _tercih_al(user_id, anahtar, 1)
    view  = TercihlerView(user_id, mevcut)
    embed = view._embed()
    stats_add(interaction)
    await interaction.followup.send(embed=embed, view=view, ephemeral=True)

# ─── KEEP-ALIVE (botu canlı tutar) ───────────────────────────────────────────
from aiohttp import web as _aio_web

async def _keepalive_server():
    """8090 portunda basit bir HTTP sunucu açar — UptimeRobot bu adresi pinglesin."""
    async def _handle(request):
        return _aio_web.Response(text="OK")
    app = _aio_web.Application()
    app.router.add_get("/", _handle)
    app.router.add_get("/ping", _handle)
    runner = _aio_web.AppRunner(app)
    await runner.setup()
    site = _aio_web.TCPSite(runner, "0.0.0.0", 8090)
    await site.start()
    logger.info("Keep-alive sunucusu başladı: port 8090")

async def _self_ping_loop():
    """Her 7 dakikada bir kendi /ping adresine istek atar — Replit uyumasın."""
    await asyncio.sleep(30)  # Bot açılışında 30 saniye bekle
    replit_url = os.environ.get("REPLIT_DEV_DOMAIN", "")
    if not replit_url:
        logger.info("Self-ping: REPLIT_DEV_DOMAIN bulunamadı, atlanıyor.")
        return
    ping_url = f"https://{replit_url}/ping"
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(ping_url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    logger.info(f"Self-ping: {r.status} — {ping_url}")
            except Exception as ex:
                logger.warning(f"Self-ping hata: {ex}")
            await asyncio.sleep(7 * 60)  # 7 dakika


# ─── RUN ──────────────────────────────────────────────────────────────────────
async def _main():
    if not BOT_TOKEN:
        logger.error("DISCORD_TOKEN bulunamadı! Replit Secrets'a ekle.")
        exit(1)
    await _keepalive_server()
    asyncio.create_task(_self_ping_loop())
    await bot.start(BOT_TOKEN)

if __name__ == "__main__":
    asyncio.run(_main())
