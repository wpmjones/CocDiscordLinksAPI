import asyncpg

from fastapi import FastAPI
from loguru import logger
from pydantic import BaseModel

app = FastAPI()


class Link(BaseModel):
    playerTag: str
    discordId: int


@app.get("/")
async def root():
    logger.info("Hello world")
    return {"message": "Hello world"}


# @app.get("/links")
# async def get_links(tag_or_id: str):
#     try:
#         # Try and convert input to int
#         # If successful, it's a Discord ID
#         discordId = int(tag_or_id)
#         playerTag = ""
#     except ValueError:
#         # If it fails, it's a player tag
#         playerTag = tag_or_id
#         discordId = 0
#         logger.info(playerTag)
