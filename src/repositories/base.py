from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection

from src.core.database import Database, _session


class BaseRepository:
    def __init__(self, collection_name: str):
        self.collection_name = collection_name

    @property
    def col(self) -> AsyncIOMotorCollection:
        return Database.db[self.collection_name]

    async def insert_one(self, document: dict[str, Any]) -> str:
        res = await self.col.insert_one(document, session=_session.get())
        return str(res.inserted_id)

    async def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        return await self.col.find_one(query, session=_session.get())

    async def find_many(self, query: dict[str, Any], limit: int = 0) -> list[dict[str, Any]]:
        cursor = self.col.find(query, session=_session.get())
        if limit > 0:
            cursor = cursor.limit(limit)
        return await cursor.to_list(length=None)

    async def update_one(
        self, query: dict[str, Any], update: dict[str, Any], upsert: bool = False
    ) -> int:
        res = await self.col.update_one(query, update, upsert=upsert, session=_session.get())
        return res.modified_count

    async def delete_many(self, query: dict[str, Any]) -> int:
        res = await self.col.delete_many(query, session=_session.get())
        return res.deleted_count

    async def count(self, query: dict[str, Any]) -> int:
        return await self.col.count_documents(query)
