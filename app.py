import asyncpg
import creds
import jwt
import re
import time

from fastapi import FastAPI, Header, Response, status, Depends
from fastapi_asyncpg import configure_asyncpg
from loguru import logger
from pydantic import BaseModel
from typing import Optional, List

app = FastAPI()
db = configure_asyncpg(app, creds.pg)

tag_validator = re.compile("^#?[PYLQGRJCUV0289]+$")


class Link(BaseModel):
    playerTag: str
    discordId: str


class User(BaseModel):
    username: str
    password: str


class Message(BaseModel):
    message: str


class Token(BaseModel):
    token: str


def get_jwt(username, user_id):
    payload = {"username": username, "user_id": user_id, "exp": time.time() + 7200.0}
    return jwt.encode(payload, creds.jwt_key, algorithm="HS256")


def decode_jwt(authorization):
    try:
        decoded = jwt.decode(authorization[7:], creds.jwt_key, algorithms="HS256")
        return decoded
    except:
        return None


@db.on_init
async def initialization(conn):
    # fastapi_asyncpg seems to freak out if you don't do some kind of initialization
    await conn.execute("SELECT 1")


@app.get("/", response_model=Message)
async def index():
    return {"message": "Hello world!"}


@app.post("/login", responses={200: {"model": Token}, 401: {"model": Message}})
async def login(user: User, response: Response, conn=Depends(db.connection)):
    logger.info(f"Login attempt by: {user.username}")
    print(user)
    sql = "SELECT user_id FROM coc_discord_users WHERE username = $1 and passwd = $2 and approved = True"
    user_id = await conn.fetchval(sql, user.username, user.password)
    if not user_id:
        logger.warning(f"Login attempt by {user.username} failed. Password provided: {user.password}")
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return {"message": "Not a valid user/password combination"}
    else:
        logger.info(f"Login by {user.username} successful.")
        token = get_jwt(user.username, user_id)
        return {"token": token}


@app.get("/links/{tag_or_id}", responses={200: {"model": List[Link]}, 400: {"model": Message}, 401: {"model": Message}})
async def get_links(tag_or_id: str,
                    response: Response,
                    authorization: Optional[str] = Header(None),
                    conn=Depends(db.connection)):
    jwt_payload = decode_jwt(authorization)
    if not jwt_payload:
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return {"message": "Token is invalid"}
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
            return {"message": "Not a valid player tag"}
        sql = "SELECT discordid FROM coc_discord_links WHERE playertag = $1"
        discord_id = await conn.fetchval(sql, player_tag)
        tags.append({"playerTag": player_tag, "discordId": str(discord_id)})
    return tags


@app.post("/batch", responses={200: {"model": List[Link]}, 401: {"model": Message}})
async def get_batch(user_input: list,
                    response: Response,
                    authorization: Optional[str] = Header(None),
                    conn=Depends(db.connection)):
    jwt_payload = decode_jwt(authorization)
    if not jwt_payload:
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return {"message": "Token is invalid"}
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
                # Not a valid Player tag or Discord ID
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
    return pairs


@app.post("/links",
          responses={
              200: {"model": Message}, 400: {"model": Message}, 401: {"model": Message}, 409: {"model": Message}
          })
async def add_link(link: Link,
                   response: Response,
                   authorization: Optional[str] = Header(None),
                   conn=Depends(db.connection)):
    jwt_payload = decode_jwt(authorization)
    if not jwt_payload:
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return {"message": "Token is invalid"}
    if not tag_validator.match(link.playerTag):
        response.status_code = status.HTTP_400_BAD_REQUEST
        return {"message": "Not a valid player tag"}
    sql = "INSERT INTO coc_discord_links (playertag, discordid) VALUES ($1, $2)"
    try:
        await conn.execute(sql, link.playerTag, int(link.discordId))
    except asyncpg.exceptions.UniqueViolationError:
        response.status_code = status.HTTP_409_CONFLICT
        return {"message": "Player tag is already in the database"}
    except:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return {"message": "Unknown exception"}

    # Logging
    sql = "INSERT INTO coc_discord_log (user_id, activity, playertag, discordid) VALUES ($1, $2, $3, $4)"
    await conn.execute(sql, jwt_payload['user_id'], "ADD", link.playerTag, int(link.discordId))
    return {"message": "OK"}


@app.delete("/links/{tag}", responses={200: {"model": Message}, 400: {"model": Message}, 401: {"model": Message}})
async def delete_link(tag: str,
                      response: Response,
                      authorization: Optional[str] = Header(None),
                      conn=Depends(db.connection)):
    jwt_payload = decode_jwt(authorization)
    if not jwt_payload:
        response.status_code = status.HTTP_401_UNAUTHORIZED
        return {"message": "Token is invalid"}
    if tag.startswith("#"):
        player_tag = tag.upper()
    else:
        player_tag = f"#{tag.upper()}"
    sql = "SELECT discordid FROM coc_discord_links WHERE playertag = $1"
    discord_id = await conn.fetchval(sql, player_tag)
    if not discord_id:
        response.status_code = status.HTTP_404_NOT_FOUND
        return {"message": "Player tag not found in database"}
    sql = "DELETE FROM coc_discord_links WHERE playertag = $1"
    await conn.execute(sql, player_tag)
    
    # Logging
    sql = "INSERT INTO coc_discord_log (user_id, activity, playertag, discordid) VALUES ($1, $2, $3, $4)"
    await conn.execute(sql, jwt_payload['user_id'], "DELETE", player_tag, discord_id)
    return {"message": "OK"}
