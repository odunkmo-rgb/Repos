import aiohttp

ROBLOX_API = "https://api.roblox.com"
USERS_API = "https://users.roblox.com"
THUMBNAILS_API = "https://thumbnails.roblox.com"


async def get_user_by_username(username: str) -> dict | None:
    async with aiohttp.ClientSession() as session:
        try:
            url = f"{USERS_API}/v1/usernames/users"
            payload = {"usernames": [username], "excludeBannedUsers": False}
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                users = data.get("data", [])
                if not users:
                    return None
                user = users[0]
                return {
                    "id": str(user["id"]),
                    "name": user["name"],
                    "display_name": user.get("displayName", user["name"]),
                }
        except Exception:
            return None


async def get_user_details(roblox_id: str) -> dict | None:
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{USERS_API}/v1/users/{roblox_id}") as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return {
                    "id": str(data["id"]),
                    "name": data["name"],
                    "display_name": data.get("displayName", data["name"]),
                    "description": data.get("description", ""),
                    "created": data.get("created", ""),
                }
        except Exception:
            return None


async def get_avatar_url(roblox_id: str) -> str:
    async with aiohttp.ClientSession() as session:
        try:
            url = (
                f"{THUMBNAILS_API}/v1/users/avatar-headshot"
                f"?userIds={roblox_id}&size=420x420&format=Png&isCircular=false"
            )
            async with session.get(url) as resp:
                if resp.status != 200:
                    return ""
                data = await resp.json()
                items = data.get("data", [])
                if items and items[0].get("state") == "Completed":
                    return items[0].get("imageUrl", "")
                return ""
        except Exception:
            return ""


async def search_users(keyword: str) -> list:
    async with aiohttp.ClientSession() as session:
        try:
            url = f"{USERS_API}/v1/users/search?keyword={keyword}&limit=5"
            async with session.get(url) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return data.get("data", [])
        except Exception:
            return []
