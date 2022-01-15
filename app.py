import asyncpg
import creds
import re

from fastapi import FastAPI, Path, Response, status
from loguru import logger
from pydantic import BaseModel, Field
from typing import Union

app = FastAPI()

# tag_validator = re.compile("^#?[PYLQGRJCUV0289]+$")


class Link(BaseModel):
    playerTag: str   # = Field(regex="^#?[PYLQGRJCUV0289]+$", description="")
    discordId: int


@app.get("/")
async def root():
    logger.info("Hello world")
    return {"message": "Hello world"}


@app.get("/links/{tag_or_id}")
async def get_links(tag_or_id: str):
    try:
        # Try and convert input to int
        # If successful, it's a Discord ID
        discordId = int(tag_or_id)
        playerTag = "blank"
    except ValueError:
        # If it fails, it's a player tag
        playerTag = tag_or_id
        discordId = 0
        logger.info(playerTag)
    response = Link(playerTag=playerTag, discordId=discordId)
    return response


@app.post("/links", status_code=status.HTTP_200_OK)
async def add_link(link: Link, response: Response):
    conn = await asyncpg.connect(dsn=creds.pg)
    sql = "INSERT INTO coc_discord_links (playerTag, discordId) VALUES ($1, $2)"
    try:
        await conn.execute(sql, link.playerTag, link.discordId)
    except:
        logger.exception("Failure")
        response.status_code = status.HTTP_409_CONFLICT
    await conn.close()
    return link
