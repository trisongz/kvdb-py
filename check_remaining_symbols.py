try:
    from lzl.io.persistence import PersistentDict
    print("lzl.io.persistence.PersistentDict imported")
except ImportError as e:
    print(f"lzl.io.persistence.PersistentDict failed: {e}")

try:
    from lzl.io.persistence.backends.base import BaseStatefulBackend, SchemaType
    print("lzl.io.persistence.backends.base imported")
except ImportError as e:
    print(f"lzl.io.persistence.backends.base failed: {e}")

try:
    from lzo.utils.times import Timer
    print("lzo.utils.times.Timer imported")
except ImportError as e:
    print(f"lzo.utils.times.Timer failed: {e}")

try:
    from lzo.utils.helpers import timed_cache
    print("lzo.utils.helpers.timed_cache imported")
except ImportError as e:
    print(f"lzo.utils.helpers.timed_cache failed: {e}")

try:
    from lzo.utils.debugging import inspect_serializability
    print("lzo.utils.debugging.inspect_serializability imported")
except ImportError as e:
    print(f"lzo.utils.debugging.inspect_serializability failed: {e}")

try:
    from lzl.load import lazy_function_wrapper
    print("lzl.load.lazy_function_wrapper imported")
except ImportError as e:
    print(f"lzl.load.lazy_function_wrapper failed: {e}")
