"""
Patch of the hiredis parser
"""

import anyio
import asyncio
from kvdb.utils.logs import logger
from redis._parsers.hiredis import (
    _AsyncHiredisParser as _BaseAsyncHiredisParser,
    SERVER_CLOSED_CONNECTION_ERROR,
    HIREDIS_AVAILABLE,
    async_timeout,
)


class _AsyncHiredisParser(_BaseAsyncHiredisParser):
    """
    Patch of the hiredis parser
    """

    async def can_read_destructive(self):
        if not self._connected:
            raise ConnectionError(SERVER_CLOSED_CONNECTION_ERROR)
        if self._reader.gets():
            return True
        try:
            with anyio.fail_after(0):
                return await self.read_from_socket()
        except TimeoutError:
            return False
        except Exception as e:
            logger.error(f"Error in can_read_destructive: {e}")
            return False

        # try:
        #     async with async_timeout(0):
        #         return await self.read_from_socket()
        # except asyncio.TimeoutError:
        #     return False