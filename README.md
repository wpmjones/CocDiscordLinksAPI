# CocDiscordLinkAPI

## About
CocDiscordLinkAPI is a service created for Clash of Clans Discord bot developers. The purpose is to be a central repository for links between Clash of Clans player accounts and their Discord account. 

This is a REST-based service, hosted in PYthon. It requires a username/password to use. To request a login, join the Clash API Developers server and send a message in #coc-discord-link-api. Click here to join: https://discord.gg/clashapi

## Using the Service

### Authentication
POST - https://cocdiscordlink.azurewebsites.net/api/login

Payload Example:
```json
{
    "username": "accountname", 
    "password": "accountpassword"
}
```

If successful, you will receive a 200 OK message, with your token
```json
{
    "token": "23jl2k3jh23jKLKk3lh2Kl.A5D46d2312eFealkjkl3Jkl.x923laslkjlKLJlk32lkJlk12jKl3lkjKLJKl1355a"
}
```
If not successful, you will receive a 401 Unauthorized message.

**Retrieving the token expiration time**

Tokens are only valid for 2 hours from the time they are issued. Expiration time is stored in UTC as a claim on the token. Below is an example in C# using Jwt.NET of how to obtain the expiration:

```csharp
var token = "23jl2k3jh23jKLKk3lh2Kl.A5D46d2312eFealkjkl3Jkl.x923laslkjlKLJlk32lkJlk12jKl3lkjKLJKl1355a";
var jwt = new JwtBuilder().WithAlgorithm(new HMACSHA256Algorithm())
    .Decode<Dictionary<string, object>>(token);
var tokenExpireTime = DateTimeOffset.FromUnixTimeSeconds(Convert.ToUInt32(jwt["exp"]));
```

### Retrieving a Link by Player Tag
GET - https://cocdiscordlink.azurewebsites.net/api/links/{tag}

*Note: You do not need to include the # in the query, but if you do, be sure to encode it to %23*

Example(s):
```
https://cocdiscordlink.azurewebsites.net/api/links/RQ33GCCG (no #)
https://cocdiscordlink.azurewebsites.net/api/links/%23RQ33GCCG (# is encoded)
```
Returns:
```json
[
    {
        "playerTag": "#RQ33GCCG",
        "discordId": "658256846652301451"
    }
]
```

### Retrieving a Link by DiscordId
GET - https://cocdiscordlink.azurewebsites.net/api/links/{id}

Example(s):
```
https://cocdiscordlink.azurewebsites.net/api/links/658256846652301451
```
Returns:
```json
[
    {
        "playerTag": "#RQ33GCCG",
        "discordId": "658256846652301451"
    }
]
```

### Retrieving Multiples in Batch
POST - https://cocdiscordlink.azurewebsites.net/api/links/batch

*Note: This payload can take both DiscordIds and Player Tags both, and they can be mix-and-matched, as in the example below:*

Payload Example (JSON string array):

```json
[
    "658256846652301451",
    "Q802PFCGG"
]
```

Results Example:
```json
[
    {
        "playerTag": "#RQ33GCCG",
        "discordId": "658256846652301451"
    },
    {
        "playerTag": "#Q802PFCGG",
        "discordId": "655321455562025874"
    }    
]
```
**Return Values**
Success: 200 OK 
No records: 404 Not Found

### Adding a New Link
POST - https://cocdiscordlink.azurewebsites.net/api/links

Payload Example: 
```json
{
    "playerTag": "#RQ33GCCG",
    "discordId": "658256846652301451"
}
```

**Return Values:**
Successful result: 200 OK
Player already exists: 409 Conflict

### Deleting an Existing Link
DELETE - https://cocdiscordlink.azurewebsites.net/api/links/{tag}

*Note: This only works on Clash of Clans Player Tags*

Example(s):
```
https://cocdiscordlink.azurewebsites.net/api/links/RQ33GCCG (no #)
https://cocdiscordlink.azurewebsites.net/api/links/%23RQ33GCCG (# is encoded)
```

**Return Values:**
Success: 200 OK
Player does not exist: 404 Not Found
