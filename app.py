import asyncpg
import creds
import re

from temp import fred
from fastapi import FastAPI, Response, status
from loguru import logger
from pydantic import BaseModel

app = FastAPI()

tag_validator = re.compile("^#?[PYLQGRJCUV0289]+$")


class Link(BaseModel):
    playerTag: str
    discordId: int


@app.get("/")
async def root():
    conn = await asyncpg.connect(dsn=creds.pg)
    sql = "INSERT INTO coc_discord_links (playertag, discordid) VALUES ($1, $2)"
    for x in fred:
        await conn.execute(sql, x['playerTag'], x['discordId'])
    await conn.close()
    return "Success"


@app.get("/links/{tag_or_id}")
async def get_links(tag_or_id: str, response: Response):
    conn = await asyncpg.connect(dsn=creds.pg)
    tags = []
    try:
        # Try and convert input to int
        # If successful, it's a Discord ID
        discord_id = int(tag_or_id)
        sql = "SELECT playertag FROM coc_discord_links WHERE discordid = $1"
        fetch = await conn.fetch(sql, discord_id)
        for row in fetch:
            tags.append({"playerTag": row[0], "discordId": discord_id})
    except ValueError:
        # If it fails, it's a player tag
        if tag_or_id.startswith("#"):
            player_tag = tag_or_id.upper()
        else:
            player_tag = f"#{tag_or_id.upper()}"
        if not tag_validator.match(player_tag):
            response.status_code = status.HTTP_400_BAD_REQUEST
            return "Not a valid player tag."
        sql = "SELECT discordid FROM coc_discord_links WHERE playertag = $1"
        discord_id = await conn.fetchval(sql, player_tag)
        tags.append({"playerTag": player_tag, "discordId": discord_id})
    return tags


@app.post("/links", status_code=status.HTTP_200_OK)
async def add_link(link: Link, response: Response):
    if not tag_validator.match(link.playerTag):
        response.status_code = status.HTTP_400_BAD_REQUEST
        return "Not a valid player tag."
    conn = await asyncpg.connect(dsn=creds.pg)
    sql = "INSERT INTO coc_discord_links (playertag, discordid) VALUES ($1, $2)"
    try:
        await conn.execute(sql, link.playerTag, link.discordId)
    except:
        response.status_code = status.HTTP_409_CONFLICT
    await conn.close()
    return
