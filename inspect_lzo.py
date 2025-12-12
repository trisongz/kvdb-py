import lzo.utils
import lzl
import inspect

print("lzo.utils attributes:", dir(lzo.utils))

try:
    import lzo.utils.timer
    print("lzo.utils.timer imported")
except ImportError:
    pass

try:
    from lzo.utils import Timer
    print("lzo.utils.Timer imported")
except ImportError:
    pass

try:
    from lzl.utils import Timer
    print("lzl.utils.Timer imported")
except ImportError:
    pass

try:
    from lzo.utils import inspect_serializability
    print("lzo.utils.inspect_serializability imported")
except ImportError:
    pass
