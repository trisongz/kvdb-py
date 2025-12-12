try:
    import lzo.debugging
    print(f"lzo.debugging: {dir(lzo.debugging)}")
except ImportError:
    print("lzo.debugging failed")

try:
    import lzl.debug
    print(f"lzl.debug: {dir(lzl.debug)}")
except ImportError:
    print("lzl.debug failed")

try:
    from lzo.utils.debugging import inspect_serializability
    print("lzo.utils.debugging.inspect_serializability imported")
except ImportError:
    print("lzo.utils.debugging.inspect_serializability failed")
