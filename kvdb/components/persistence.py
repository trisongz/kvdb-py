from __future__ import annotations

"""
A KVDB-backed Dict-like object
"""
import re
import time
import binascii
from kvdb.configs import settings as kvdb_settings
from kvdb.configs.base import SerializerConfig
from kvdb.utils.logs import logger
from kvdb.types.base import supported_schemas, KVDBUrl
try:
    from lzl.io.persistence.backends.base import BaseStatefulBackend, SchemaType
    from lzl.io.persistence import PersistentDict
except ImportError:
    from lazyops.libs.persistence.backends.base import BaseStatefulBackend, SchemaType
    from lazyops.libs.persistence import PersistentDict

from typing import Any, Dict, Optional, Union, Iterable, List, Type, Set, Callable, TYPE_CHECKING


if TYPE_CHECKING:
    from .session import KVDBSession
    from .lock import Lock, AsyncLock

    from lzl.types import BaseSettings
    from lzl.io.ser.base import ObjectValue

    # from lazyops.types.models import BaseSettings
    # from lazyops.libs.persistence.serializers.base import ObjectValue


class KVDBStatefulBackend(BaseStatefulBackend):
    """
    Implements Stateful Backend using KVDB
    """
    
    name: Optional[str] = "kvdb"

    # Default Global Level Settings that can then be tuned
    # at an instance level
    expiration: Optional[int] = None
    hset_disabled: Optional[bool] = False
    keyjoin: Optional[str] = ':'
    cache: Optional['KVDBSession'] = None

    def __init__(
        self,
        name: Optional[str] = None,
        expiration: Optional[int] = None,
        hset_disabled: Optional[bool] = False,
        keyjoin: Optional[str] = None,
        base_key: Optional[str] = None,
        async_enabled: Optional[bool] = False,
        settings: Optional['BaseSettings'] = None,
        url: Optional[Union[str, KVDBUrl]] = None,
        serializer: Optional[str] = None,
        serializer_kwargs: Optional[Dict[str, Any]] = None,
        session_serialization_enabled: Optional[bool] = None, # Defer serialization to the session
        session: Optional['KVDBSession'] = None,
        context_timeout: Optional[float] = 60.0,
        **kwargs,
    ):
        """
        Initializes the backend
        """
        if settings is None: settings = kvdb_settings
        self.base_key = base_key
        self.exp_index_key = f'_exp_:{self.base_key}'
        self.async_enabled = async_enabled
        self.settings = settings
        if name is not None: self.name = name
        if expiration is not None: self.expiration = expiration

        if session is not None:
            self.cache = session
            self.session_serialization_enabled = session.session_serialization_enabled
        else:
            self.session_serialization_enabled = session_serialization_enabled

        client_kwargs = {}
        # Defer serialization to the session
        if self.session_serialization_enabled:
            # Since we handle this within the session - we disable it here
            # Handle Serialization within the session
            self.serializer = None
            self.serializer_kwargs = None
            client_kwargs.update(kwargs)
            client_kwargs['serializer'] = serializer
            client_kwargs['serializer_kwargs'] = serializer_kwargs
            
        else:
            # Handle Serialization here
            _extra_serialization_kwargs = SerializerConfig.extract_kwargs(_exclude_none = True, **kwargs)
            self.serializer = kvdb_settings.client_config.get_serializer(
                serializer = serializer,
                serializer_kwargs = serializer_kwargs,
                **_extra_serialization_kwargs,
            )
            self.serializer_kwargs = serializer_kwargs
            client_kwargs = {k : v for k, v in kwargs.items() if k not in _extra_serialization_kwargs}
        
        # Initialize the Cache if not already initialized from the session
        if self.cache is None:
            from kvdb.client import KVDBClient
            self.cache = KVDBClient.session(
                name = self.name if self.name != 'kvdb' else 'persistence',
                url = url, **client_kwargs,
            )
        self._lock: Optional[Lock] = None
        self._alock: Optional[AsyncLock] = None
        self.context_timeout = context_timeout
        self.hset_enabled = (not hset_disabled and self.base_key is not None)
        if keyjoin is not None: self.keyjoin = keyjoin
        self._kwargs = kwargs
        self._kwargs['session_serialization_enabled'] = self.session_serialization_enabled
        self._kwargs['serializer'] = serializer
        self._kwargs['serializer_kwargs'] = serializer_kwargs
        self._kwargs['async_enabled'] = async_enabled
        self._kwargs['settings'] = settings
        self._kwargs['url'] = url
        self._kwargs['hset_disabled'] = hset_disabled
        self._kwargs['expiration'] = expiration
        self._kwargs['name'] = name
        self._kwargs['keyjoin'] = keyjoin
        self._kwargs['context_timeout'] = context_timeout
        if kvdb_settings.debug:
            logger.info(f'[{self.base_key}] Initialized KVDBStatefulBackend with {self._kwargs}')

    @classmethod
    def as_persistent_dict(
        cls,
        name: Optional[str] = None,
        expiration: Optional[int] = None,
        hset_disabled: Optional[bool] = False,
        keyjoin: Optional[str] = None,
        base_key: Optional[str] = None,
        async_enabled: Optional[bool] = False,
        settings: Optional['BaseSettings'] = None,
        url: Optional[Union[str, KVDBUrl]] = None,
        serializer: Optional[str] = None,
        serializer_kwargs: Optional[Dict[str, Any]] = None,
        session_serialization_enabled: Optional[bool] = None, # Defer serialization to the session
        session: Optional['KVDBSession'] = None,
        **kwargs,
    ) -> PersistentDict:
        """
        Creates a Persistent Dict from the Backend that 
        uses the KVDB Backend
        """
        return PersistentDict(
            name = name,
            serializer = serializer,
            serializer_kwargs = serializer_kwargs,
            base_key = base_key,
            backend_type = cls.name,
            backend = cls,
            async_enabled = async_enabled,
            settings = settings,
            url = url,
            expiration = expiration,
            hset_disabled = hset_disabled,
            keyjoin = keyjoin,
            session = session,
            session_serialization_enabled = session_serialization_enabled,
            **kwargs,
        )


    def encode_value(self, value: Union[Any, SchemaType], _raw: Optional[bool] = None, **kwargs) -> Union[str, bytes]:
        """
        Encodes a Value
        """
        if self.session_serialization_enabled or _raw: return value
        return self.serializer.encode(value, **kwargs) if self.serializer is not None else value
    
    async def aencode_value(self, value: Union[Any, SchemaType], _raw: Optional[bool] = None, **kwargs) -> Union[str, bytes]:
        """
        Encodes a Value
        """
        # logger.info(f'[{self.base_key}] Decoding Value: {value}')
        if self.session_serialization_enabled or _raw: return value
        return await self.serializer.aencode(value, **kwargs) if self.serializer is not None else value

    def decode_value(self, value: Union[str, bytes], _raw: Optional[bool] = None, **kwargs) -> Any:
        """
        Decodes a Value
        """
        # logger.info(f'[{self.base_key}] Decoding Value: {value}')
        # if self.session_serialization_enabled:
        #     return value
        if self.session_serialization_enabled or _raw: return value
        return self.serializer.decode(value, **kwargs) if self.serializer is not None else value
    
    async def adecode_value(self, value: Union[str, bytes], _raw: Optional[bool] = None, **kwargs) -> Any:
        """
        Decodes a Value
        """
        # logger.info(f'[{self.base_key}] Decoding Value: {value}')
        # if self.session_serialization_enabled:
        #     return value
        if self.session_serialization_enabled or _raw: return value
        return await self.serializer.adecode(value, **kwargs) if self.serializer is not None else value

    def get_key(self, key: str) -> str:
        """
        Gets a Key
        """
        if not self.base_key: return key
        return key if self.base_key in key else f'{self.base_key}{self.keyjoin}{key}'
    
    """
    Expiration Methods for HSET
    """

    def hset_expire(self, key: str, ex: int):
        """
        Sets the expiration for a key
        """
        if ex is None: return
        exp_time = int(time.time()) + ex
        self.cache.hset(self.exp_index_key, key, exp_time)

    def hset_expire_batch(self, keys: Union[Dict[str, Any], List[str]], ex: int):
        """
        Sets the expiration for a batch of keys
        """
        if ex is None: return
        if isinstance(keys, dict): keys = list(keys.keys())
        exp_time = int(time.time()) + ex
        data = {k: exp_time for k in keys}
        self.cache.hset(self.exp_index_key, mapping = data)

    async def ahset_expire(self, key: str, ex: int):
        """
        Sets the expiration for a key
        """
        if ex is None: return
        exp_time = int(time.time()) + ex
        await self.cache.ahset(self.exp_index_key, key, exp_time)

    async def ahset_expire_batch(self, keys: Union[Dict[str, Any], List[str]], ex: int):
        """
        Sets the expiration for a batch of keys
        """
        if ex is None: return
        if isinstance(keys, dict): keys = list(keys.keys())
        exp_time = int(time.time()) + ex
        data = {k: exp_time for k in keys}
        await self.cache.ahset(self.exp_index_key, mapping = data)

    def _run_expiration_check(self, keys: Optional[List[str]] = None):
        """
        [HSET] Runs the expiration check
        """
        if not keys: keys = self.cache.hkeys(self.exp_index_key)
        if not keys: return
        exp_times = self.cache.hmget(self.exp_index_key, keys)
        # exp_items = dict(zip(keys, exp_times))
        for key, exp_time in zip(keys, exp_times):
            if exp_time is None: continue
            if int(exp_time) < int(time.time()): 
                self.cache.hdel(self.exp_index_key, key)
                self.cache.hdel(self.base_key, key)
                # logger.info(f'Expired key `|g|{key}|e|` (TTL: {int(exp_time) - int(time.time())})', prefix = self.base_key, colored = True)
    
    async def _arun_expiration_check(self, keys: Optional[List[str]] = None):
        """
        [HSET] Runs the expiration check
        """
        if not keys: keys = await self.cache.ahkeys(self.exp_index_key)
        if not keys: return
        exp_times = await self.cache.ahmget(self.exp_index_key, keys)
        # exp_items = dict(zip(keys, exp_times))
        for key, exp_time in zip(keys, exp_times):
            if exp_time is None: continue
            if int(exp_time) < int(time.time()): 
                await self.cache.ahdel(self.exp_index_key, key)
                await self.cache.ahdel(self.base_key, key)
                # logger.info(f'Expired key `|g|{key}|e|` (TTL: {int(exp_time) - int(time.time())})', prefix = self.base_key, colored = True)

    def hset_expiration_check(self, key: str):
        """
        [HSET] Checks if the key has expired
        """
        if not self.cache.hexists(self.exp_index_key, key): return
        exp_time = self.cache.hget(self.exp_index_key, key)
        if exp_time is None:
            self.cache.hdel(self.exp_index_key, key)
            return
        if int(exp_time) < int(time.time()): 
            self.cache.hdel(self.exp_index_key, key)
            self.cache.hdel(self.base_key, key)
            # logger.info(f'Expired key `|g|{key}|e|` (TTL: {int(exp_time) - int(time.time())})', prefix = self.base_key, colored = True)

    async def ahset_expiration_check(self, key: str):
        """
        [HSET] Checks if the key has expired
        """
        if not await self.cache.ahexists(self.exp_index_key, key): return
        exp_time = await self.cache.ahget(self.exp_index_key, key)
        if exp_time is None:
            await self.cache.ahdel(self.exp_index_key, key)
            return
        if int(exp_time) < int(time.time()): 
            await self.cache.ahdel(self.exp_index_key, key)
            await self.cache.ahdel(self.base_key, key)
            # logger.info(f'Expired key `|g|{key}|e|` (TTL: {int(exp_time) - int(time.time())})', prefix = self.base_key, colored = True)
    
    def get(self, key: str, default: Optional[Any] = None, _raw: Optional[bool] = None, **kwargs) -> Optional[Any]:
        """
        Gets a Value from the DB
        """
        if self.hset_enabled: 
            self.hset_expiration_check(key)
            value = self.cache.hget(self.base_key, key)
        else: value = self.cache.client.get(self.get_key(key))
        if value is None: return default
        try:
            return self.decode_value(value, _raw = _raw, **kwargs)
        except Exception as e:
            logger.error(f'Error Getting Value for Key: {key} - {e}')
            self.delete(key)
            return default

    def get_values(self, keys: Iterable[str], _raw: Optional[bool] = None, **kwargs) -> List[Any]:
        """
        Gets a Value from the DB
        """
        if self.hset_enabled: 
            self._run_expiration_check(keys)
            values = self.cache.hmget(self.base_key, keys)
        else: values = self.cache.client.mget([self.get_key(key) for key in keys])
        results = []
        for key, value in zip(keys, values):
            try:
                results.append(self.decode_value(value, _raw = _raw, **kwargs))
            except Exception as e:
                logger.error(f'Error Getting Value for Key: {key} - {e}')
                self.delete(key)
                results.append(None)
        return results


    def set(self, key: str, value: Any, ex: Optional[int] = None, _raw: Optional[bool] = None, **kwargs) -> None:
        """
        Saves a Value to the DB
        """
        ex = ex or self.expiration
        if self.hset_enabled:
            self.cache.hset(self.base_key, key, self.encode_value(value, _raw = _raw, **kwargs))
            if ex is not None: self.hset_expire(key, ex)
            # if ex is not None: self.cache.expire(self.base_key, ex)
        else:
            self.cache.client.set(self.get_key(key), self.encode_value(value, _raw = _raw, **kwargs), ex = ex)
    
    def set_batch(self, data: Dict[str, Any], ex: Optional[int] = None, _raw: Optional[bool] = None, **kwargs) -> None:
        """
        Saves a Value to the DB
        """
        ex = ex or self.expiration
        data = {k: self.encode_value(v, _raw = _raw, **kwargs) for k, v in data.items()}
        if self.hset_enabled:
            self.cache.client.hset(self.base_key, mapping = data)
            if ex is not None: self.hset_expire_batch(data, ex)
            # if ex is not None: self.cache.expire(self.base_key, ex)
        else:
            if self.base_key: data = {self.get_key(k): v for k, v in data.items()}
            self.cache.client.mset(data)
            if ex is not None:
                for key in data:
                    self.cache.client.expire(key, ex)


    def delete(self, key: str, **kwargs) -> None:
        """
        Deletes a Value from the DB
        """
        if self.hset_enabled: 
            self.cache.hdel(self.base_key, key)
            self.cache.hdel(self.exp_index_key, key)
        else: self.cache.client.delete(self.get_key(key))

    def clear(self, *keys, **kwargs):
        """
        Clears the Cache
        """
        if self.hset_enabled:
            if keys: 
                self.cache.hdel(self.base_key, *keys)
                self.cache.hdel(self.exp_index_key, *keys)
            else: self.cache.delete(self.base_key)
        elif keys:
            keys = [self.get_key(key) for key in keys]
            self.cache.delete(*keys)
        else:
            keys = self.cache.client.keys(f'{self.base_key}{self.keyjoin}*')
            if keys: self.cache.client.delete(*keys)
    
    async def aget(self, key: str, default: Optional[Any] = None, _raw: Optional[bool] = None, **kwargs) -> Optional[Any]:
        """
        Gets a Value from the DB
        """
        if self.hset_enabled: 
            await self.ahset_expiration_check(key)
            value = await self.cache.ahget(self.base_key, key)
        else: value = await self.cache.aget(self.get_key(key))
        if value is None: return default
        try:
            return self.decode_value(value, _raw = _raw, **kwargs)
        except Exception as e:
            logger.error(f'Error Getting Value for Key: {key} - {e}')
            await self.adelete(key)
            return default

    async def aget_values(self, keys: Iterable[str], _raw: Optional[bool] = None, **kwargs) -> List[Any]:
        """
        Gets a Value from the DB
        """
        if self.hset_enabled: 
            await self._arun_expiration_check(keys)
            values = await self.cache.ahmget(self.base_key, keys)
        else: values = await self.cache.amget([self.get_key(key) for key in keys])
        results = []
        for key, value in zip(keys, values):
            try: results.append(self.decode_value(value, _raw = _raw, **kwargs))
            except Exception as e:
                logger.error(f'Error Getting Value for Key: {key} - {e}')
                await self.adelete(key)
                results.append(None)
        return results
        
    async def aset(self, key: str, value: Any, ex: Optional[int] = None, _raw: Optional[bool] = None, **kwargs) -> None:
        """
        Saves a Value to the DB
        """
        ex = ex or self.expiration
        if self.hset_enabled:
            await self.cache.ahset(self.base_key, key, self.encode_value(value, _raw = _raw, **kwargs))
            if ex is not None: await self.ahset_expire(key, ex)
            # if ex is not None: await self.cache.aexpire(self.base_key, ex)
        else:
            await self.cache.aset(self.get_key(key), self.encode_value(value, _raw = _raw, **kwargs), ex = ex)

    async def aset_batch(self, data: Dict[str, Any], ex: Optional[int] = None, _raw: Optional[bool] = None, **kwargs) -> None:
        """
        Saves a Value to the DB
        """
        ex = ex or self.expiration
        data = {k: self.encode_value(v, _raw = _raw, **kwargs) for k, v in data.items()}
        if self.hset_enabled:
            await self.cache.ahset(self.base_key, mapping = data)
            if ex is not None: await self.ahset_expire_batch(data, ex)
            # if ex is not None: await self.cache.aexpire(self.base_key, ex)
        else:
            if self.base_key: data = {self.get_key(k): v for k, v in data.items()}
            await self.cache.amset(data)
            if ex is not None:
                for key in data:
                    await self.cache.aexpire(key, ex)
    
    
    async def adelete(self, key: str, **kwargs) -> None:
        """
        Deletes a Value from the DB
        """
        if self.hset_enabled: 
            await self.cache.ahdel(self.base_key, key)
            await self.cache.ahdel(self.exp_index_key, key)
        else: await self.cache.adelete(self.get_key(key))

    async def aclear(self, *keys, **kwargs):
        """
        Clears the Cache
        """
        if self.hset_enabled:
            if keys: 
                await self.cache.ahdel(self.base_key, *keys)
                await self.cache.ahdel(self.exp_index_key, *keys)
            else: await self.cache.adelete(self.base_key)
        elif keys:
            keys = [self.get_key(key) for key in keys]
            await self.cache.adelete(*keys)

        else:
            keys = await self.cache.akeys(f'{self.base_key}{self.keyjoin}*')
            if keys: await self.cache.adelete(*keys)

    def iterate(self, **kwargs) -> Iterable[Any]:
        """
        Iterates over the Cache
        """
        if self.hset_enabled: 
            self._run_expiration_check()
            return iter(self.cache.hkeys(self.base_key))
        if not self.base_key:
            raise NotImplementedError('Cannot iterate over a Redis Cache without a base key')
        return iter(self.cache.client.keys(f'{self.base_key}{self.keyjoin}*'))
    
    def length(self, **kwargs) -> int:
        """
        Returns the Length of the Cache
        """
        if self.hset_enabled: 
            self._run_expiration_check()
            return self.cache.hlen(self.base_key)
        if not self.base_key:
            raise NotImplementedError('Cannot get the length of a Redis Cache without a base key')
        return len(self.cache.client.keys(f'{self.base_key}{self.keyjoin}*'))
    
    async def alength(self, **kwargs) -> int:
        """
        Returns the Length of the Cache
        """
        if self.hset_enabled: 
            await self._arun_expiration_check()
            return await self.cache.ahlen(self.base_key)
        if not self.base_key:
            raise NotImplementedError('Cannot get the length of a Redis Cache without a base key')
        return len(await self.cache.akeys(f'{self.base_key}{self.keyjoin}*'))
    
    def __len__(self):
        """
        Returns the Length of the Cache
        """
        return self.length()
    

    def get_all_data(self, exclude_base_key: Optional[bool] = False, _raw: Optional[bool] = None, **kwargs) -> Dict[str, Any]:
        """
        Loads all the Data
        """
        if not self.hset_enabled and not self.base_key:
            raise NotImplementedError('Cannot get all data from a KVDB Cache without a base key')
        if self.hset_enabled:
            self._run_expiration_check()
            data = self.cache.hgetall(self.base_key)
            results = {}
            for key, value in data.items():
                if isinstance(key, bytes): key = key.decode()
                try: results[key] = self.decode_value(value, _raw = _raw, **kwargs)
                except AttributeError:
                    logger.warning(f'Unable to decode value for {key}')
                    self.delete(key)
            return results
        
        keys = self._fetch_set_keys(decode = True)
        data_list = self.cache.client.mget(keys)
        results: Dict[str, Any] = {}
        for key, value in zip(keys, data_list):
            if isinstance(key, bytes): key = key.decode()
            try:
                results[key] = self.decode_value(value, _raw = _raw, **kwargs)
            except AttributeError:
                logger.warning(f'Unable to decode value for {key}')
                self.delete(key)
        if exclude_base_key:
            results = {k.replace(f'{self.base_key}{self.keyjoin}', ''): v for k, v in results.items()}
        return results
    
    def get_keys(self, pattern: str, exclude_base_key: Optional[str] = False, **kwargs) -> List[str]:
        """
        Returns the keys that match the pattern
        """
        # if not self.base_key:
        #     raise NotImplementedError('Cannot get keys from a Redis Cache without a base key')
        base_pattern = pattern if self.hset_enabled else f'{self.base_key}{pattern}'
        if self.hset_enabled: 
            self._run_expiration_check()
            keys = self._fetch_hset_keys(decode = True)
            keys = [key for key in keys if re.match(base_pattern, key)]
        else:
            keys: List[str] = self.cache.client.keys(base_pattern)
            keys = [k.decode() if isinstance(k, bytes) else k for k in keys]
        if exclude_base_key:
            keys = [key.replace(f'{self.base_key}{self.keyjoin}', '') for key in keys]
        return keys

    def get_all_keys(self, exclude_base_key: Optional[bool] = False, **kwargs) -> List[str]:
        """
        Returns all the Keys
        """
        if not self.base_key:
            raise NotImplementedError('Cannot get all keys from a KVDB Cache without a base key')
        if self.hset_enabled: 
            self._run_expiration_check()
            return self._fetch_hset_keys(decode = True)
        keys = self._fetch_set_keys(decode = True)
        if exclude_base_key:
            keys = [key.replace(f'{self.base_key}{self.keyjoin}', '') for key in keys]
        return keys
    
    def get_all_values(self, _raw: Optional[bool] = None, **kwargs) -> List[Any]:
        """
        Returns all the Values
        """
        if not self.base_key:
            raise NotImplementedError('Cannot get all values from a KVDB Cache without a base key')
        if self.hset_enabled:
            self._run_expiration_check()
            data = self.cache.hgetall(self.base_key)
            results = []
            for key, value in data.items():
                try:
                    results.append(self.decode_value(value, _raw = _raw, **kwargs))
                except Exception as e:
                    logger.warning(f'Unable to decode value for {key}: {e}')
                    self.delete(key)
            return results
        keys = self._fetch_set_keys(decode = False)
        data_list = self.cache.client.mget(keys)
        results = []
        for key, value in zip(keys, data_list):
            try:
                results.append(self.decode_value(value, _raw = _raw, **kwargs))
            except Exception as e:
                logger.warning(f'Unable to decode value for {key}: {e}')
                self.delete(key)
        return results

    async def aget_all_data(self, exclude_base_key: Optional[bool] = False, _raw: Optional[bool] = None, **kwargs) -> Dict[str, Any]:
        """
        Loads all the Data
        """
        if not self.base_key:
            raise NotImplementedError('Cannot get all data from a KVDB Cache without a base key')
        if self.hset_enabled:
            await self._arun_expiration_check()
            data = await self.cache.ahgetall(self.base_key)
            results = {}
            for key, value in data.items():
                if isinstance(key, bytes): key = key.decode()
                try:
                    results[key] = self.decode_value(value, _raw = _raw, **kwargs)
                except Exception as e:
                    logger.warning(f'Unable to decode value for {key}: {e}')
                    await self.adelete(key)
            return results
        keys = await self._afetch_set_keys(decode = True)
        data_list = await self.cache.amget(keys)
        results: Dict[str, Any] = {}
        for key, value in zip(keys, data_list):
            try:
                results[key] = self.decode_value(value, _raw = _raw, **kwargs)
            except Exception as e:
                logger.warning(f'Unable to decode value for {key}: {e}')
                await self.adelete(key)
        if exclude_base_key:
            results = {k.replace(f'{self.base_key}{self.keyjoin}', ''): v for k, v in results.items()}
        return results
    
    async def aget_keys(self, pattern: str, exclude_base_key: Optional[str] = False, **kwargs) -> List[str]:
        """
        Returns the keys that match the pattern
        """
        base_pattern = pattern if self.hset_enabled else f'{self.base_key}{self.keyjoin}{pattern}'
        if self.hset_enabled: 
            self._run_expiration_check()
            keys = await self._afetch_hset_keys(decode = True)
            keys = [key for key in keys if re.match(base_pattern, key)]
        else:
            keys: List[bytes] = await self.cache.aclient.keys(base_pattern)
            keys = [key.decode() if isinstance(key, bytes) else key for key in keys]
        if exclude_base_key:
            keys = [key.replace(f'{self.base_key}{self.keyjoin}', '') for key in keys]
        return keys

    
    async def aget_all_keys(self, exclude_base_key: Optional[bool] = False, **kwargs) -> List[str]:
        """
        Returns all the Keys
        """
        if not self.base_key:
            raise NotImplementedError('Cannot get all keys from a KVDB Cache without a base key')
        if self.hset_enabled: 
            await self._arun_expiration_check()
            return await self._afetch_hset_keys(decode = True)
        keys = await self._afetch_set_keys(decode = True)
        if exclude_base_key:
            keys = [key.replace(f'{self.base_key}{self.keyjoin}', '') for key in keys]
        return keys
    
    async def aget_all_values(self, _raw: Optional[bool] = None, **kwargs) -> List[Any]:
        """
        Returns all the Values
        """
        if not self.base_key:
            raise NotImplementedError('Cannot get all values from a KVDB Cache without a base key')
        if self.hset_enabled:
            await self._arun_expiration_check()
            data = await self.cache.ahgetall(self.base_key)
            results = []
            for key, value in data.items():
                try:
                    results.append(self.decode_value(value, _raw = _raw, **kwargs))
                except Exception as e:
                    logger.warning(f'Unable to decode value for {key}: {e}')
                    await self.adelete(key)
            return results
        keys = await self._afetch_set_keys(decode = False)
        data_list = await self.cache.amget(keys)
        results = []
        for key, value in zip(keys, data_list):
            try:
                results.append(self.decode_value(value, _raw = _raw, **kwargs))
            except Exception as e:
                logger.warning(f'Unable to decode value for {key}: {e}')
                await self.adelete(key)
        return results

    def contains(self, key, **kwargs):
        """
        Returns True if the Cache contains the Key
        """
        if self.hset_enabled: 
            self.hset_expiration_check(key)
            return self.cache.hexists(self.base_key, key)
        return self.cache.client.exists(self.get_key(key))
    
    async def acontains(self, key, **kwargs):
        """
        Returns True if the Cache contains the Key
        """
        if self.hset_enabled: 
            await self.ahset_expiration_check(key)
            return await self.cache.ahexists(self.base_key, key)
        return await self.cache.aexists(self.get_key(key))
    
    def expire(self, key: str, ex: int, **kwargs) -> None:
        """
        Expires a Key
        """
        if self.hset_enabled: 
            # logger.warning(f'Cannot expire a key in a hset cache: {self.base_key}.{key}')
            return self.hset_expire(key, ex)
        self.cache.client.expire(self.get_key(key), ex)

    async def aexpire(self, key: str, ex: int, **kwargs) -> None:
        """
        Expires a Key
        """
        if self.hset_enabled: 
            # logger.warning(f'Cannot expire a key in a hset cache: {self.base_key}.{key}')
            return await self.ahset_expire(key, ex)
            # await self.cache.aexpire(self.base_key, ex)
        await self.cache.aexpire(self.get_key(key), ex)
    
    def get_all_data_raw(self, exclude_base_key: Optional[bool] = False, **kwargs) -> Dict[str, Any]:
        """
        Loads all the Data
        """
        results = {}
        if self.hset_enabled:
            self._run_expiration_check()
            data = self.cache.hgetall(self.base_key)
            exp_index = self.cache.hgetall(self.exp_index_key)
            if exp_index: results['_exp_'] = {str(k): int(v) for k, v in exp_index.items()}
        else:
            keys = self._fetch_set_keys(decode = False)
            data = self.cache.mget(keys)
        
        for key, value in data.items():
            if isinstance(key, bytes): key = key.decode()
            if not exclude_base_key:
                key = self.get_key(key)
            else: 
                key = key.replace(f'{self.base_key}{self.keyjoin}', '')
            if isinstance(value, bytes): 
                try:
                    value = value.decode()
                except Exception as e:
                    value = value.hex()
                    if '_hexed_' not in results: results['_hexed_'] = []
                    results['_hexed_'].append(key)
            results[key] = value
        return results
        
    async def aget_all_data_raw(self, exclude_base_key: Optional[bool] = False, **kwargs) -> Dict[str, Any]:
        """
        Exports all the Data in Raw Format
        """
        results = {}
        if self.hset_enabled:
            await self._arun_expiration_check()
            data = await self.cache.ahgetall(self.base_key)
            exp_index = await self.cache.ahgetall(self.exp_index_key)
            if exp_index: results['_exp_'] = {str(k): int(v) for k, v in exp_index.items()}
        else:
            keys = await self._afetch_set_keys(decode = False)
            data = await self.cache.amget(keys)
        
        for key, value in data.items():
            if isinstance(key, bytes): key = key.decode()
            if not exclude_base_key:
                key = self.get_key(key)
            else: 
                key = key.replace(f'{self.base_key}{self.keyjoin}', '')
            if isinstance(value, bytes):
                try: 
                    value = value.decode()
                except Exception as e:
                    value = value.hex()
                    if '_hexed_' not in results: results['_hexed_'] = []
                    results['_hexed_'].append(key)
            results[key] = value
        return results
    
    def load_data_raw(self, data: Dict[str, Any], includes_base_key: Optional[bool] = False, **kwargs):
        # sourcery skip: default-get
        """
        Loads the Data
        """
        ex = kwargs.get('ex') if 'ex' in kwargs else self.expiration
        hexed = data.pop('_hexed_', [])
        exp_index = data.pop('_exp_', {})
        for key in hexed:
            try:
                data[key] = binascii.unhexlify(data[key])
            except Exception as e:
                logger.warning(f'Error Decoding Hexed Key: {key} - {e}')
        if self.hset_enabled:
            # Remove the base key from the keys
            if includes_base_key:
                data = {k.replace(f'{self.base_key}{self.keyjoin}', ''): v for k, v in data.items()}
            self.cache.hset(self.base_key, mapping = data)
            if exp_index: self.cache.hset(self.exp_index_key, mapping = exp_index)
            elif ex is not None: self.cache.expire(self.base_key, ex)
            # if ex is not None: self.cache.expire(self.base_key, ex)
            return
        if not includes_base_key:
            data = {self.get_key(k): v for k, v in data.items()}
        self.cache.mset(data)
        
    
    async def aload_data_raw(self, data: Dict[str, Any], includes_base_key: Optional[bool] = False, **kwargs):
        # sourcery skip: default-get
        """
        Loads the Data from a Raw Data Source
        This implies that the data is already encoded
        """
        ex = kwargs.get('ex') if 'ex' in kwargs else self.expiration
        hexed = data.pop('_hexed_', [])
        exp_index = data.pop('_exp_', {})
        for key in hexed:
            try:
                data[key] = binascii.unhexlify(data[key])
            except Exception as e:
                logger.warning(f'Error Decoding Hexed Key: {key} - {e}')
        if self.hset_enabled:
            # Remove the base key from the keys
            if includes_base_key:
                data = {k.replace(f'{self.base_key}{self.keyjoin}', ''): v for k, v in data.items()}
            await self.cache.ahset(self.base_key, mapping = data)
            if exp_index: await self.cache.ahset(self.exp_index_key, mapping = exp_index)
            elif ex is not None: await self.cache.aexpire(self.base_key, ex)
            return
        if not includes_base_key:
            data = {self.get_key(k): v for k, v in data.items()}
        await self.cache.amset(data)
        

    def dump_data_raw(self, include_base_key: Optional[bool] = False, **kwargs) -> Dict[str, Any]:
        """
        Dumps the Data
        """
        return self.get_all_data_raw(exclude_base_key = not include_base_key, **kwargs)
    

    async def adump_data_raw(self, include_base_key: Optional[bool] = False, **kwargs) -> Dict[str, Any]:
        """
        Dumps the Data
        """
        return await self.aget_all_data_raw(exclude_base_key = not include_base_key, **kwargs)
    
    def replicate_from(self, source: Union[str, 'KVDBSession'], **kwargs):
        """
        Replicates the data from another source and merges it into the current source
        """
        if isinstance(source, str):
            from kvdb import KVDBClient
            source = KVDBClient.session(name = f'{self.name}_source', url = source, **kwargs)
        if self.hset_enabled:
            data = source.hgetall(self.base_key)
            exp_index = source.hgetall(self.exp_index_key)
            if data:
                logger.info(f'[{self.base_key}] Replicating [{len(data)}] Data from {source.name} to {self.name}')
                self.cache.hset(self.base_key, mapping = data)
                if exp_index: self.cache.hset(self.exp_index_key, mapping = exp_index)
        else:
            keys = source.keys(f'{self.base_key}{self.keyjoin}*')
            data = source.mget(keys)
            if data:
                logger.info(f'[{self.base_key}] Replicating [{len(data)}] Data from {source.name} to {self.name}')
                self.cache.mset(data)

    async def areplicate_from(self, source: Union[str, 'KVDBSession'], **kwargs):
        """
        Replicates the data from another source and merges it into the current source
        """
        if isinstance(source, str):
            from kvdb import KVDBClient
            source = KVDBClient.session(name = f'{self.name}_source', url = source, **kwargs)
        if self.hset_enabled:
            data = await source.ahgetall(self.base_key)
            exp_index = source.hgetall(self.exp_index_key)
            if data:
                logger.info(f'[{self.base_key}] Replicating [{len(data)}] Data from {source.name} to {self.name}')
                await self.cache.ahset(self.base_key, mapping = data)
                if exp_index: await self.cache.ahset(self.exp_index_key, mapping = exp_index)
        else:
            keys = await source.akeys(f'{self.base_key}{self.keyjoin}*')
            data = await source.amget(keys)
            if data:
                logger.info(f'[{self.base_key}] Replicating [{len(data)}] Data from {source.name} to {self.name}')
                await self.cache.amset(data)
    

    """
    Add methods that reflect the `PersistentDict` API
    so that it can be used as a standalone backend
    """

    def get_child(self, key: str, **kwargs) -> 'KVDBStatefulBackend':
        """
        Gets a Child Persistent Dictionary
        """
        base_key = f'{self.base_key}.{key}' if self.base_key else key
        if 'async_enabled' not in kwargs:
            kwargs['async_enabled'] = self.async_enabled
        base_kwargs = self._kwargs.copy()
        base_kwargs.update(kwargs)
        return self.__class__(
            base_key = base_key, 
            **base_kwargs
        )



    """
    Utility Functions
    """

    def _fetch_set_keys(self, decode: Optional[bool] = True) -> List[str]:
        """
        This is a utility func for non-hset
        """
        keys: List[Union[str, bytes]] = self.cache.client.keys(f'{self.base_key}{self.keyjoin}*')
        if decode: return [key.decode() if isinstance(key, bytes) else key for key in keys]
        return keys
    
    def _fetch_hset_keys(self, decode: Optional[bool] = True) -> List[str]:
        """
        This is a utility func for hset
        """
        keys: List[Union[str, bytes]] = self.cache.hkeys(self.base_key)
        if decode: return [key.decode() if isinstance(key, bytes) else key for key in keys]
        return keys

    async def _afetch_set_keys(self, decode: Optional[bool] = True) -> List[str]:
        """
        This is a utility func for non-hset
        """
        keys: List[Union[str, bytes]] = await self.cache.akeys(f'{self.base_key}{self.keyjoin}*')
        if decode: return [key.decode() if isinstance(key, bytes) else key for key in keys]
        return keys
    
    async def _afetch_hset_keys(self, decode: Optional[bool] = True) -> List[str]:
        """
        This is a utility func for hset
        """
        keys: List[Union[str, bytes]] = await self.cache.ahkeys(self.base_key)
        if decode: return [key.decode() if isinstance(key, bytes) else key for key in keys]
        return keys
    
    """
    Math Operations
    """

    def incrby(self, key: str, amount: int = 1, **kwargs) -> int:
        """
        [int] Increments the value of the key by the given amount
        """
        if self.hset_enabled:
            return self.cache.hincrby(self.base_key, key, amount = amount, **kwargs)
        return self.cache.incrby(self.get_key(key), amount = amount, **kwargs)
    
    def incrbyfloat(self, key: str, amount: float = 1.0, **kwargs) -> float:
        """
        [float] Increments the value of the key by the given amount
        """
        if self.hset_enabled:
            return self.cache.hincrbyfloat(self.base_key, key, amount = amount, **kwargs)
        return self.cache.incrbyfloat(self.get_key(key), amount = amount, **kwargs)
    
    async def aincrby(self, key: str, amount: int = 1, **kwargs) -> int:
        """
        [int] Increments the value of the key by the given amount
        """
        if self.hset_enabled:
            return await self.cache.ahincrby(self.base_key, key, amount = amount, **kwargs)
        return await self.cache.aincrby(self.get_key(key), amount = amount, **kwargs)
    
    async def aincrbyfloat(self, key: str, amount: float = 1.0, **kwargs) -> float:
        """
        [float] Increments the value of the key by the given amount
        """
        if self.hset_enabled:
            return await self.cache.ahincrbyfloat(self.base_key, key, amount = amount, **kwargs)
        return await self.cache.aincrbyfloat(self.get_key(key), amount = amount, **kwargs)
    
    def decrby(self, key: str, amount: int = 1, **kwargs) -> int:
        """
        [int] Decrements the value of the key by the given amount
        """
        if self.hset_enabled:
            return self.cache.hincrby(self.base_key, key, amount = (amount * -1), **kwargs)
        return self.cache.decrby(self.get_key(key), amount = amount, **kwargs)

    def decrbyfloat(self, key: str, amount: float = 1.0, **kwargs) -> float:
        """
        [float] Decrements the value of the key by the given amount
        """
        if self.hset_enabled:
            return self.cache.hincrbyfloat(self.base_key, key, amount = (amount * -1), **kwargs)
        return self.cache.incrbyfloat(self.get_key(key), amount = (amount * -1), **kwargs)
    
    async def adecrby(self, key: str, amount: int = 1, **kwargs) -> int:
        """
        [int] Decrements the value of the key by the given amount
        """
        if self.hset_enabled:
            return await self.cache.ahincrby(self.base_key, key, amount = (amount * -1), **kwargs)
        return await self.cache.adecrby(self.get_key(key), amount = amount, **kwargs)
    
    async def adecrbyfloat(self, key: str, amount: float = 1.0, **kwargs) -> float:
        """
        [float] Decrements the value of the key by the given amount
        """
        if self.hset_enabled:
            return await self.cache.ahincrbyfloat(self.base_key, key, amount = (amount * -1), **kwargs)
        return await self.cache.aincrbyfloat(self.get_key(key), amount = (amount * -1), **kwargs)
    
    """
    Set Operations
    """

    def sadd(self, key: str, *values: str, **kwargs) -> int:
        """
        Adds the given values to the set stored at key
        """
        if self.hset_enabled:
            value: Set = self.get(key, default = set())
            value.update(values)
            self.set(key, values, **kwargs)
            return len(value)
        return self.cache.sadd(self.get_key(key), *values, **kwargs)
    
    async def asadd(self, key: str, *values: str, **kwargs) -> int:
        """
        Adds the given values to the set stored at key
        """
        if self.hset_enabled:
            value: Set = await self.aget(key, default = set())
            value.update(values)
            await self.aset(key, value, **kwargs)
            return len(value)
        return await self.cache.asadd(self.get_key(key), *values, **kwargs)
    
    def smembers(self, key: str, **kwargs) -> List[str]:
        """
        Returns the members of the set stored at key
        """
        if self.hset_enabled:
            return self.get(key, default = set())
        return self.cache.smembers(self.get_key(key), **kwargs)
    
    async def asmembers(self, key: str, **kwargs) -> List[str]:
        """
        Returns the members of the set stored at key
        """
        if self.hset_enabled:
            return await self.aget(key, default = set())
        return await self.cache.asmembers(self.get_key(key), **kwargs)
    
    def sismember(self, key: str, value: str, **kwargs) -> bool:
        """
        Returns True if value is a member of the set stored at key
        """
        if self.hset_enabled:
            return value in self.get(key, default = set())
        return self.cache.sismember(self.get_key(key), value, **kwargs)
    
    async def asismember(self, key: str, value: str, **kwargs) -> bool:
        """
        Returns True if value is a member of the set stored at key
        """
        if self.hset_enabled:
            return value in await self.aget(key, default = set())
        return await self.cache.asismember(self.get_key(key), value, **kwargs)
    
    def slength(self, key: str, **kwargs) -> int:
        """
        Returns the number of elements in the set stored at key
        """
        if self.hset_enabled:
            return len(self.get(key, default = set()))
        return self.cache.scard(self.get_key(key), **kwargs)
    
    async def aslength(self, key: str, **kwargs) -> int:
        """
        Returns the number of elements in the set stored at key
        """
        if self.hset_enabled:
            return len(await self.aget(key, default = set()))
        return await self.cache.ascard(self.get_key(key), **kwargs)
    
    def srem(self, key: str, *values: str, **kwargs) -> int:
        """
        Removes the given values from the set stored at key
        """
        if self.hset_enabled:
            value: Set = self.get(key, default = set())
            value.difference_update(values)
            self.set(key, value, **kwargs)
            return len(value)
        return self.cache.srem(self.get_key(key), *values, **kwargs)
    
    async def asrem(self, key: str, *values: str, **kwargs) -> int:
        """
        Removes the given values from the set stored at key
        """
        if self.hset_enabled:
            value: Set = await self.aget(key, default = set())
            value.difference_update(values)
            await self.aset(key, value, **kwargs)
            return len(value)
        return await self.cache.asrem(self.get_key(key), *values, **kwargs)
    
    def spop(self, key: str, count: int = 1, **kwargs) -> List[str]:
        """
        Removes and returns a random member of the set stored at key
        """
        if self.hset_enabled:
            value: Set = self.get(key, default = set())
            return [] if len(value) < count else list(value)[:count]
        return self.cache.spop(self.get_key(key), count = count, **kwargs)
    

    async def aspop(self, key: str, count: int = 1, **kwargs) -> List[str]:
        """
        Removes and returns a random member of the set stored at key
        """
        if self.hset_enabled:
            value: Set = await self.aget(key, default = set())
            return [] if len(value) < count else list(value)[:count]
        return await self.cache.aspop(self.get_key(key), count = count, **kwargs)
    

    def migrate_schema(self, schema_map: Dict[str, str], overwrite: Optional[bool] = False, **kwargs) -> None:
        """
        Migrates the schema of the current object to the new schema
        """
        if self.serializer.name != 'json': 
            raise ValueError(f'Cannot migrate schema for {self.serializer.name} serializer')
        # logger.info(f'Migrating schema for {self.name} using {schema_map}')
        # from lazyops.utils import Timer
        from lzo.utils import Timer
        t = Timer()
        results = {}
        if self.hset_enabled:
            self._run_expiration_check()
            data = self.cache.hgetall(self.base_key)
        else:
            keys = self._fetch_set_keys(decode = False)
            data = self.cache.mget(keys)
        logger.info(f'Migrating schema for {self.name} using {schema_map} with {len(data)} results')
        for key, value in data.items():
            if isinstance(key, bytes): key = key.decode()
            try:
                value = self.serializer.decode(value, schema_map = schema_map, raise_errors = True)
            except Exception as e:
                logger.trace(f'Error Decoding Value: ({type(value)}) {str(value)[:1000]}', e)
                raise e
            results[key] = self.serializer.encode(value)
        
        if self.hset_enabled: self.cache.hmset(self.base_key, mapping = results)
        else: self.cache.mset(results)
        logger.info(f'Completed Migration for {self.name} with {len(results)} results in {t.total_s}')
        return results

    async def amigrate_schema(self, schema_map: Dict[str, str], overwrite: Optional[bool] = False, **kwargs) -> None:
        """
        Migrates the schema of the current object to the new schema
        """
        if self.serializer.name != 'json': raise ValueError(f'Cannot migrate schema for {self.serializer.name} serializer')
        # from lazyops.utils import Timer
        from lzo.utils import Timer
        t = Timer()
        results = {}
        if self.hset_enabled:
            await self._arun_expiration_check()
            data = await self.cache.ahgetall(self.base_key)
        else:
            keys = await self._afetch_set_keys(decode = False)
            data = await self.cache.amget(keys)
        logger.info(f'Migrating schema for {self.name} using {schema_map} with {len(data)} results')
        for key, value in data.items():
            if isinstance(key, bytes): key = key.decode()
            try:
                value = await self.serializer.adecode(value, schema_map = schema_map, raise_errors = True)
            except Exception as e:
                logger.trace(f'Error Decoding Value: ({type(value)}) {str(value)[:1000]}', e)
                raise e
            results[key] = await self.serializer.aencode(value)
        
        if self.hset_enabled: await self.cache.ahmset(self.base_key, mapping = results)
        else: await self.cache.amset(results)
        logger.info(f'Completed Migration for {self.name} with {len(results)} results in {t.total_s}')
        return results

    """
    Cloning Methods    
    """
        
    
    def clone(
        self, 
        target: Optional[str], 
        target_base_key: Optional[str] = None,
        target_db_id: Optional[int] = None,
        schema_map: Optional[Dict[str, str]] = None,
        overwrite: Optional[bool] = False, 
        **kwargs
    ):
        """
        Clones the data from the current PersistentDict to a new PersistentDict

            The target should be a URL
            Schema Map is only supported for the JSON Serializer
        """
        pass
    
    async def _aclone(
        self,
        from_session: KVDBSession,
        from_base_key: str,
        from_keys: List[str],
        to_session: KVDBSession,
        to_base_key: str,
        schema_map: Optional[Dict[str, str]] = None,
        excluded: Optional[List[str]] = None,
        filter_function: Optional[Callable[[str], bool]] = None,
        hset_key_function: Optional[Callable[[str], str]] = None,
        raise_errors: Optional[bool] = True,
        verbose: Optional[bool] = True,
        overwrite: Optional[bool] = None,
        **kwargs
    ) -> Dict[str, Union[List[str], int, float]]:  # sourcery skip: low-code-quality
        """
        Runs the Clone Operation
        """
        # from lazyops.utils import Timer
        from lzo.utils import Timer
        t = Timer()
        from_keys = [k.decode() if isinstance(k, bytes) else k for k in from_keys]

        existing_keys: List[str] = []
        if overwrite is False:
            existing_keys = await to_session.akeys(f'{to_base_key}*')
            if (exp_keys := (await to_session.akeys(f'_exp_:{to_base_key}*'))): existing_keys.extend(exp_keys)
            existing_keys = [k.decode() if isinstance(k, bytes) else k for k in existing_keys]

        is_diff_key = from_base_key != to_base_key
        can_migrate_schema = schema_map is not None and self.serializer.name == 'json'
        excluded = excluded or []
        completed, errors, skipped = 0, 0, 0
        completed_keys = []
        completed_hkeys, skipped_hkeys = [], []
        for key in from_keys:
            key_type = await from_session.atype(key)
            key_type = key_type.decode() if isinstance(key_type, bytes) else key_type
            if (key in excluded) or (filter_function and filter_function(key, key_type = key_type)): 
                skipped += 1
                continue
            to_key = key.replace(from_base_key, to_base_key) if is_diff_key else key
            if (to_key in excluded) or (filter_function and filter_function(to_key, key_type = key_type)): 
                skipped += 1
                continue
            if verbose: logger.info(f'Copying Key: {key} -> |g|{to_key}|e|', prefix = from_base_key, colored = True)
            try:
                if verbose: logger.info(f'Key Type: |g|{key} = {key_type}|e|', prefix = from_base_key, colored = True)
                # These are our two primary types
                if key_type == 'string':
                    if to_key in existing_keys: 
                        skipped += 1
                        continue
                    if '_exp_:' not in key and can_migrate_schema:
                        value = await from_session.aget(key)
                        try:
                            value = await self.serializer.adecode(value, schema_map = schema_map, raise_errors = True)
                        except Exception as e:
                            logger.trace(f'Error Decoding Value for Key {from_base_key}: ({type(value)}) {str(value)[:1000]}', e)
                            if raise_errors: raise e
                            errors += 1
                            continue
                        value = await self.serializer.aencode(value)
                        await to_session.aset(to_key, value)
                    else: await to_session.aset(to_key, await from_session.aget(key))
                elif key_type == 'hash':
                    existing_hkeys: List[str] = []
                    if not overwrite:
                        existing_hkeys = await to_session.ahkeys(to_key)
                        existing_hkeys = [k.decode() if isinstance(k, bytes) else k for k in existing_hkeys]
                        if verbose: logger.info(f'Existing Hash Keys: {len(existing_hkeys)}', prefix = to_key, colored = True)
                    
                    data = await from_session.ahgetall(key)
                    if '_exp_:' not in key and can_migrate_schema:
                        # data = await from_session.ahgetall(key)
                        results = {}
                        for k,v in data.items():
                            k = k.decode() if isinstance(k, bytes) else k
                            if (k in excluded) or (filter_function and filter_function(k, key_type = 'hash_item')) or (k in existing_hkeys):
                                skipped_hkeys.append(f'{to_key}:{k}')
                                continue
                            if hset_key_function: k = hset_key_function(k)
                            if verbose: logger.info(f'Copying HKey: {key}:{k} -> |g|{to_key}:{k}|e|', prefix = from_base_key, colored = True)
                            try:
                                v = await self.serializer.adecode(v, schema_map = schema_map, raise_errors = True)
                            except Exception as e:
                                logger.trace(f'Error Decoding Value for HKey {key}:{k}: ({type(v)}) {str(v)[:1000]}', e)
                                if raise_errors: raise e
                                errors += 1
                                continue
                            results[k] = await self.serializer.aencode(v)
                            completed_hkeys.append(f'{to_key}:{k}')
                        if results: await to_session.ahmset(to_key, mapping = results)
                    
                    elif existing_hkeys:
                        # data = await from_session.ahgetall(key)
                        results = {}
                        for k,v in data.items():
                            k = k.decode() if isinstance(k, bytes) else k
                            if (k in excluded) or (filter_function and filter_function(k, key_type = 'hash_item')) or (k in existing_hkeys):
                                skipped_hkeys.append(f'{to_key}:{k}')
                                continue
                            if hset_key_function: k = hset_key_function(k)
                            if verbose: logger.info(f'Copying HKey: {key}:{k} -> |g|{to_key}:{k}|e|', prefix = from_base_key, colored = True)
                            results[k] = v
                            completed_hkeys.append(f'{to_key}:{k}')
                        if results: await to_session.ahmset(to_key, mapping = results)
                    elif filter_function or hset_key_function:
                        results = {}
                        for k,v in data.items():
                            k = k.decode() if isinstance(k, bytes) else k
                            if (k in excluded) or (filter_function and filter_function(k, key_type = 'hash_item')):
                                skipped_hkeys.append(f'{to_key}:{k}')
                                continue
                            if hset_key_function: k = hset_key_function(k)
                            results[k] = v
                            completed_hkeys.append(f'{to_key}:{k}')
                        if results: await to_session.ahmset(to_key, mapping = results)
                    else:
                        await to_session.ahmset(to_key, data)
                        _hkeys = [k.decode() if isinstance(k, bytes) else k for k in data.keys()]
                        _hkeys = [f'{to_key}:{k}' for k in _hkeys]
                        completed_hkeys.extend(_hkeys)
                
                elif key_type == 'set': 
                    if key in existing_keys: 
                        skipped += 1
                        continue
                    await to_session.asadd(to_key, await from_session.asmembers(key))
                elif key_type == 'list': 
                    if key in existing_keys: 
                        skipped += 1
                        continue
                    await to_session.arpush(to_key, await from_session.alrange(key, 0, -1))
                elif key_type == 'zset':
                    if key in existing_keys: 
                        skipped += 1
                        continue
                    for k,v in await from_session.azrange(key, 0, -1, withscores=True):
                        await to_session.azadd(to_key, k, v)
                completed += 1
                completed_keys.append(key)
                if verbose: logger.info(f'Completed Cloning Key: |g|{to_key}|e|', prefix = from_base_key, colored = True)
            except Exception as e:
                logger.error(f'Error Cloning Key: {key} - {e}')
                if raise_errors: raise e
                errors += 1
        logger.info(f'Completed Cloning from |g|{from_session.url}|e| for {from_base_key} -> {to_base_key} (completed: {completed}, errors:  {errors}, skipped: {skipped}, total: {len(from_keys)}, hkeys_set: {len(completed_hkeys)}, hkeys_skipped: {len(skipped_hkeys)}) results in {t.total_s}', prefix = from_base_key, colored = True)
        return {
            'completed': completed,
            'errors': errors,
            'skipped': skipped,
            'completed_keys': completed_keys,
            'completed_hkeys': completed_hkeys,
            'skipped_hkeys': skipped_hkeys,
            'num_completed_hkeys': len(completed_hkeys),
            'num_skipped_hkeys': len(skipped_hkeys),
            'duration': t.total,
        }

    
    async def aclone(
        self,
        target: str, 
        target_base_key: Optional[str] = None,
        target_db_id: Optional[int] = None,
        source_url: Optional[Union[str, KVDBUrl]] = None,
        source_base_key: Optional[str] = None,
        schema_map: Optional[Dict[str, str]] = None,
        overwrite: Optional[bool] = None, 
        excluded: Optional[Union[str, List[str]]] = None,
        filter_function: Optional[Callable[[str], bool]] = None,
        hset_key_function: Optional[Callable[[str], str]] = None,
        raise_errors: Optional[bool] = True,
        verbose: Optional[bool] = True,
        **kwargs
    ) -> Dict[str, Union[List[str], int, float]]:  # sourcery skip: low-code-quality
        """
        Clones the data from the current PersistentDict to a new PersistentDict
                
            The target should be a URL
            Schema Map is only supported for the JSON Serializer
        """
        source_url = self.cache.url if source_url is None else KVDBUrl(source_url)
        target_url = KVDBUrl(target)
        if target_db_id: target_url = target_url.with_db_id(target_db_id)
        target_base_key = target_base_key or self.base_key
        source_base_key = source_base_key or self.base_key
        logger.info(f'Cloning |g|{source_url}|e| to |y|{target_url}|e|: [{source_base_key} > |g|{target_base_key}|e|]', colored = True, prefix = self.name)
        from kvdb.client import KVDBClient
        src_session = KVDBClient.create_session(name = f'{self.cache.name}-source', url = source_url, serializer = None, disable_store = True)
        target_session = KVDBClient.create_session(name = f'{self.cache.name}-target', url = target_url, serializer = None, disable_store = True)
        excluded = excluded or []
        if isinstance(excluded, str): excluded = [excluded]
        
        source_keys: List[str] = await src_session.akeys(f'{source_base_key}*')
        if not source_keys: 
            logger.info(f'No keys found in {source_url}', prefix = self.name)
            return
        logger.info(f'Found {len(source_keys)} keys in {source_url}', prefix = self.name, colored = True)
        if exp_keys := (await src_session.akeys(f'_exp_:{source_base_key}*')): source_keys.extend(exp_keys)
        return await self._aclone(
            from_session = src_session,
            from_base_key = source_base_key,
            from_keys = source_keys,
            to_session = target_session,
            to_base_key = target_base_key,
            schema_map = schema_map,
            excluded = excluded,
            filter_function = filter_function,
            hset_key_function = hset_key_function,
            raise_errors = raise_errors,
            verbose = verbose,
            overwrite = overwrite,
            **kwargs,
        )
        

    async def aclone_from(
        self,
        target: str, 
        target_base_key: Optional[str] = None,
        target_db_id: Optional[int] = None,
        source_url: Optional[Union[str, KVDBUrl]] = None,
        source_base_key: Optional[str] = None,
        schema_map: Optional[Dict[str, str]] = None,
        overwrite: Optional[bool] = None, 
        excluded: Optional[Union[str, List[str]]] = None,
        filter_function: Optional[Callable[[str], bool]] = None,
        hset_key_function: Optional[Callable[[str], str]] = None,
        raise_errors: Optional[bool] = True,
        verbose: Optional[bool] = True,
        **kwargs
    ) -> Dict[str, Union[List[str], int, float]]:    # sourcery skip: low-code-quality
        """
        Clones the data from the target PersistentDict to a current PersistentDict
                
            The target should be a URL
            Schema Map is only supported for the JSON Serializer
        """
        source_url = self.cache.url if source_url is None else KVDBUrl(source_url)
        target_url = KVDBUrl(target)
        if target_db_id: target_url = target_url.with_db_id(target_db_id)
        target_base_key = target_base_key or self.base_key
        source_base_key = source_base_key or self.base_key
        logger.info(f'Cloning |g|{target_url}|e| to |y|{source_url}|e|: [{target_base_key} > |g|{source_base_key}|e|]', colored = True, prefix = self.name)
        from kvdb.client import KVDBClient
        src_session = KVDBClient.create_session(name = f'{self.cache.name}-source', url = source_url, serializer = None, disable_store = True)
        target_session = KVDBClient.create_session(name = f'{self.cache.name}-target', url = target_url, serializer = None, disable_store = True)
        excluded = excluded or []
        if isinstance(excluded, str): excluded = [excluded]
        target_keys: List[str] = await target_session.akeys(f'{target_base_key}*')
        if not target_keys: 
            logger.info(f'No keys found in {target_url}', prefix = self.name)
            return
        logger.info(f'Found {len(target_keys)} keys in {target_url}', prefix = self.name, colored = True)
        if exp_keys := (await target_session.akeys(f'_exp_:{target_base_key}*')): target_keys.extend(exp_keys)
        return await self._aclone(
            from_session=target_session,
            from_base_key=target_base_key,
            from_keys=target_keys,
            to_session=src_session,
            to_base_key=source_base_key,
            schema_map=schema_map,
            excluded=excluded,
            overwrite=overwrite,
            filter_function=filter_function,
            hset_key_function=hset_key_function,
            raise_errors=raise_errors,
            verbose=verbose,
            **kwargs,
        )

    """
    Context Locks    
    """
        

    def acquire_lock(self, timeout: Optional[float] = None, blocking: Optional[bool] = True, **kwargs) -> bool:
        """
        Acquires the lock
        """
        if self._lock is None: self._lock = self.cache.lock(name = self.get_key('ctxlock'), thread_local = False)
        if timeout is None: timeout = self.context_timeout
        try:
            return self._lock.acquire(blocking_timeout = timeout, blocking = blocking)
        except Exception as e:
            logger.error(f'Error acquiring lock: {e}')
            return False
    
    def release_lock(self):
        """
        Releases the lock
        """
        if self._lock is not None:
            try:
                self._lock.release()
            except Exception as e:
                logger.error(f'Error releasing lock: {e}')
                self.cache.delete(self.get_key('ctxlock'))

    async def acquire_alock(self, timeout: Optional[float] = None, blocking: Optional[bool] = True, **kwargs) -> bool:
        """
        Acquires the lock
        """
        if self._alock is None: self._alock = self.cache.alock(name = self.get_key('ctxlock'), thread_local = False)
        if timeout is None: timeout = self.context_timeout
        try:
            return await self._alock.acquire(blocking = blocking, blocking_timeout = timeout)
        except Exception as e:
            logger.error(f'Error acquiring async lock: {e} - {self._alock}')
            return False
        
    async def release_alock(self):
        """
        Releases the lock
        """
        if self._alock is not None:
            try:
                await self._alock.release()
            except Exception as e:
                logger.error(f'Error releasing lock: {e}')
                await self.cache.delete(self.get_key('ctxlock'))






PersistentDict.register_backend('kvdb', KVDBStatefulBackend)