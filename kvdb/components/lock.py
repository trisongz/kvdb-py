from __future__ import annotations

from redis.lock import (
    Lock as _Lock,
    LockError, 
    LockNotOwnedError
)
from redis.asyncio.lock import (
    Lock as _AsyncLock,
)
from kvdb.configs import settings

import kvdb.errors as errors
from typing import Optional, Union, Awaitable, TYPE_CHECKING

if TYPE_CHECKING:
    from .client import KVDB, AsyncKVDB
    from .cluster import AsyncKVDBCluster


class Lock(_Lock):

    if TYPE_CHECKING:
        redis: KVDB
    
    def __init__(
        self,
        db: "KVDB",
        name: str,
        timeout: Optional[float] = None,
        sleep: float = 0.1,
        blocking: bool = True,
        blocking_timeout: Optional[float] = None,
        thread_local: bool = True,
        force_unlock: Optional[bool] = None,
        **kwargs,
    ):
        """
        Create a new Lock instance named ``name`` using the Redis client
        supplied by ``redis``.

        ``timeout`` indicates a maximum life for the lock in seconds.
        By default, it will remain locked until release() is called.
        ``timeout`` can be specified as a float or integer, both representing
        the number of seconds to wait.

        ``sleep`` indicates the amount of time to sleep in seconds per loop
        iteration when the lock is in blocking mode and another client is
        currently holding the lock.

        ``blocking`` indicates whether calling ``acquire`` should block until
        the lock has been acquired or to fail immediately, causing ``acquire``
        to return False and the lock not being acquired. Defaults to True.
        Note this value can be overridden by passing a ``blocking``
        argument to ``acquire``.

        ``blocking_timeout`` indicates the maximum amount of time in seconds to
        spend trying to acquire the lock. A value of ``None`` indicates
        continue trying forever. ``blocking_timeout`` can be specified as a
        float or integer, both representing the number of seconds to wait.

        ``thread_local`` indicates whether the lock token is placed in
        thread-local storage. By default, the token is placed in thread local
        storage so that a thread only sees its token, not a token set by
        another thread. Consider the following timeline:

            time: 0, thread-1 acquires `my-lock`, with a timeout of 5 seconds.
                     thread-1 sets the token to "abc"
            time: 1, thread-2 blocks trying to acquire `my-lock` using the
                     Lock instance.
            time: 5, thread-1 has not yet completed. redis expires the lock
                     key.
            time: 5, thread-2 acquired `my-lock` now that it's available.
                     thread-2 sets the token to "xyz"
            time: 6, thread-1 finishes its work and calls release(). if the
                     token is *not* stored in thread local storage, then
                     thread-1 would see the token value as "xyz" and would be
                     able to successfully release the thread-2's lock.

        In some use cases it's necessary to disable thread local storage. For
        example, if you have code where one thread acquires a lock and passes
        that lock instance to a worker thread to release later. If thread
        local storage isn't disabled in this case, the worker thread won't see
        the token set by the thread that acquired the lock. Our assumption
        is that these cases aren't common and as such default to using
        thread local storage.
        """
        self._force_unlock = force_unlock
        super().__init__(
            db,
            name,
            timeout = timeout,
            sleep = sleep,
            blocking = blocking,
            blocking_timeout = blocking_timeout,
            thread_local = thread_local,
            **kwargs,
        )

    @property
    def db(self) -> "KVDB":
        """
        Returns the db instance
        """
        return self.redis
    
    def release(
        self,
        force: Optional[bool] = None,
        raise_errors: Optional[bool] = True,
    ):
        """
        Release the lock if we currently own it.

        ``force`` indicates whether to force release the lock even if it's
        expired or we don't currently own it. Defaults to False.

        ``raise_errors`` indicates whether to raise any errors that occur
        during the release process. Defaults to True.
        """
        if force is None: force = self._force_unlock
        try:
            return super().release()
        except (LockNotOwnedError, LockError) as e:
            if force:
                settings.autologger.warning(f"Force releasing lock {self.name}: {e}")
                self.redis.delete(self.name)
                return True
            if raise_errors: raise errors.transpose_error(e, msg = f"Failed to release lock {self.name}") from e
        

class AsyncLock(_AsyncLock):

    if TYPE_CHECKING:
        redis: AsyncKVDB

    def __init__(
        self,
        db: Union["AsyncKVDB", "AsyncKVDBCluster"],
        name: Union[str, bytes, memoryview],
        timeout: Optional[float] = None,
        sleep: float = 0.1,
        blocking: bool = True,
        blocking_timeout: Optional[float] = None,
        thread_local: bool = True,
        force_unlock: Optional[bool] = None,
        **kwargs,
    ):
        """
        Create a new Lock instance named ``name`` using the Redis client
        supplied by ``redis``.

        ``timeout`` indicates a maximum life for the lock in seconds.
        By default, it will remain locked until release() is called.
        ``timeout`` can be specified as a float or integer, both representing
        the number of seconds to wait.

        ``sleep`` indicates the amount of time to sleep in seconds per loop
        iteration when the lock is in blocking mode and another client is
        currently holding the lock.

        ``blocking`` indicates whether calling ``acquire`` should block until
        the lock has been acquired or to fail immediately, causing ``acquire``
        to return False and the lock not being acquired. Defaults to True.
        Note this value can be overridden by passing a ``blocking``
        argument to ``acquire``.

        ``blocking_timeout`` indicates the maximum amount of time in seconds to
        spend trying to acquire the lock. A value of ``None`` indicates
        continue trying forever. ``blocking_timeout`` can be specified as a
        float or integer, both representing the number of seconds to wait.

        ``thread_local`` indicates whether the lock token is placed in
        thread-local storage. By default, the token is placed in thread local
        storage so that a thread only sees its token, not a token set by
        another thread. Consider the following timeline:

            time: 0, thread-1 acquires `my-lock`, with a timeout of 5 seconds.
                     thread-1 sets the token to "abc"
            time: 1, thread-2 blocks trying to acquire `my-lock` using the
                     Lock instance.
            time: 5, thread-1 has not yet completed. redis expires the lock
                     key.
            time: 5, thread-2 acquired `my-lock` now that it's available.
                     thread-2 sets the token to "xyz"
            time: 6, thread-1 finishes its work and calls release(). if the
                     token is *not* stored in thread local storage, then
                     thread-1 would see the token value as "xyz" and would be
                     able to successfully release the thread-2's lock.

        In some use cases it's necessary to disable thread local storage. For
        example, if you have code where one thread acquires a lock and passes
        that lock instance to a worker thread to release later. If thread
        local storage isn't disabled in this case, the worker thread won't see
        the token set by the thread that acquired the lock. Our assumption
        is that these cases aren't common and as such default to using
        thread local storage.
        """
        self._force_unlock = force_unlock
        super().__init__(
            db,
            name,
            timeout = timeout,
            sleep = sleep,
            blocking = blocking,
            blocking_timeout = blocking_timeout,
            thread_local = thread_local,
            **kwargs,
        )


    @property
    def db(self) -> "AsyncKVDB":
        """
        Returns the db instance
        """
        return self.redis
    

    async def do_release(
        self, 
        expected_token: bytes,
        force: Optional[bool] = None,
        raise_errors: Optional[bool] = True,
    ) -> None:
        """
        This is a copy of the original do_release method, but with the
        ability to force release the lock even if it's expired or we don't
        currently own it.
        """
        if force is None: force = self._force_unlock
        if not bool(
            await self.lua_release(
                keys=[self.name], args=[expected_token], client=self.redis
            )
        ):
            if raise_errors and not force:
                raise errors.LockNotOwnedError("Cannot release a lock that's no longer owned")
            if force:
                settings.autologger.warning(f"Force releasing lock {self.name}")
                await self.redis.delete(self.name)
                return True


    def release(
        self,
        force: Optional[bool] = None,
        raise_errors: Optional[bool] = True,
    ) -> Awaitable[None]:
        """
        Release the lock if we currently own it.

        ``force`` indicates whether to force release the lock even if it's
        expired or we don't currently own it. Defaults to False.

        ``raise_errors`` indicates whether to raise any errors that occur
        during the release process. Defaults to True.
        """
        expected_token = self.local.token
        if expected_token is None:
            if raise_errors: raise LockError("Cannot release an unlocked lock")
            return False
        self.local.token = None
        return self.do_release(expected_token, force = force, raise_errors = raise_errors)


LockT = Union[Lock, AsyncLock]