"""CI-only bootstrap for a downloaded mongod or a locally configured instance."""

import os
import time

from pymongo import MongoClient
from pymongo.errors import PyMongoError

client = MongoClient(
    os.environ.get("TEST_MONGO_URI", "mongodb://localhost:27017"),
    directConnection=True,
    serverSelectionTimeoutMS=1000,
)
deadline = time.monotonic() + 60
initiated = False
while time.monotonic() < deadline:
    try:
        client.admin.command("ping")
        if os.environ.get("MONGO_MODE") == "replica":
            if not initiated:
                try:
                    client.admin.command(
                        "replSetInitiate",
                        {"_id": "rs0", "members": [{"_id": 0, "host": "localhost:27017"}]},
                    )
                except PyMongoError as error:
                    if getattr(error, "code", None) != 23:  # AlreadyInitialized
                        raise
                initiated = True
            if not client.admin.command("hello").get("isWritablePrimary"):
                time.sleep(0.2)
                continue
        break
    except PyMongoError:
        time.sleep(0.2)
else:
    raise SystemExit("MongoDB did not become ready within 60 seconds")
client.close()
