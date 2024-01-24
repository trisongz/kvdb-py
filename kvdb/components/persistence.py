from __future__ import annotations

"""
A KVDB-backed Dict-like object
"""
import re
from kvdb.configs import settings as kvdb_settings
from kvdb.configs.base import SerializerConfig
from kvdb.utils.logs import logger
from kvdb.types.base import supported_schemas, KVDBUrl
from lazyops.libs.persistence.backends.base import BaseStatefulBackend, SchemaType
from lazyops.libs.persistence import PersistentDict

from typing import Any, Dict, Optional, Union, Iterable, List, Type, TYPE_CHECKING


if TYPE_CHECKING:
    from .session import KVDBSession
    from lazyops.types.models import BaseSettings
    from lazyops.libs.persistence.serializers.base import ObjectValue


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
        **kwargs,
    ):
        """
        Initializes the backend
        """
        if settings is None: settings = kvdb_settings
        self.base_key = base_key
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


    def encode_value(self, value: Union[Any, SchemaType], **kwargs) -> Union[str, bytes]:
        """
        Encodes a Value
        """
        return self.serializer.encode(value, **kwargs) if self.serializer is not None else value
    
    async def aencode_value(self, value: Union[Any, SchemaType], **kwargs) -> Union[str, bytes]:
        """
        Encodes a Value
        """
        return await self.serializer.aencode(value, **kwargs) if self.serializer is not None else value

    def decode_value(self, value: Union[str, bytes], **kwargs) -> Any:
        """
        Decodes a Value
        """
        return self.serializer.decode(value, **kwargs) if self.serializer is not None else value
    
    async def adecode_value(self, value: Union[str, bytes], **kwargs) -> Any:
        """
        Decodes a Value
        """
        return await self.serializer.adecode(value, **kwargs) if self.serializer is not None else value


    def get_key(self, key: str) -> str:
        """
        Gets a Key
        """
        if not self.base_key: return key
        return key if self.base_key in key else f'{self.base_key}{self.keyjoin}{key}'
    
    def get(self, key: str, default: Optional[Any] = None, **kwargs) -> Optional[Any]:
        """
        Gets a Value from the DB
        """
        if self.hset_enabled: value = self.cache.hget(self.base_key, key)
        else: value = self.cache.client.get(self.get_key(key))
        if value is None: return default
        try:
            return self.decode_value(value)
        except Exception as e:
            logger.error(f'Error Getting Value for Key: {key} - {e}')
            self.delete(key)
            return default

    def get_values(self, keys: Iterable[str]) -> List[Any]:
        """
        Gets a Value from the DB
        """
        if self.hset_enabled: values = self.cache.hmget(self.base_key, keys)
        else: values = self.cache.client.mget([self.get_key(key) for key in keys])
        results = []
        for key, value in zip(keys, values):
            try:
                results.append(self.decode_value(value))
            except Exception as e:
                logger.error(f'Error Getting Value for Key: {key} - {e}')
                self.delete(key)
                results.append(None)
        return results


    def set(self, key: str, value: Any, ex: Optional[int] = None, **kwargs) -> None:
        """
        Saves a Value to the DB
        """
        ex = ex or self.expiration
        if self.hset_enabled:
            self.cache.hset(self.base_key, key, self.encode_value(value))
            if ex is not None: self.cache.expire(self.base_key, ex)
        else:
            self.cache.client.set(self.get_key(key), self.encode_value(value), ex = ex)
    
    def set_batch(self, data: Dict[str, Any], ex: Optional[int] = None, **kwargs) -> None:
        """
        Saves a Value to the DB
        """
        ex = ex or self.expiration
        data = {k: self.encode_value(v) for k, v in data.items()}
        if self.hset_enabled:
            self.cache.client.hset(self.base_key, mapping = data)
            if ex is not None: self.cache.expire(self.base_key, ex)
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
        if self.hset_enabled: self.cache.hdel(self.base_key, key)
        else: self.cache.client.delete(self.get_key(key))

    def clear(self, *keys, **kwargs):
        """
        Clears the Cache
        """
        if self.hset_enabled:
            if keys: self.cache.hdel(self.base_key, *keys)
            else: self.cache.delete(self.base_key)
        elif keys:
            keys = [self.get_key(key) for key in keys]
            self.cache.delete(*keys)
        else:
            keys = self.cache.client.keys(f'{self.base_key}{self.keyjoin}*')
            if keys: self.cache.client.delete(*keys)
    
    async def aget(self, key: str, default: Optional[Any] = None, **kwargs) -> Optional[Any]:
        """
        Gets a Value from the DB
        """
        if self.hset_enabled: value = await self.cache.ahget(self.base_key, key)
        else: value = await self.cache.aget(self.get_key(key))
        if value is None: return default
        try:
            return self.decode_value(value)
        except Exception as e:
            logger.error(f'Error Getting Value for Key: {key} - {e}')
            await self.adelete(key)
            return default

    async def aget_values(self, keys: Iterable[str]) -> List[Any]:
        """
        Gets a Value from the DB
        """
        if self.hset_enabled: values = await self.cache.ahmget(self.base_key, keys)
        else: values = await self.cache.amget([self.get_key(key) for key in keys])
        results = []
        for key, value in zip(keys, values):
            try: results.append(self.decode_value(value))
            except Exception as e:
                logger.error(f'Error Getting Value for Key: {key} - {e}')
                await self.adelete(key)
                results.append(None)
        return results
        
    async def aset(self, key: str, value: Any, ex: Optional[int] = None, **kwargs) -> None:
        """
        Saves a Value to the DB
        """
        ex = ex or self.expiration
        if self.hset_enabled:
            await self.cache.ahset(self.base_key, key, self.encode_value(value))
            if ex is not None: await self.cache.aexpire(self.base_key, ex)
        else:
            await self.cache.aset(self.get_key(key), self.encode_value(value), ex = ex)

    async def aset_batch(self, data: Dict[str, Any], ex: Optional[int] = None, **kwargs) -> None:
        """
        Saves a Value to the DB
        """
        ex = ex or self.expiration
        data = {k: self.encode_value(v) for k, v in data.items()}
        if self.hset_enabled:
            await self.cache.ahset(self.base_key, mapping = data)
            if ex is not None: await self.cache.aexpire(self.base_key, ex)
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
        if self.hset_enabled: await self.cache.ahdel(self.base_key, key)
        else: await self.cache.adelete(self.get_key(key))

    async def aclear(self, *keys, **kwargs):
        """
        Clears the Cache
        """
        if self.hset_enabled:
            if keys: await self.cache.ahdel(self.base_key, *keys)
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
        if self.hset_enabled: return iter(self.cache.hkeys(self.base_key))
        if not self.base_key:
            raise NotImplementedError('Cannot iterate over a Redis Cache without a base key')
        return iter(self.cache.client.keys(f'{self.base_key}{self.keyjoin}*'))
    
    def __len__(self):
        """
        Returns the Length of the Cache
        """
        if self.hset_enabled: return self.cache.hlen(self.base_key)
        if not self.base_key:
            raise NotImplementedError('Cannot get the length of a Redis Cache without a base key')
        return len(self.cache.client.keys(f'{self.base_key}{self.keyjoin}*'))
    

    def get_all_data(self, exclude_base_key: Optional[bool] = False) -> Dict[str, Any]:
        """
        Loads all the Data
        """
        if not self.hset_enabled and not self.base_key:
            raise NotImplementedError('Cannot get all data from a Redis Cache without a base key')
        if self.hset_enabled:
            data = self.cache.hgetall(self.base_key)
            results = {}
            for key, value in data.items():
                if isinstance(key, bytes): key = key.decode()
                try: results[key] = self.decode_value(value)
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
                results[key] = self.decode_value(value)
            except AttributeError:
                logger.warning(f'Unable to decode value for {key}')
                self.delete(key)
        if exclude_base_key:
            results = {k.replace(f'{self.base_key}.', ''): v for k, v in results.items()}
        return results
    
    def get_keys(self, pattern: str, exclude_base_key: Optional[str] = False) -> List[str]:
        """
        Returns the keys that match the pattern
        """
        # if not self.base_key:
        #     raise NotImplementedError('Cannot get keys from a Redis Cache without a base key')
        base_pattern = pattern if self.hset_enabled else f'{self.base_key}{pattern}'
        if self.hset_enabled: 
            keys = self._fetch_hset_keys(decode = True)
            keys = [key for key in keys if re.match(base_pattern, key)]
        else:
            keys: List[str] = self.cache.client.keys(base_pattern)        
        if exclude_base_key:
            keys = [key.replace(f'{self.base_key}.', '') for key in keys]
        return keys


    def get_all_keys(self, exclude_base_key: Optional[bool] = False) -> List[str]:
        """
        Returns all the Keys
        """
        if not self.base_key:
            raise NotImplementedError('Cannot get all keys from a Redis Cache without a base key')
        if self.hset_enabled: return self._fetch_hset_keys(decode = True)
        keys = self._fetch_set_keys(decode = True)
        if exclude_base_key:
            keys = [key.replace(f'{self.base_key}.', '') for key in keys]
        return keys
    
    def get_all_values(self) -> List[Any]:
        """
        Returns all the Values
        """
        if not self.base_key:
            raise NotImplementedError('Cannot get all values from a Redis Cache without a base key')
        if self.hset_enabled:
            data = self.cache.hgetall(self.base_key)
            results = []
            for key, value in data.items():
                try:
                    results.append(self.decode_value(value))
                except Exception as e:
                    logger.warning(f'Unable to decode value for {key}: {e}')
                    self.delete(key)
            return results
        keys = self._fetch_set_keys(decode = False)
        data_list = self.cache.client.mget(keys)
        results = []
        for key, value in zip(keys, data_list):
            try:
                results.append(self.decode_value(value))
            except Exception as e:
                logger.warning(f'Unable to decode value for {key}: {e}')
                self.delete(key)
        return results

    async def aget_all_data(self, exclude_base_key: Optional[bool] = False) -> Dict[str, Any]:
        """
        Loads all the Data
        """
        if not self.base_key:
            raise NotImplementedError('Cannot get all data from a Redis Cache without a base key')
        if self.hset_enabled:
            data = await self.cache.ahgetall(self.base_key)
            results = {}
            for key, value in data.items():
                if isinstance(key, bytes): key = key.decode()
                try:
                    results[key] = self.decode_value(value)
                except Exception as e:
                    logger.warning(f'Unable to decode value for {key}: {e}')
                    await self.adelete(key)
            return results
        keys = await self._afetch_set_keys(decode = True)
        data_list = await self.cache.amget(keys)
        results: Dict[str, Any] = {}
        for key, value in zip(keys, data_list):
            try:
                results[key] = self.decode_value(value)
            except Exception as e:
                logger.warning(f'Unable to decode value for {key}: {e}')
                await self.adelete(key)
        if exclude_base_key:
            results = {k.replace(f'{self.base_key}.', ''): v for k, v in results.items()}
        return results
    
    async def aget_keys(self, pattern: str, exclude_base_key: Optional[str] = False) -> List[str]:
        """
        Returns the keys that match the pattern
        """
        base_pattern = pattern if self.hset_enabled else f'{self.base_key}{pattern}'
        if self.hset_enabled: 
            keys = await self._afetch_hset_keys(decode = True)
            keys = [key for key in keys if re.match(base_pattern, key)]
        else:
            keys: List[str] = await self.cache.aclient.keys(base_pattern)
        if exclude_base_key:
            keys = [key.replace(f'{self.base_key}.', '') for key in keys]
        return keys

    
    async def aget_all_keys(self, exclude_base_key: Optional[bool] = False) -> List[str]:
        """
        Returns all the Keys
        """
        if not self.base_key:
            raise NotImplementedError('Cannot get all keys from a Redis Cache without a base key')
        if self.hset_enabled: 
            return await self._afetch_hset_keys(decode = True)
        keys = await self._afetch_set_keys(decode = True)
        if exclude_base_key:
            keys = [key.replace(f'{self.base_key}.', '') for key in keys]
        return keys
    
    async def aget_all_values(self) -> List[Any]:
        """
        Returns all the Values
        """
        if not self.base_key:
            raise NotImplementedError('Cannot get all values from a Redis Cache without a base key')
        if self.hset_enabled:
            data = await self.cache.ahgetall(self.base_key)
            results = []
            for key, value in data.items():
                try:
                    results.append(self.decode_value(value))
                except Exception as e:
                    logger.warning(f'Unable to decode value for {key}: {e}')
                    await self.adelete(key)
            return results
        keys = await self._afetch_set_keys(decode = False)
        data_list = await self.cache.amget(keys)
        results = []
        for key, value in zip(keys, data_list):
            try:
                results.append(self.decode_value(value))
            except Exception as e:
                logger.warning(f'Unable to decode value for {key}: {e}')
                await self.adelete(key)
        return results

    def contains(self, key):
        """
        Returns True if the Cache contains the Key
        """
        if self.hset_enabled: return self.cache.hexists(self.base_key, key)
        return self.cache.client.exists(self.get_key(key))
    
    async def acontains(self, key):
        """
        Returns True if the Cache contains the Key
        """
        if self.hset_enabled: return await self.cache.ahexists(self.base_key, key)
        return await self.cache.aexists(self.get_key(key))
    
    def expire(self, key: str, ex: int) -> None:
        """
        Expires a Key
        """
        if self.hset_enabled: 
            logger.warning(f'Cannot expire a key in a hset cache: {self.base_key}.{key}')
            return
        self.cache.client.expire(self.get_key(key), ex)

    async def aexpire(self, key: str, ex: int) -> None:
        """
        Expires a Key
        """
        if self.hset_enabled: 
            logger.warning(f'Cannot expire a key in a hset cache: {self.base_key}.{key}')
            return
            # await self.cache.aexpire(self.base_key, ex)
        await self.cache.aexpire(self.get_key(key), ex)

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
    

PersistentDict.register_backend('kvdb', KVDBStatefulBackend)