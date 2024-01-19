import typing

from redis.backoff import (
    AbstractBackoff,
    ConstantBackoff,
    ExponentialBackoff,
    FullJitterBackoff,
    NoBackoff,
    EqualJitterBackoff,
    DecorrelatedJitterBackoff,
)

def default_backoff() -> typing.Type[AbstractBackoff]:
    """
    Return the default backoff class
    """
    return EqualJitterBackoff()
