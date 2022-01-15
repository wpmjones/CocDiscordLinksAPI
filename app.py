import asyncpg
import creds
import jwt
import re
import time

from fastapi import FastAPI, Header, Response, status
from loguru import logger
from pydantic import BaseModel
from typing import Optional

app = FastAPI()

tag_validator = re.compile("^#?[PYLQGRJCUV0289]+$")


class Link(BaseModel):
    playerTag: str
    discordId: int


class User(BaseModel):
    username: str
    password: str
    expiry: float = None


def get_jwt(username, expires):
    payload = {"username": username, "expiry": expires}
    logger.info(payload)
    return jwt.encode(payload, creds.jwt_key, algorithm="HS256")


def check_token(token):
    decoded = jwt.decode(token, creds.jwt_key, algorithms="HS256")
    if check_expiry(decoded['expiry']):
        return True
    else:
        return False


def check_expiry(expiry: float):
    if expiry > time.time():
        return True
    else:
        return False


@app.post("/login")
async def login(user: User, response: Response):
    logger.info(f"Login attempt by: {user.username}")
    conn = await asyncpg.connect(dsn=creds.pg)
    sql = "SELECT user_id, expiry FROM coc_discord_users WHERE username = $1 and passwd = $2 and approved = True"
    row = await conn.fetchrow(sql, user.username, user.password)
    if not row:
        logger.warning(f"Login attempt by {user.username} failed. Password provided: {user.password}")
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return "Not a valid user/password combination."
    if row[1]:
        # value exists in db, test for expiration
        user.expiry = row[1]
        if check_expiry(user.expiry):
            # existing token still valid, send to user
            logger.info("Existing valid token")
            token = get_jwt(user.username, user.expiry)
            return token
    # either no token exists or it has expired
    logger.info(f"Creating new token for {user.username}")
    user.expiry = time.time() + 7200.0  # two hours
    sql = "UPDATE coc_discord_users SET expiry = $1 WHERE user_id = $2"
    await conn.execute(sql, user.expiry, row['user_id'])
    token = get_jwt(user.username, user.expiry)
    return token


@app.get("/links/{tag_or_id}")
async def get_links(tag_or_id: str, response: Response, authorization: Optional[str] = Header(None)):
    if not check_token(authorization[7:]):
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return "Token is invalid"
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
    await conn.close()
    return tags


@app.get("/batch")
async def get_batch(user_input: list, response: Response, authorization: Optional[str] = Header(None)):
    if not check_token(authorization[7:]):
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return "Token is invalid"
    conn = await asyncpg.connect(dsn=creds.pg)
    tags = []
    for item in user_input:
        try:
            # Try and convert input to int
            # If successful, it's a Discord ID
            discord_id = int(item)
            sql = "SELECT playertag FROM coc_discord_links WHERE discordid = $1"
            fetch = await conn.fetch(sql, discord_id)
            for row in fetch:
                tags.append({"playerTag": row[0], "discordId": discord_id})
        except ValueError:
            # If it fails, it's a player tag
            if item.startswith("#"):
                player_tag = item.upper()
            else:
                player_tag = f"#{item.upper()}"
            if not tag_validator.match(player_tag):
                response.status_code = status.HTTP_400_BAD_REQUEST
                return "Not a valid player tag."
            sql = "SELECT discordid FROM coc_discord_links WHERE playertag = $1"
            discord_id = await conn.fetchval(sql, player_tag)
            if discord_id:
                tags.append({"playerTag": player_tag, "discordId": discord_id})
    await conn.close()
    if len(tags) == 0:
        response.status_code = status.HTTP_404_NOT_FOUND
        return
    return tags


@app.post("/links", status_code=status.HTTP_200_OK)
async def add_link(link: Link, response: Response, authorization: Optional[str] = Header(None)):
    if not check_token(authorization[7:]):
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return "Token is invalid"
    if not tag_validator.match(link.playerTag):
        response.status_code = status.HTTP_400_BAD_REQUEST
        return "Not a valid player tag."
    conn = await asyncpg.connect(dsn=creds.pg)
    sql = "INSERT INTO coc_discord_links (playertag, discordid) VALUES ($1, $2)"
    try:
        await conn.execute(sql, link.playerTag, link.discordId)
    except asyncpg.exceptions.UniqueViolationError:
        response.status_code = status.HTTP_409_CONFLICT
    except:
        response.status_code = status.HTTP_400_BAD_REQUEST
    await conn.close()
    return


@app.delete("/links/{tag_or_id}")
async def delete_link(tag: str, response: Response, authorization: Optional[str] = Header(None)):
    if not check_token(authorization[7:]):
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return "Token is invalid"
    conn = await asyncpg.connect(dsn=creds.pg)
    if tag.startswith("#"):
        player_tag = tag.upper()
    else:
        player_tag = f"#{tag.upper()}"
    sql = "SELECT discordid FROM coc_discord_links WHERE playertag = $1"
    fetch = await conn.fetch(sql, player_tag)
    if len(fetch) == 0:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "Player tag not found in database"
    sql = "DELETE FROM coc_discord_links WHERE playertag = $1"
    await conn.execute(sql, player_tag)
    await conn.close()
    return
