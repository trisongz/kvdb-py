

from kvdb.utils.retry import get_retryable_wrapper
# from kvdb.utils.helpers import lazy_function_wrapper
from lzl.load import lazy_function_wrapper
from kvdb.errors import ConnectionError

def get_pubsub_wrapper(enabled: bool = True):
    """
    Gets the PubSub Wrapper
    """
    print(f'GETTING PUBSUB WRAPPER: Enabled {enabled}')
    return get_retryable_wrapper(enabled=enabled)


retryable = lazy_function_wrapper(get_pubsub_wrapper)
fake_retryable = lazy_function_wrapper(get_pubsub_wrapper, enabled = False)

@retryable
def test_1():
    raise ConnectionError('test_1', fatal = True)


@fake_retryable
def test_2():
    raise ConnectionError('test_2', fatal = True)



# test_1()
test_2()

from kvdb.components.session import KVDBSession
x = KVDBSession()

x.set()