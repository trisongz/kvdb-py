from __future__ import annotations

import typing
from redis.client import PubSub
from redis.asyncio.client import PubSub as AsyncPubSub
from kvdb.utils.retry import get_retry
from typing import Union,TYPE_CHECKING

if TYPE_CHECKING:
    from redis.typing import ChannelT


retryable = get_retry('pubsub')

class RetryablePubSub(PubSub):
    """
    Retryable PubSub
    """

    @retryable
    def subscribe(self, *args: 'ChannelT', **kwargs: typing.Callable):
        """
        Subscribe to channels. Channels supplied as keyword arguments expect
        a channel name as the key and a callable as the value. A channel's
        callable will be invoked automatically when a message is received on
        that channel rather than producing a message via ``listen()`` or
        ``get_message()``.
        """
        return super().subscribe(*args, **kwargs)
    
    @retryable
    def unsubscribe(self, *args):
        """
        Unsubscribe from the supplied channels. If empty, unsubscribe from
        all channels
        """
        return super().unsubscribe(*args)

    @retryable
    def listen(self) -> typing.Iterator:
        """Listen for messages on channels this client has been subscribed to"""
        yield from super().listen()


class AsyncRetryablePubSub(AsyncPubSub):
    """
    Retryable PubSub
    """

    @retryable
    async def subscribe(self, *args: 'ChannelT', **kwargs: typing.Callable):
        """
        Subscribe to channels. Channels supplied as keyword arguments expect
        a channel name as the key and a callable as the value. A channel's
        callable will be invoked automatically when a message is received on
        that channel rather than producing a message via ``listen()`` or
        ``get_message()``.
        """
        return await super().subscribe(*args, **kwargs)
    
    @retryable
    def unsubscribe(self, *args) -> typing.Awaitable:
        """
        Unsubscribe from the supplied channels. If empty, unsubscribe from
        all channels
        """
        return super().unsubscribe(*args)

    @retryable
    async def listen(self) -> typing.AsyncIterator:
        """Listen for messages on channels this client has been subscribed to"""
        async for response in super().listen():
            yield response


PubSubT = Union[PubSub, RetryablePubSub]
AsyncPubSubT = Union[AsyncPubSub, AsyncRetryablePubSub]

