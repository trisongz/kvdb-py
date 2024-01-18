

from kvdb.utils.retry import get_retryable_wrapper
from kvdb.utils.helpers import lazy_function_wrapper
from kvdb.errors import ConnectionError

def get_pubsub_wrapper():
    """
    Gets the PubSub Wrapper
    """
    print('GETTING PUBSUB WRAPPER')
    return get_retryable_wrapper()


retryable = lazy_function_wrapper(get_pubsub_wrapper)

@retryable
def test_1():
    raise ConnectionError('test_1')


test_1()