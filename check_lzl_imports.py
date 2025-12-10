try:
    from lzl.io import TemporaryData
    print("lzl.io.TemporaryData imported")
except ImportError as e:
    print(f"lzl.io.TemporaryData failed: {e}")

try:
    from lzl.io.persistence import TemporaryData
    print("lzl.io.persistence.TemporaryData imported")
except ImportError as e:
    print(f"lzl.io.persistence.TemporaryData failed: {e}")

try:
    from lzo.utils.system import is_in_kubernetes
    print("lzo.utils.system.is_in_kubernetes imported")
except ImportError as e:
    print(f"lzo.utils.system.is_in_kubernetes failed: {e}")
