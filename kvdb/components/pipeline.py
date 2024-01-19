from __future__ import annotations

import typing
import datetime
from redis.client import Pipeline
from redis.asyncio.client import Pipeline as AsyncPipeline
from kvdb.utils.retry import get_retry
from typing import Union, Callable, Literal, Any, Iterable, Mapping, overload, TYPE_CHECKING

if TYPE_CHECKING:
    from kvdb.types.generic import (
        _Key,
        _Value,
        _StrType
    )

retryable = get_retry('pipeline')


class RetryablePipeline(Pipeline):
    """
    Retryable Pipeline
    """

    @retryable
    def execute(self, raise_on_error: bool = True) -> typing.List[typing.Any]:
        """
        Execute all the commands in the current pipeline
        """
        return super().execute(raise_on_error = raise_on_error)


class AsyncRetryablePipeline(AsyncPipeline):
    """
    Retryable Pipeline
    """

    @retryable
    async def execute(self, raise_on_error: bool = True):
        """Execute all the commands in the current pipeline"""
        return await super().execute(raise_on_error = raise_on_error)
    
    if typing.TYPE_CHECKING:
        # This is only for type checking purposes, and will be removed in the future.
        def exists(self, *names: _Key) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def expire(  # type: ignore[override]
            self, name: _Key, time: int | datetime.timedelta, nx: bool = False, xx: bool = False, gt: bool = False, lt: bool = False
        ) -> 'AsyncRetryablePipeline': ...
        def expireat(self, name, when, nx: bool = False, xx: bool = False, gt: bool = False, lt: bool = False) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def get(self, name: _Key) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def getdel(self, name: _Key) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def getex(  # type: ignore[override]
            self,
            name,
            ex: Any | None = None,
            px: Any | None = None,
            exat: Any | None = None,
            pxat: Any | None = None,
            persist: bool = False,
        ) -> 'AsyncRetryablePipeline': ...
        def set(  # type: ignore[override]
            self,
            name: _Key,
            value: _Value,
            ex: None | int | datetime.timedelta = None,
            px: None | int | datetime.timedelta = None,
            nx: bool = False,
            xx: bool = False,
            keepttl: bool = False,
            get: bool = False,
            exat: Any | None = None,
            pxat: Any | None = None,
        ) -> 'AsyncRetryablePipeline': ...
        def setbit(self, name: _Key, offset: int, value: int) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def setex(self, name: _Key, time: int | datetime.timedelta, value: _Value) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def setnx(self, name: _Key, value: _Value) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def setrange(self, name, offset, value) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def stralgo(  # type: ignore[override]
            self,
            algo,
            value1,
            value2,
            specific_argument: str = "strings",
            len: bool = False,
            idx: bool = False,
            minmatchlen: Any | None = None,
            withmatchlen: bool = False,
            **kwargs: Any,
        ) -> 'AsyncRetryablePipeline': ...
        def strlen(self, name) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def substr(self, name, start, end: int = -1) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def touch(self, *args) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def ttl(self, name: _Key) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        @overload
        def blpop(self, keys: _Value | Iterable[_Value], timeout: Literal[0] | None = 0) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        @overload
        def blpop(self, keys: _Value | Iterable[_Value], timeout: float) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        @overload
        def brpop(self, keys: _Value | Iterable[_Value], timeout: Literal[0] | None = 0) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        @overload
        def brpop(self, keys: _Value | Iterable[_Value], timeout: float) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def brpoplpush(self, src, dst, timeout: int | None = 0) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def lindex(self, name: _Key, index: int) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def linsert(  # type: ignore[override]
            self, name: _Key, where: Literal["BEFORE", "AFTER", "before", "after"], refvalue: _Value, value: _Value
        ) -> 'AsyncRetryablePipeline': ...
        def llen(self, name: _Key) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def lpop(self, name, count: int | None = None) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def lpush(self, name: _Value, *values: _Value) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def lpushx(self, name, value) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def lrange(self, name: _Key, start: int, end: int) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def lrem(self, name: _Key, count: int, value: _Value) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def lset(self, name: _Key, index: int, value: _Value) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def ltrim(self, name: _Key, start: int, end: int) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def rpop(self, name, count: int | None = None) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def rpoplpush(self, src, dst) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def rpush(self, name: _Value, *values: _Value) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def rpushx(self, name, value) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def hmget(self, name: _Key, keys: _Value | Iterable[_Value]) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def hmset(self, name: _Key, mapping: Mapping[_Key, _Value]) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def hset(self, name: _Key, key: _Key, value: _Value) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def hsetnx(self, name: _Key, key: _Key, value: _Value) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def hstrlen(self, name: _Key, key: _Key) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def hvals(self, name: _Key) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def hscan(self, name: _Key, cursor: int = 0, match: _Value | None = None, count: int | None = None) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def hdel(self, name: _Key, *keys: _Value) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def hget(self, name: _Key, key: _Key) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def hgetall(self, name: _Key) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def hexists(self, name: _Key, key: _Key) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def hincrby(self, name: _Key, key: _Key, amount: int) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def hincrbyfloat(self, name: _Key, key: _Key, amount: float) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def zadd(  # type: ignore[override]
        self,
        name: _Key,
        mapping: Mapping[_Key, _Value],
        nx: bool = False,
        xx: bool = False,
        ch: bool = False,
        incr: bool = False,
        gt: Any | None = False,
        lt: Any | None = False,
        ) -> 'AsyncRetryablePipeline': ...
        def zcard(self, name: _Key) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def zcount(self, name: _Key, min: _Value, max: _Value) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def zdiff(self, keys, withscores: bool = False) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def zdiffstore(self, dest, keys) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def zincrby(self, name: _Key, amount: float, value: _Value) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def zinter(self, keys, aggregate: Any | None = None, withscores: bool = False) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def zinterstore(self, dest: _Key, keys: Iterable[_Key], aggregate: Literal["SUM", "MIN", "MAX"] | None = None) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def zlexcount(self, name: _Key, min: _Value, max: _Value) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def zpopmax(self, name: _Key, count: int | None = None) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def zpopmin(self, name: _Key, count: int | None = None) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def zrandmember(self, key, count: Any | None = None, withscores: bool = False) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        @overload  # type: ignore[override]
        def bzpopmax(self, keys: _Key | Iterable[_Key], timeout: Literal[0] = 0) -> 'AsyncRetryablePipeline': ...
        @overload  # type: ignore[override]
        def bzpopmax(self, keys: _Key | Iterable[_Key], timeout: float) -> 'AsyncRetryablePipeline': ...
        @overload  # type: ignore[override]
        def bzpopmin(self, keys: _Key | Iterable[_Key], timeout: Literal[0] = 0) -> 'AsyncRetryablePipeline': ...
        @overload  # type: ignore[override]
        def bzpopmin(self, keys: _Key | Iterable[_Key], timeout: float) -> 'AsyncRetryablePipeline': ...
        @overload  # type: ignore[override]
        def zrange(
            self,
            name: _Key,
            start: int,
            end: int,
            desc: bool,
            withscores: Literal[True],
            score_cast_func: Callable[[_StrType], Any],
            byscore: bool = False,
            bylex: bool = False,
            offset: int | None = None,
            num: int | None = None,
        ) -> 'AsyncRetryablePipeline': ...
        @overload  # type: ignore[override]
        def zrange(
            self,
            name: _Key,
            start: int,
            end: int,
            desc: bool,
            withscores: Literal[True],
            score_cast_func: Callable[[_StrType], float] = ...,
            byscore: bool = False,
            bylex: bool = False,
            offset: int | None = None,
            num: int | None = None,
        ) -> 'AsyncRetryablePipeline': ...
        @overload  # type: ignore[override]
        def zrange(
            self,
            name: _Key,
            start: int,
            end: int,
            *,
            withscores: Literal[True],
            score_cast_func: Callable[[_StrType], None],
            byscore: bool = False,
            bylex: bool = False,
            offset: int | None = None,
            num: int | None = None,
        ) -> 'AsyncRetryablePipeline': ...
        @overload  # type: ignore[override]
        def zrange(
            self,
            name: _Key,
            start: int,
            end: int,
            *,
            withscores: Literal[True],
            score_cast_func: Callable[[_StrType], float] = ...,
            byscore: bool = False,
            bylex: bool = False,
            offset: int | None = None,
            num: int | None = None,
        ) -> 'AsyncRetryablePipeline': ...
        @overload  # type: ignore[override]
        def zrange(
            self,
            name: _Key,
            start: int,
            end: int,
            desc: bool = False,
            withscores: bool = False,
            score_cast_func: Callable[[_StrType], Any] = ...,
            byscore: bool = False,
            bylex: bool = False,
            offset: int | None = None,
            num: int | None = None,
        ) -> 'AsyncRetryablePipeline': ...
        @overload  # type: ignore[override]
        def zrevrange(
            self, name: _Key, start: int, end: int, withscores: Literal[True], score_cast_func: Callable[[_StrType], None]
        ) -> 'AsyncRetryablePipeline': ...
        @overload  # type: ignore[override]
        def zrevrange(self, name: _Key, start: int, end: int, withscores: Literal[True]) -> 'AsyncRetryablePipeline': ...
        @overload  # type: ignore[override]
        def zrevrange(
            self, name: _Key, start: int, end: int, withscores: bool = False, score_cast_func: Callable[[Any], Any] = ...
        ) -> 'AsyncRetryablePipeline': ...
        def zrangestore(  # type: ignore[override]
            self,
            dest,
            name,
            start,
            end,
            byscore: bool = False,
            bylex: bool = False,
            desc: bool = False,
            offset: Any | None = None,
            num: Any | None = None,
        ) -> 'AsyncRetryablePipeline': ...
        def zrangebylex(self, name: _Key, min: _Value, max: _Value, start: int | None = None, num: int | None = None) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def zrevrangebylex(self, name: _Key, max: _Value, min: _Value, start: int | None = None, num: int | None = None) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        @overload  # type: ignore[override]
        def zrangebyscore(
            self,
            name: _Key,
            min: _Value,
            max: _Value,
            start: int | None = None,
            num: int | None = None,
            *,
            withscores: Literal[True],
            score_cast_func: Callable[[_StrType], None],
        ) -> 'AsyncRetryablePipeline': ...
        @overload  # type: ignore[override]
        def zrangebyscore(
            self, name: _Key, min: _Value, max: _Value, start: int | None = None, num: int | None = None, *, withscores: Literal[True]
        ) -> 'AsyncRetryablePipeline': ...
        @overload  # type: ignore[override]
        def zrangebyscore(
            self,
            name: _Key,
            min: _Value,
            max: _Value,
            start: int | None = None,
            num: int | None = None,
            withscores: bool = False,
            score_cast_func: Callable[[_StrType], Any] = ...,
        ) -> 'AsyncRetryablePipeline': ...
        @overload  # type: ignore[override]
        def zrevrangebyscore(
            self,
            name: _Key,
            max: _Value,
            min: _Value,
            start: int | None = None,
            num: int | None = None,
            *,
            withscores: Literal[True],
            score_cast_func: Callable[[_StrType], Any],
        ) -> 'AsyncRetryablePipeline': ...
        @overload  # type: ignore[override]
        def zrevrangebyscore(
            self, name: _Key, max: _Value, min: _Value, start: int | None = None, num: int | None = None, *, withscores: Literal[True]
        ) -> 'AsyncRetryablePipeline': ...
        @overload  # type: ignore[override]
        def zrevrangebyscore(
            self,
            name: _Key,
            max: _Value,
            min: _Value,
            start: int | None = None,
            num: int | None = None,
            withscores: bool = False,
            score_cast_func: Callable[[_StrType], Any] = ...,
        ) -> 'AsyncRetryablePipeline': ...
        def zrank(self, name: _Key, value: _Value) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def zrem(self, name: _Key, *values: _Value) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def zremrangebylex(self, name: _Key, min: _Value, max: _Value) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def zremrangebyrank(self, name: _Key, min: int, max: int) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def zremrangebyscore(self, name: _Key, min: _Value, max: _Value) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def zrevrank(self, name: _Key, value: _Value, withscore: bool = False) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def zscore(self, name: _Key, value: _Value) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def zunion(self, keys, aggregate: Any | None = None, withscores: bool = False) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def zunionstore(self, dest: _Key, keys: Iterable[_Key], aggregate: Literal["SUM", "MIN", "MAX"] | None = None) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]
        def zmscore(self, key, members) -> 'AsyncRetryablePipeline': ...  # type: ignore[override]

PipelineT = Union[Pipeline, RetryablePipeline]
AsyncPipelineT = Union[AsyncPipeline, AsyncRetryablePipeline]