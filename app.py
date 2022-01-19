import asyncpg
import creds
import jwt
import re
import time

from fastapi import FastAPI, Header, Response, status, Depends
from fastapi_asyncpg import configure_asyncpg
from loguru import logger
from pydantic import BaseModel
from typing import Optional

app = FastAPI()
db = configure_asyncpg(app, creds.pg)

tag_validator = re.compile("^#?[PYLQGRJCUV0289]+$")


class Link(BaseModel):
    playerTag: str
    discordId: int


class User(BaseModel):
    username: str
    password: str
    user_id: int = None
    expiry: float = None


def get_jwt(user_id, expires):
    payload = {"user_id": user_id, "exp": expires}
    return jwt.encode(payload, creds.jwt_key, algorithm="HS256")


def decode_jwt(token):
    decoded = jwt.decode(token, creds.jwt_key, algorithms="HS256")
    return decoded


def check_token(token):
    try:
        jwt.decode(token, creds.jwt_key, algorithms="HS256")
        return True
    except jwt.ExpiredSignatureError:
        return False


@db.on_init
async def initialization(conn):
    # fastapi_asyncpg seems to freak out if you don't do some kind of initialization
    await conn.execute("SELECT 1")


@app.get("/")
async def index():
    return {"message": "Hello world!"}


@app.post("/login")
async def login(user: User, response: Response, conn=Depends(db.connection)):
    logger.info(f"Login attempt by: {user.username}")
    sql = "SELECT user_id FROM coc_discord_users WHERE username = $1 and passwd = $2 and approved = True"
    user.user_id = await conn.fetchval(sql, user.username, user.password)
    if not user.user_id:
        logger.warning(f"Login attempt by {user.username} failed. Password provided: {user.password}")
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return {"Error message": "Not a valid user/password combination."}
    else:
        logger.info(f"Login by {user.username} successful.")
        user.expiry = time.time() + 7200.0  # two hours
        token = get_jwt(user.user_id, user.expiry)
        return {"token": token}


@app.get("/links/{tag_or_id}")
async def get_links(tag_or_id: str,
                    response: Response,
                    authorization: Optional[str] = Header(None),
                    conn=Depends(db.connection)):
    if not check_token(authorization[7:]):
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return {"Error message": "Token is invalid"}
    tags = []
    try:
        # Try and convert input to int
        # If successful, it's a Discord ID
        discord_id = int(tag_or_id)
        sql = "SELECT playertag FROM coc_discord_links WHERE discordid = $1"
        fetch = await conn.fetch(sql, discord_id)
        for row in fetch:
            tags.append({"playerTag": row[0], "discordId": str(discord_id)})
    except ValueError:
        # If it fails, it's a player tag
        if tag_or_id.startswith("#"):
            player_tag = tag_or_id.upper()
        else:
            player_tag = f"#{tag_or_id.upper()}"
        if not tag_validator.match(player_tag):
            response.status_code = status.HTTP_400_BAD_REQUEST
            return {"Error message": "Not a valid player tag."}
        sql = "SELECT discordid FROM coc_discord_links WHERE playertag = $1"
        discord_id = await conn.fetchval(sql, player_tag)
        tags.append({"playerTag": player_tag, "discordId": str(discord_id)})
    await conn.close()
    return tags


@app.post("/batch")
async def get_batch(user_input: list,
                    response: Response,
                    authorization: Optional[str] = Header(None),
                    conn=Depends(db.connection)):
    if not check_token(authorization[7:]):
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return {"Error message": "Token is invalid"}
    tags = []
    ids = []
    for tag_or_id in user_input:
        if re.match(tag_validator, tag_or_id):
            if tag_or_id.startswith("#"):
                player_tag = tag_or_id.upper()
            else:
                player_tag = f"#{tag_or_id.upper()}"
            tags.append(player_tag)
        else:
            try:
                ids.append(int(tag_or_id))
            except ValueError:
                # not a valid player tag or discord ID
                pass
    pairs = []
    tag_sql = "SELECT playertag, discordid FROM coc_discord_links WHERE playertag = any($1::text[])"
    id_sql = "SELECT playertag, discordid FROM coc_discord_links WHERE discordid = any($1::bigint[])"
    # handle player tags in list
    fetch = await conn.fetch(tag_sql, tags)
    for row in fetch:
        pairs.append({"playerTag": row[0], "discordId": str(row[1])})
    # handle Discord IDs
    fetch = await conn.fetch(id_sql, ids)
    for row in fetch:
        pairs.append({"playerTag": row[0], "discordId": str(row[1])})
    await conn.close()
    return pairs


@app.post("/links", status_code=status.HTTP_200_OK)
async def add_link(link: Link,
                   response: Response,
                   authorization: Optional[str] = Header(None),
                   conn=Depends(db.connection)):
    if not check_token(authorization[7:]):
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return {"Error message": "Token is invalid"}
    if not tag_validator.match(link.playerTag):
        response.status_code = status.HTTP_400_BAD_REQUEST
        return {"Error message": "Not a valid player tag."}
    sql = "INSERT INTO coc_discord_links (playertag, discordid) VALUES ($1, $2)"
    try:
        await conn.execute(sql, link.playerTag, link.discordId)
    except asyncpg.exceptions.UniqueViolationError:
        response.status_code = status.HTTP_409_CONFLICT
    except:
        response.status_code = status.HTTP_400_BAD_REQUEST
    # Logging
    jwt_payload = decode_jwt(authorization[7:])
    sql = "INSERT INTO coc_discord_log (user_id, activity, playertag, discordid) VALUES ($1, $2, $3, $4)"
    await conn.execute(sql, jwt_payload['user_id'], "ADD", link.playerTag, link.discordId)
    await conn.close()
    return {}


@app.delete("/links/{tag}")
async def delete_link(tag: str,
                      response: Response,
                      authorization: Optional[str] = Header(None),
                      conn=Depends(db.connection)):
    if not check_token(authorization[7:]):
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return {"Error message": "Token is invalid"}
    if tag.startswith("#"):
        player_tag = tag.upper()
    else:
        player_tag = f"#{tag.upper()}"
    sql = "SELECT discordid FROM coc_discord_links WHERE playertag = $1"
    discord_id = await conn.fetchval(sql, player_tag)
    if not discord_id:
        response.status_code = status.HTTP_404_NOT_FOUND
        return {"Error message": "Player tag not found in database"}
    sql = "DELETE FROM coc_discord_links WHERE playertag = $1"
    await conn.execute(sql, player_tag)
    # Logging
    jwt_payload = decode_jwt(authorization[7:])
    sql = "INSERT INTO coc_discord_log (user_id, activity, playertag, discordid) VALUES ($1, $2, $3, $4)"
    await conn.execute(sql, jwt_payload['user_id'], "DELETE", player_tag, discord_id)
    await conn.close()
    return {}
