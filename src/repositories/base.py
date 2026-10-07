from motor.motor_asyncio import AsyncIOMotorCollection
from typing import Any, Dict, List, Optional
from src.core.database import Database

class BaseRepository:
    def __init__(self, collection_name: str):
        self.collection_name = collection_name

    @property
    def col(self) -> AsyncIOMotorCollection:
        return Database.db[self.collection_name]

    async def insert_one(self, document: Dict[str, Any]) -> str:
        res = await self.col.insert_one(document)
        return str(res.inserted_id)

    async def find_one(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return await self.col.find_one(query)

    async def find_many(self, query: Dict[str, Any], limit: int = 0) -> List[Dict[str, Any]]:
        cursor = self.col.find(query)
        if limit > 0:
            cursor = cursor.limit(limit)
        return await cursor.to_list(length=None)

    async def update_one(self, query: Dict[str, Any], update: Dict[str, Any], upsert: bool = False) -> int:
        res = await self.col.update_one(query, update, upsert=upsert)
        return res.modified_count

    async def delete_many(self, query: Dict[str, Any]) -> int:
        res = await self.col.delete_many(query)
        return res.deleted_count
