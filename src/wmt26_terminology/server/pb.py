import httpx

from wmt26_terminology.server.config import settings

_OK = 200
_UNAUTHORIZED = 401
_FORBIDDEN = 403
_BAD_REQUEST = 400


class PocketBaseError(Exception):
    pass


class PocketBase:
    """Minimal async PocketBase REST client (superuser-scoped); collection
    rules lock the collections down, so all access goes through this backend."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(base_url=settings.pb_url, timeout=30.0)
        self._token: str | None = None

    async def _headers(self, refresh: bool = False) -> dict[str, str]:
        if self._token is None or refresh:
            response = await self._client.post(
                "/api/collections/_superusers/auth-with-password",
                json={"identity": settings.pb_superuser_email, "password": settings.pb_superuser_password},
            )
            if response.status_code != _OK:
                raise PocketBaseError(f"superuser auth failed: {response.status_code}")
            self._token = response.json()["token"]
        return {"Authorization": self._token or ""}

    async def _request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        response = await self._client.request(method, path, headers=await self._headers(), **kwargs)  # type: ignore[arg-type]
        # An expired token yields 403 ("only superusers ...") on rule-locked
        # collections, not 401, so both trigger a re-auth retry.
        if response.status_code in {_UNAUTHORIZED, _FORBIDDEN}:
            response = await self._client.request(method, path, headers=await self._headers(refresh=True), **kwargs)  # type: ignore[arg-type]
        if response.status_code >= _BAD_REQUEST:
            raise PocketBaseError(f"{method} {path}: {response.status_code} {response.text[:300]}")
        return response

    async def _page(self, collection: str, filter_: str, sort: str, per_page: int, page: int) -> dict:
        params: dict[str, object] = {"page": page, "perPage": per_page, "sort": sort}
        if filter_:
            params["filter"] = filter_
        response = await self._request("GET", f"/api/collections/{collection}/records", params=params)
        return response.json()

    async def list(self, collection: str, filter_: str = "", sort: str = "-created", per_page: int = 500) -> list[dict]:
        items: list[dict] = []
        page = 1
        while True:
            payload = await self._page(collection, filter_, sort, per_page, page)
            items.extend(payload["items"])
            if page >= payload["totalPages"]:
                return items
            page += 1

    async def first(self, collection: str, filter_: str) -> dict | None:
        items = (await self._page(collection, filter_, "-created", 1, 1))["items"]
        return items[0] if items else None

    async def create(self, collection: str, data: dict, files: dict | None = None) -> dict:
        if files:
            response = await self._request("POST", f"/api/collections/{collection}/records", data=data, files=files)
        else:
            response = await self._request("POST", f"/api/collections/{collection}/records", json=data)
        return response.json()

    async def update(self, collection: str, record_id: str, data: dict, files: dict | None = None) -> dict:
        if files:
            response = await self._request(
                "PATCH", f"/api/collections/{collection}/records/{record_id}", data=data, files=files
            )
        else:
            response = await self._request("PATCH", f"/api/collections/{collection}/records/{record_id}", json=data)
        return response.json()

    async def file_bytes(self, collection: str, record: dict, filename: str) -> bytes:
        response = await self._request("GET", f"/api/files/{collection}/{record['id']}/{filename}")
        return response.content

    async def close(self) -> None:
        await self._client.aclose()
