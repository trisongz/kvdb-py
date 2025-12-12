try:
    from lzo.utils.helpers import update_dict
    print("lzo.utils.helpers.update_dict imported")
except ImportError as e:
    print(f"lzo.utils.helpers.update_dict failed: {e}")

try:
    from lzl.utils.helpers import update_dict
    print("lzl.utils.helpers.update_dict imported")
except ImportError as e:
    print(f"lzl.utils.helpers.update_dict failed: {e}")

try:
    from lzl.types import BaseSettings as AppSettings
    print("lzl.types.BaseSettings imported")
except ImportError as e:
    print(f"lzl.types.BaseSettings failed: {e}")

try:
    from lzo.types import AppSettings
    print("lzo.types.AppSettings imported")
except ImportError as e:
    print(f"lzo.types.AppSettings failed: {e}")
