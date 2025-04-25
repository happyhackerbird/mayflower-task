# Import the specific crud modules to make them available
# under the 'app.crud' namespace when 'from app import crud' is used.
from . import address
from . import poem

# Optionally, you could expose specific functions directly:
# from .address import create_address, get_address, ...
# from .poem import create_poem, get_poem_by_location_key, ...
