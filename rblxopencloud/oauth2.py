from .exceptions import rblx_opencloudException, InvalidKey, ServiceUnavailable, InsufficientScope, InvalidCode
from urllib import parse
import datetime, time
from typing import Optional, Union, TYPE_CHECKING
from .user import User
from .group import Group
from .experience import Experience
import base64, jwt
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, load_der_public_key
from cryptography.hazmat.backends import default_backend
import hashlib, string, secrets
from . import send_request, iterate_request

__all__ = (
    "Resources",
    "AccessTokenInfo",
    "PartialAccessToken",
    "AccessToken",
    "OAuth2App"
)

class AccessTokenInfo():
    """
    Contains information about a access token. 
    """

    def __init__(self, data: dict):
        self.active: bool = data["active"]
        self.id: str = data["jti"]
        self.client_id: int = int(data["client_id"])
        self.user_id: int = data["sub"]
        self.scope: list[str] = data["scope"].split(" ")
        self.expires_at: datetime.datetime = (
            datetime.datetime.fromtimestamp(data["exp"])
        )
        self.issued_at: datetime.datetime = (
            datetime.datetime.fromtimestamp(data["iat"])
        )
    
    def __repr__(self) -> str:
        return f"<rblxopencloud.AccessTokenInfo \
id=\"{self.id}\" user_id={self.user_id}>"

class Resources():
    """
    Contains the authorized users, groups, and experiences for the \
    authorization.
    """

    def __init__(self, experiences, accounts):
        self.experiences: list[Experience] = experiences
        self.accounts: list[Union[User, Group]] = accounts
    
    def __repr__(self) -> str:
        return f"<rblxopencloud.Resources \
experiences={self.experiences} accounts={self.accounts}>"

class PartialAccessToken():
    """
    Represents an access token via OAuth2 consent without all information. It \
    allows access to all resources authorized by the user, but not other \
    information like the refresh token.
    """

    def __init__(self, app, access_token) -> None:
        self.app: OAuth2App = app
        self.token: str = access_token
    
    def __repr__(self) -> str:
        return f"<rblxopencloud.PartialAccessToken \
    token=\"{self.token[:15]}...\">"

    def fetch_userinfo(self) -> User:
        """
        Returns a [`User`][rblxopencloud.User] object for this authorization. \
        This object can be used to directly access granted user resources \
        (such as like uploading files).
        """

        status, data, _ = send_request("GET", "oauth/v1/userinfo",
            authorization=f"Bearer {self.token}", expected_status=[200, 401])

        if status == 401:
            if data["error"] == "insufficient_scope":
                raise InsufficientScope(
                    data["scope"],
                    f"Access token missing required scope:'{data['scope']}'"
                )
            raise InvalidKey("The key has expired, been revoked or is invalid")
        
        user = User(data.get("id") or data.get("sub"), f"Bearer {self.token}")
        user.username = data.get("preferred_username")
        user.display_name = data.get("nickname")
        user.headshot_uri = data.get("picture")
        user.created_at = (
            datetime.datetime.fromtimestamp(data["created_at"])
            if data.get("created_at") else None
        )

        return user
            
    def fetch_resources(self) -> Resources:
        """
        Fetches the authorized accounts (users and groups) and experiences.
        """

        status, data, _ = send_request("GET", "oauth/v1/token/resources",
            expected_status=[200, 401], data={
                "token": self.token,
                "client_id": self.app.id,
                "client_secret": self.app._OAuth2App__secret
            }
        )

        if status == 401:
            if data["error"] == "insufficient_scope":
                raise InsufficientScope(
                    data["scope"],
                    f"Access token missing required scope: '{data['scope']}'"
                )
            raise InvalidKey("The key has expired, been revoked or is invalid")

        experiences = []
        accounts = []
        
        api_key = f"Bearer {self.token}"

        for resource in data["resource_infos"]:
            owner = resource["owner"]
            if resource["resources"].get("universe"):
                for experience_id in resource["resources"]["universe"]["ids"]:
                    experience = Experience(experience_id, api_key)
                    if owner["type"] == "User":
                        experience.owner = User(owner["id"], api_key)
                    elif owner["type"] == "Group":
                        experience.owner = Group(owner["id"], api_key)
                    experiences.append(experience)

            if resource["resources"].get("creator"):
                for creator_id in resource["resources"]["creator"]["ids"]:
                    if creator_id == "U":
                        accounts.append(User(owner["id"], api_key))
                    elif creator_id.startswith("U"):
                        accounts.append(User(creator_id[1:], api_key))
                    elif creator_id.startswith("G"):
                        accounts.append(Group(creator_id[1:], api_key))

        return Resources(experiences=experiences, accounts=accounts)

    def fetch_token_info(self) -> AccessTokenInfo:
        """
        Fetches token information such as the user's id, the authorized \
        scope, and it's expiry time.
        """

        status, data, _ = send_request("GET", "oauth/v1/token/introspect",
            expected_status=[200, 401], data={
                "token": self.token,
                "client_id": self.app.id,
                "client_secret": self.app._OAuth2App__secret
            }
        )
        
        if status == 401:
            if data["error"] == "insufficient_scope":
                raise InsufficientScope(data["scope"],
                f"Access token missing required scope: '{data['scope']}")
            raise InvalidKey("The key has expired, been revoked or is invalid")
        
        return AccessTokenInfo(data)
    
    def revoke(self):
        self.app.revoke_token(self.token)

class AccessToken(PartialAccessToken):
    """
    Represents access via OAuth2 consent. It allows access to all resources \
    authorized by the user.
    """
    def __init__(self, app, payload, id_token) -> None:
        super().__init__(app, payload["access_token"])
        self.refresh_token: str = payload["refresh_token"]
        self.scope: list[str] = payload["scope"].split(" ")
        self.expires_at: datetime = (
            datetime.datetime.now() + datetime.timedelta(payload["expires_in"])
        )

        if id_token:
            self.user: Optional[User] = User(
                id_token.get("id") or id_token.get("sub"),
                f"Bearer {self.token}"
            )
            self.user.username = id_token.get("preferred_username")
            self.user.display_name = id_token.get("nickname")
            self.user.headshot_uri = id_token.get("picture")
            self.user.created_at = (
                datetime.datetime.fromtimestamp(id_token["created_at"])
                if id_token.get("created_at") else None
            )
        else: self.user: Optional[User] = None

    def __repr__(self) -> str:
        return f"<rblxopencloud.AccessToken token=\"{self.token[:15]}...\" \
user={self.user})"
    
    def revoke_refresh_token(self):
        """
        Shortcut to revoke the refresh token.
        """
        self.app.revoke_token(self.refresh_token)

class OAuth2App():
    """
    Represents an OAuth2 app. It is used to exchange codes, refresh tokens, \
    and access the API for authenticated users.

    Args:
        id (int): The app's client ID.
        secret (str): The app's client secret.
        redirect_uri (str): The redirect URI that is being used for \
        authorization. If you need to use multiple, you must make seperate \
        objects.
        openid_certs_cache_seconds (int): The number of seconds to cache the \
        OpenID certs. You can ignore this if you don't know what it does.

    Attributes:
        if (int): The app's client ID.
        secret (str): The app's client secret.
        redirect_uri (str): The redirect URI being used for authorization.
        openid_certs_cache_seconds (int): The number of seconds to cache the \
        OpenID certs.
    """

    def __init__(
            self, id: int, secret: str, redirect_uri: str,
            openid_certs_cache_seconds: int = 3600
        ):
        self.id: int = id
        self.redirect_uri: str = redirect_uri
        self.__secret: str = secret

        self.openid_certs_cache_seconds: int = openid_certs_cache_seconds
        self.__openid_certs_cache = None
        self.__openid_certs_cache_updated = None
    
    def __repr__(self) -> str:
        return f"<rblxopencloud.OAuth2App(id={self.id} \
redirect_uri=\"{self.redirect_uri}\")"

    def generate_code_verifier(self, length: Optional[int]=128):
        """
        Generates a code verifier which can be provided to \
        [`OAuth2App.generate_uri`][rblxopencloud.OAuth2App.generate_uri] and \
        [`OAuth2App.exchange_code`][rblxopencloud.OAuth2App.exchange_code] \
        to add extra security to the OAuth2 flow.

        If a code verifier is used, it must be provided to both methods and \
        should also be unique.
        
        Args:
            length (Optional[int]): How long the code verifier should be.
        """

        return ''.join(
            secrets.choice(f"{string.ascii_letters}{string.digits}-._~")
            for _ in range(length)
        )

    def generate_uri(
            self, scope: Union[str, list[str]], state: str=None,
            generate_code: bool=True, code_verifier: str=None
        ) -> str:
        """
        Creates an authorization uri with the client information prefilled.
        
        Args:
            scope: Union[str, list[str]] - A string, or list of strings specifying the scopes for authorization. For example `['openid', 'profile']`
            state: str - A string that will be returned on the otherside of authorization. It isn't required, but is recommend for security.
            generate_code: bool - Wether to generate a code on return. Defaults to `True`.
            code_verifier: Optional[str] - The code verifier generated using OAuth2App.generate_code_verifier()`
        """

        params = {
            "client_id": self.id,
            "scope": " ".join(scope) if type(scope) == list else scope,
            "state": state,
            "redirect_uri": self.redirect_uri,
            "response_type": "code" if generate_code else "none",
            "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).replace(b"=", b"").decode() if code_verifier else None,
            "code_challenge_method": "S256" if code_verifier else None
        }
        return f"https://apis.roblox.com/oauth/v1/authorize?{parse.urlencode({key: value for key, value in params.items() if value is not None})}"

    def from_access_token_string(self, access_token: str) -> PartialAccessToken:
        """
        Creates an `rblx-open-cloud.PartialAccessToken` from an access token string, fairly useless due to these tokens expiring after 15 minutes.

        It is also advised the refresh token instead of the access token, and refresh the token each time you need to access information instead of the access_token to improve security.
        ### Parameters
        access_token: str - The access token string.
        """

        return PartialAccessToken(self, access_token)

    def exchange_code(self, code: str, code_verifier: Optional[str]=None) -> AccessToken:
        """
        Creates an `rblx-open-cloud.AccessToken` from an authorization code returned from Roblox.
        ### Parameters
        code: str - The code from the authorization server.
        code_verifier: Optional[str] - the string for this OAuth2 flow generated by `OAuth2App.generate_code_verifier()`.
        """
        response = request_session.post("https://apis.roblox.com/oauth/v1/token", data={
            "client_id": self.id,
            "client_secret": self.__secret,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": code_verifier,
            "code": code
        }, headers={"user-agent": user_agent})
        id_token = None
        if response.json().get("id_token"):
            if not self.__openid_certs_cache or time.time() - self.__openid_certs_cache_updated > self.openid_certs_cache_seconds:
                certs = request_session.get("https://apis.roblox.com/oauth/v1/certs", headers={"user-agent": user_agent})
                if not certs.ok: raise ServiceUnavailable("Failed to retrieve OpenID certs.")

                self.__openid_certs_cache = []
                for cert in certs.json()["keys"]:
                    self.__openid_certs_cache.append(load_der_public_key(ec.EllipticCurvePublicNumbers(
                        int.from_bytes(base64.urlsafe_b64decode(cert['x'] + '=='), 'big'),
                        int.from_bytes(base64.urlsafe_b64decode(cert['y'] + '=='), 'big'),
                        ec.SECP256R1()
                    ).public_key(default_backend()).public_bytes(
                        Encoding.DER,
                        PublicFormat.SubjectPublicKeyInfo
                    ), default_backend()))
                self.__openid_certs_cache_updated = time.time()

            for cert in self.__openid_certs_cache:
                try:
                    id_token = jwt.decode(response.json()["id_token"], cert,  algorithms=['ES256'], audience=str(self.id))
                    break
                except(AttributeError): raise rblx_opencloudException("jwt conflicts with PyJWT. Please uninstall jwt to fix this issue.")
                except(jwt.exceptions.PyJWTError): pass

        if response.ok: return AccessToken(self, response.json(), id_token)
        elif response.status_code == 400: raise InvalidKey(response.json().get("error_description", "The client id, client secret, or redirect uri is invalid."))
        elif response.status_code == 401: raise InvalidCode(response.json().get("error_description", "The code is invalid, or has been used."))
        elif response.status_code >= 500: raise ServiceUnavailable("The service is unavailable or has encountered an error.")
        else: raise rblx_opencloudException(f"Unexpected HTTP {response.status_code}")

    def refresh_token(self, refresh_token: str) -> AccessToken:
        """
        Creates an `rblx-open-cloud.AccessToken` from a refresh token. The new access token will have a different refresh token, and you must store the new refresh token.
        ### Parameters
        refresh_token: str - The refresh token to refresh.
        """
        response = request_session.post("https://apis.roblox.com/oauth/v1/token", data={
            "client_id": self.id,
            "client_secret": self.__secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        }, headers={"user-agent": user_agent})
        if response.ok: return AccessToken(self, response.json(), None)
        elif response.status_code == 400: raise InvalidKey(response.json().get("error_description", "The code, client id, client secret, or redirect uri is invalid."))
        elif response.status_code >= 500: raise ServiceUnavailable("The service is unavailable or has encountered an error.")
        else: raise rblx_opencloudException(f"Unexpected HTTP {response.status_code}")
    
    def revoke_token(self, token: str):
        """
        Revokes the authorization for a given access token or refresh token string.

        token: str - The refresh token to refresh.
        """
        response = request_session.post("https://apis.roblox.com/oauth/v1/token/revoke", data={
            "token": token,
            "client_id": self.id,
            "client_secret": self.__secret
        }, headers={"user-agent": user_agent})
        if response.ok: return
        elif response.status_code == 400: raise InvalidKey("The code, client id, client secret, or redirect uri is invalid.")
        elif response.status_code >= 500: raise ServiceUnavailable("The service is unavailable or has encountered an error.")
        else: raise rblx_opencloudException(f"Unexpected HTTP {response.status_code}")
