from .experience import *
from .datastore import *
from .exceptions import *
from .user import *
from .group import *
from .creator import *

from typing import Literal

VERSION: str = "1.3.0"
VERSION_INFO: Literal['alpha', 'beta', 'final'] = "beta"

del Literal
