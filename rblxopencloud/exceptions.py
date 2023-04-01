from typing import Union, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .datastore import EntryInfo

__all__ = (
    "rblx_opencloudException",
    "NotFound",
    "InvalidKey",
    "RateLimited",
    "ServiceUnavailable",
    "PreconditionFailed",
    "InvalidAsset",
)

class rblx_opencloudException(Exception): pass
class NotFound(rblx_opencloudException): pass
class InvalidKey(rblx_opencloudException): pass
class RateLimited(rblx_opencloudException): pass
class ServiceUnavailable(rblx_opencloudException): pass
class PreconditionFailed(rblx_opencloudException):
    def __init__(self, value, info, *args: object) -> None:
        self.value: Optional[Union[str, dict, list, int, float]] = value
        self.info: Optional[EntryInfo] = info
        super().__init__(*args)
class InvalidAsset(rblx_opencloudException): pass
class ModeratedText(rblx_opencloudException): pass
