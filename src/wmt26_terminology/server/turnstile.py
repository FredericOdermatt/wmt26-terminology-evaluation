import httpx

from wmt26_terminology.server.config import settings

_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def verify(token: str, remote_ip: str | None) -> bool:
    if not settings.turnstile_secret:
        return True
    payload = {"secret": settings.turnstile_secret, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(_VERIFY_URL, data=payload)
        except httpx.HTTPError:
            # Cloudflare outage must not lock participants out entirely;
            # rate limits remain as the backstop.
            return True
    return bool(response.json().get("success"))
