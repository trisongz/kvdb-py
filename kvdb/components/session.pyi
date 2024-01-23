import abc
import types
import typing
from kvdb.types.base import KVDBUrl
from kvdb.configs.main import KVDBSettings
from kvdb.io.serializers import SerializerT
from kvdb.io.encoder import Encoder
from kvdb.utils.logs import Logger
from kvdb.types.generic import ExpiryT, KeyT, Number 
from kvdb.types.contexts import SessionPools, SessionState
from kvdb.components.lock import Lock, AsyncLock
from kvdb.components.pubsub import PubSub, AsyncPubSub, AsyncPubSubT, PubSubT
from kvdb.components.pipeline import AsyncPipelineT, PipelineT
from kvdb.components.client import AsyncKVDB, KVDB, ClientT
from lazyops.libs.persistence import PersistentDict
from redis.commands.core import ResponseT, Script, BitFieldOperation
from redis.typing import ChannelT, EncodableT, KeysT, GroupT, AbsExpiryT, BitfieldOffsetT, PatternT, AnyKeyT, FieldT, StreamIdT, TimeoutSecT, ZScoreBoundT, ConsumerT, ScriptTextT
from typing import Any, Mapping, Optional, Union, Iterable, Tuple, Iterator, Dict, Set, Literal, List, Awaitable, Callable, Sequence, AsyncIterator

# TYPE_CHECKING: bool
ReturnT: typing.TypeVar

class KVDBSession(abc.ABC):


    def __init__(
        self,
        name: str,
        url: Union[str, KVDBUrl],
        *,
        pool: SessionPools,
        db_id: Optional[int] = None,
        serializer: Optional[Union['SerializerT', str]] = None,
        encoder: Optional['Encoder'] = None,
        **kwargs: Any,
    ) -> None:
        """
        Initializes the KVDB Session
        """

    name: str
    url: KVDBUrl
    pool: SessionPools
    db_id: Optional[int]
    serializer: Optional[SerializerT]
    encoder: Optional[Encoder]
    state: SessionState
    _kwargs: Dict[str, Any]
    logger: Logger
    autologger: Logger
    settings: KVDBSettings
    version: str
    session_serialization_enabled: bool
    persistence: PersistentDict

    def init_serializer(self, serializer: Optional[Union['SerializerT', str]] = ..., **kwargs: Any) -> None:
        """
        Initializes the serializer
        """
    def init_encoder(self, encoder: Optional['Encoder'] = ..., **kwargs: Any) -> None:
        """
        Initializes the encoder
        """
    def init_cache_config(self, **kwargs: Any) -> None:
        """
        Initializes the cache config
        """
    def init_state(self, **kwargs: Any) -> None:
        """
        Initializes the session state
        """
    def pubsub(self, retryable: typing.Optional[bool] = ..., **kwargs) -> PubSubT:
        """
        Return a Publish/Subscribe object. With this object, you can
        subscribe to channels and listen for messages that get published to
        """
    def apubsub(self, retryable: typing.Optional[bool] = ..., **kwargs) -> AsyncPubSubT:
        """
        Return a Publish/Subscribe object. With this object, you can
        subscribe to channels and listen for messages that get published to
        """
    def pipeline(self, transaction: typing.Optional[bool] = ..., shard_hint: typing.Optional[str] = ..., retryable: typing.Optional[bool] = ..., **kwargs) -> PipelineT:
        """
        Return a new pipeline object that can queue multiple commands for
        later execution. ``transaction`` indicates whether all commands
        should be executed atomically. Apart from making a group of operations
        atomic, pipelines are useful for reducing the back-and-forth overhead
        between the client and server.
        """
    def apipeline(self, transaction: typing.Optional[bool] = ..., shard_hint: typing.Optional[str] = ..., retryable: typing.Optional[bool] = ..., **kwargs) -> AsyncPipelineT:
        """
        Return a new pipeline object that can queue multiple commands for
        later execution. ``transaction`` indicates whether all commands
        should be executed atomically. Apart from making a group of operations
        atomic, pipelines are useful for reducing the back-and-forth overhead
        between the client and server.
        """
    def lock(self, name: str, timeout: typing.Optional[Number] = ..., sleep: Optional[Number] = ..., blocking: Optional[bool] = ..., blocking_timeout: Optional[Number] = ..., thread_local: Optional[bool] = ..., **kwargs) -> Lock:
        """
        Create a new Lock instance named ``name`` using the Redis client
        supplied by ``keydb``.

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
        another thread. 
        """
    def alock(self, name: str, timeout: typing.Optional[Number] = ..., sleep: Number = ..., blocking: bool = ..., blocking_timeout: typing.Optional[Number] = ..., thread_local: bool = ..., **kwargs) -> AsyncLock:
        """
        Create a new Lock instance named ``name`` using the Redis client
        supplied by ``keydb``.

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
        another thread. 
        """
    def close_locks(self, names: typing.Optional[typing.Union[typing.List[str], str]] = ..., force: Optional[bool] = ..., raise_errors: Optional[bool] = ...):
        """
        Closes the locks that are currently managed by the session
        """
    async def aclose_locks(self, names: typing.Optional[typing.Union[typing.List[str], str]] = ..., force: Optional[bool] = ..., raise_errors: Optional[bool] = ...):
        """
        Closes the locks that are currently managed by the session
        """
    def get_dictkey(self, key: KeyT) -> str:
        """
        Returns the dict key
        """
    def getitem(self, key: KeyT, default: Optional[Any] = ...) -> ReturnT:
        """
        [Dict] Returns the value for the given key
        """
    async def agetitem(self, key: KeyT, default: Optional[Any] = ...) -> ReturnT:
        """
        [Dict] Returns the value for the given key
        """
    def setitem(self, key: KeyT, value: Any, ex: Optional[ExpiryT] = ..., **kwargs: Any) -> None:
        """
        [Dict] Sets the value for the given key
        """
    async def asetitem(self, key: KeyT, value: Any, ex: Optional[ExpiryT] = ..., **kwargs: Any) -> None:
        """
        [Dict] Sets the value for the given key
        """
    def delitem(self, key: KeyT) -> None:
        """
        [Dict] Deletes the key
        """
    async def adelitem(self, key: KeyT) -> None:
        """
        [Dict] Deletes the key
        """
    def close(self, close_pool: bool = ..., force: Optional[bool] = ..., raise_errors: bool = ...):
        """
        Close the session
        """
    def aclose(self, close_pool: bool = ..., force: Optional[bool] = ..., raise_errors: bool = ...):
        """
        Close the session
        """
    def __enter__(self):
        """
        Enter the runtime context related to this object.
        """
    def __exit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: types.TracebackType | None):
        """
        On exit, close the session
        """
    async def __aenter__(self):
        """
        Enter the runtime context related to this object.
        """
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Close the session
        """
    def __setitem__(self, key: KeyT, value: Any) -> None:
        """
        [Dict] Sets the value for the given key
        """
    def __getitem__(self, key: KeyT) -> ReturnT:
        """
        [Dict] Returns the value for the given key
        """
    def __delitem__(self, key: KeyT) -> None:
        """
        [Dict] Deletes the key
        """
    def __contains__(self, key: KeyT) -> bool:
        """
        [Dict] Returns whether the key exists
        """
    @property
    def client(self) -> KVDB:
        """
        Returns the KVDB client
        """
    
    @property
    def aclient(self) -> AsyncKVDB:
        """
        Returns the KVDB client
        """

    """
    ACL Commands
    """

    async def aacl_cat(self, category: Union[str, None] = None, **kwargs) -> ResponseT:
        """
        Returns a list of categories or commands within a category.

        If ``category`` is not supplied, returns a list of all categories.
        If ``category`` is supplied, returns a list of all commands within
        that category.

        For more information see https://redis.io/commands/acl-cat
        """
    async def aacl_dryrun(self, username, *args, **kwargs):
        """
        Simulate the execution of a given command by a given ``username``.

        For more information see https://redis.io/commands/acl-dryrun
        """
    async def aacl_deluser(self, *username: str, **kwargs) -> ResponseT:
        """
        Delete the ACL for the specified ``username``s

        For more information see https://redis.io/commands/acl-deluser
        """
    async def aacl_genpass(self, bits: Union[int, None] = None, **kwargs) -> ResponseT:
        """Generate a random password value.
        If ``bits`` is supplied then use this number of bits, rounded to
        the next multiple of 4.
        See: https://redis.io/commands/acl-genpass
        """
    async def aacl_getuser(self, username: str, **kwargs) -> ResponseT:
        """
        Get the ACL details for the specified ``username``.

        If ``username`` does not exist, return None

        For more information see https://redis.io/commands/acl-getuser
        """
    async def aacl_help(self, **kwargs) -> ResponseT:
        """The ACL HELP command returns helpful text describing
        the different subcommands.

        For more information see https://redis.io/commands/acl-help
        """
    async def aacl_list(self, **kwargs) -> ResponseT:
        """
        Return a list of all ACLs on the server

        For more information see https://redis.io/commands/acl-list
        """
    async def aacl_log(self, count: Union[int, None] = None, **kwargs) -> ResponseT:
        """
        Get ACL logs as a list.
        :param int count: Get logs[0:count].
        :rtype: List.

        For more information see https://redis.io/commands/acl-log
        """
    async def aacl_log_reset(self, **kwargs) -> ResponseT:
        """
        Reset ACL logs.
        :rtype: Boolean.

        For more information see https://redis.io/commands/acl-log
        """
    async def aacl_load(self, **kwargs) -> ResponseT:
        """
        Load ACL rules from the configured ``aclfile``.

        Note that the server must be configured with the ``aclfile``
        directive to be able to load ACL rules from an aclfile.

        For more information see https://redis.io/commands/acl-load
        """
    async def aacl_save(self, **kwargs) -> ResponseT:
        """
        Save ACL rules to the configured ``aclfile``.

        Note that the server must be configured with the ``aclfile``
        directive to be able to save ACL rules to an aclfile.

        For more information see https://redis.io/commands/acl-save
        """
    async def aacl_setuser(self, username: str, enabled: bool = False, nopass: bool = False, passwords: Union[str, Iterable[str], None] = None, hashed_passwords: Union[str, Iterable[str], None] = None, categories: Optional[Iterable[str]] = None, commands: Optional[Iterable[str]] = None, keys: Optional[Iterable[KeyT]] = None, channels: Optional[Iterable[ChannelT]] = None, selectors: Optional[Iterable[Tuple[str, KeyT]]] = None, reset: bool = False, reset_keys: bool = False, reset_channels: bool = False, reset_passwords: bool = False, **kwargs) -> ResponseT:
        """
        Create or update an ACL user.

        Create or update the ACL for ``username``. If the user already exists,
        the existing ACL is completely overwritten and replaced with the
        specified values.

        ``enabled`` is a boolean indicating whether the user should be allowed
        to authenticate or not. Defaults to ``False``.

        ``nopass`` is a boolean indicating whether the can authenticate without
        a password. This cannot be True if ``passwords`` are also specified.

        ``passwords`` if specified is a list of plain text passwords
        to add to or remove from the user. Each password must be prefixed with
        a '+' to add or a '-' to remove. For convenience, the value of
        ``passwords`` can be a simple prefixed string when adding or
        removing a single password.

        ``hashed_passwords`` if specified is a list of SHA-256 hashed passwords
        to add to or remove from the user. Each hashed password must be
        prefixed with a '+' to add or a '-' to remove. For convenience,
        the value of ``hashed_passwords`` can be a simple prefixed string when
        adding or removing a single password.

        ``categories`` if specified is a list of strings representing category
        permissions. Each string must be prefixed with either a '+' to add the
        category permission or a '-' to remove the category permission.

        ``commands`` if specified is a list of strings representing command
        permissions. Each string must be prefixed with either a '+' to add the
        command permission or a '-' to remove the command permission.

        ``keys`` if specified is a list of key patterns to grant the user
        access to. Keys patterns allow '*' to support wildcard matching. For
        example, '*' grants access to all keys while 'cache:*' grants access
        to all keys that are prefixed with 'cache:'. ``keys`` should not be
        prefixed with a '~'.

        ``reset`` is a boolean indicating whether the user should be fully
        reset prior to applying the new ACL. Setting this to True will
        remove all existing passwords, flags and privileges from the user and
        then apply the specified rules. If this is False, the user's existing
        passwords, flags and privileges will be kept and any new specified
        rules will be applied on top.

        ``reset_keys`` is a boolean indicating whether the user's key
        permissions should be reset prior to applying any new key permissions
        specified in ``keys``. If this is False, the user's existing
        key permissions will be kept and any new specified key permissions
        will be applied on top.

        ``reset_channels`` is a boolean indicating whether the user's channel
        permissions should be reset prior to applying any new channel permissions
        specified in ``channels``.If this is False, the user's existing
        channel permissions will be kept and any new specified channel permissions
        will be applied on top.

        ``reset_passwords`` is a boolean indicating whether to remove all
        existing passwords and the 'nopass' flag from the user prior to
        applying any new passwords specified in 'passwords' or
        'hashed_passwords'. If this is False, the user's existing passwords
        and 'nopass' status will be kept and any new specified passwords
        or hashed_passwords will be applied on top.

        For more information see https://redis.io/commands/acl-setuser
        """
    async def aacl_users(self, **kwargs) -> ResponseT:
        """Returns a list of all registered users on the server.

        For more information see https://redis.io/commands/acl-users
        """
    async def aacl_whoami(self, **kwargs) -> ResponseT:
        """Get the username for the current connection

        For more information see https://redis.io/commands/acl-whoami
        """

    """
    Redis management commands
    """
    async def aauth(self, password: str, username: Optional[str] = None, **kwargs):
        '''
        Authenticates the user. If you do not pass username, Redis will try to
        authenticate for the "default" user. If you do pass username, it will
        authenticate for the given user.
        For more information see https://redis.io/commands/auth
        '''
    async def abgrewriteaof(self, **kwargs):
        """Tell the Redis server to rewrite the AOF file from data in memory.

        For more information see https://redis.io/commands/bgrewriteaof
        """
    async def abgsave(self, schedule: bool = True, **kwargs) -> ResponseT:
        """
        Tell the Redis server to save its data to disk.  Unlike save(),
        this method is asynchronous and returns immediately.

        For more information see https://redis.io/commands/bgsave
        """
    async def arole(self) -> ResponseT:
        """
        Provide information on the role of a Redis instance in
        the context of replication, by returning if the instance
        is currently a master, slave, or sentinel.

        For more information see https://redis.io/commands/role
        """
    async def aclient_kill(self, address: str, **kwargs) -> ResponseT:
        """Disconnects the client at ``address`` (ip:port)

        For more information see https://redis.io/commands/client-kill
        """
    async def aclient_kill_filter(self, _id: Union[str, None] = None, _type: Union[str, None] = None, addr: Union[str, None] = None, skipme: Union[bool, None] = None, laddr: Union[bool, None] = None, user: str = None, **kwargs) -> ResponseT:
        """
        Disconnects client(s) using a variety of filter options
        :param _id: Kills a client by its unique ID field
        :param _type: Kills a client by type where type is one of 'normal',
        'master', 'slave' or 'pubsub'
        :param addr: Kills a client by its 'address:port'
        :param skipme: If True, then the client calling the command
        will not get killed even if it is identified by one of the filter
        options. If skipme is not provided, the server defaults to skipme=True
        :param laddr: Kills a client by its 'local (bind) address:port'
        :param user: Kills a client for a specific user name
        """
    async def aclient_info(self, **kwargs) -> ResponseT:
        """
        Returns information and statistics about the current
        client connection.

        For more information see https://redis.io/commands/client-info
        """
    async def aclient_list(self, _type: Union[str, None] = None, client_id: List[EncodableT] = [], **kwargs) -> ResponseT:
        """
        Returns a list of currently connected clients.
        If type of client specified, only that type will be returned.

        :param _type: optional. one of the client types (normal, master,
         replica, pubsub)
        :param client_id: optional. a list of client ids

        For more information see https://redis.io/commands/client-list
        """
    async def aclient_getname(self, **kwargs) -> ResponseT:
        """
        Returns the current connection name

        For more information see https://redis.io/commands/client-getname
        """
    async def aclient_getredir(self, **kwargs) -> ResponseT:
        """
        Returns the ID (an integer) of the client to whom we are
        redirecting tracking notifications.

        see: https://redis.io/commands/client-getredir
        """
    async def aclient_reply(self, reply: Union[Literal['ON'], Literal['OFF'], Literal['SKIP']], **kwargs) -> ResponseT:
        """
        Enable and disable redis server replies.

        ``reply`` Must be ON OFF or SKIP,
        ON - The default most with server replies to commands
        OFF - Disable server responses to commands
        SKIP - Skip the response of the immediately following command.

        Note: When setting OFF or SKIP replies, you will need a client object
        with a timeout specified in seconds, and will need to catch the
        TimeoutError.
        The test_client_reply unit test illustrates this, and
        conftest.py has a client with a timeout.

        See https://redis.io/commands/client-reply
        """
    async def aclient_id(self, **kwargs) -> ResponseT:
        """
        Returns the current connection id

        For more information see https://redis.io/commands/client-id
        """
    async def aclient_tracking_on(self, clientid: Union[int, None] = None, prefix: Sequence[KeyT] = [], bcast: bool = False, optin: bool = False, optout: bool = False, noloop: bool = False) -> ResponseT:
        """
        Turn on the tracking mode.
        For more information about the options look at client_tracking func.

        See https://redis.io/commands/client-tracking
        """
    async def aclient_tracking_off(self, clientid: Union[int, None] = None, prefix: Sequence[KeyT] = [], bcast: bool = False, optin: bool = False, optout: bool = False, noloop: bool = False) -> ResponseT:
        """
        Turn off the tracking mode.
        For more information about the options look at client_tracking func.

        See https://redis.io/commands/client-tracking
        """
    async def aclient_tracking(self, on: bool = True, clientid: Union[int, None] = None, prefix: Sequence[KeyT] = [], bcast: bool = False, optin: bool = False, optout: bool = False, noloop: bool = False, **kwargs) -> ResponseT:
        """
        Enables the tracking feature of the Redis server, that is used
        for server assisted client side caching.

        ``on`` indicate for tracking on or tracking off. The dafualt is on.

        ``clientid`` send invalidation messages to the connection with
        the specified ID.

        ``bcast`` enable tracking in broadcasting mode. In this mode
        invalidation messages are reported for all the prefixes
        specified, regardless of the keys requested by the connection.

        ``optin``  when broadcasting is NOT active, normally don't track
        keys in read only commands, unless they are called immediately
        after a CLIENT CACHING yes command.

        ``optout`` when broadcasting is NOT active, normally track keys in
        read only commands, unless they are called immediately after a
        CLIENT CACHING no command.

        ``noloop`` don't send notifications about keys modified by this
        connection itself.

        ``prefix``  for broadcasting, register a given key prefix, so that
        notifications will be provided only for keys starting with this string.

        See https://redis.io/commands/client-tracking
        """
    async def aclient_trackinginfo(self, **kwargs) -> ResponseT:
        """
        Returns the information about the current client connection's
        use of the server assisted client side cache.

        See https://redis.io/commands/client-trackinginfo
        """
    async def aclient_setname(self, name: str, **kwargs) -> ResponseT:
        """
        Sets the current connection name

        For more information see https://redis.io/commands/client-setname

        .. note::
           This method sets client name only for **current** connection.

           If you want to set a common name for all connections managed
           by this client, use ``client_name`` constructor argument.
        """
    async def aclient_setinfo(self, attr: str, value: str, **kwargs) -> ResponseT:
        """
        Sets the current connection library name or version
        For mor information see https://redis.io/commands/client-setinfo
        """
    async def aclient_unblock(self, client_id: int, error: bool = False, **kwargs) -> ResponseT:
        """
        Unblocks a connection by its client id.
        If ``error`` is True, unblocks the client with a special error message.
        If ``error`` is False (default), the client is unblocked using the
        regular timeout mechanism.

        For more information see https://redis.io/commands/client-unblock
        """
    async def aclient_pause(self, timeout: int, all: bool = True, **kwargs) -> ResponseT:
        """
        Suspend all the Redis clients for the specified amount of time.


        For more information see https://redis.io/commands/client-pause

        :param timeout: milliseconds to pause clients
        :param all: If true (default) all client commands are blocked.
        otherwise, clients are only blocked if they attempt to execute
        a write command.
        For the WRITE mode, some commands have special behavior:
        EVAL/EVALSHA: Will block client for all scripts.
        PUBLISH: Will block client.
        PFCOUNT: Will block client.
        WAIT: Acknowledgments will be delayed, so this command will
        appear blocked.
        """
    async def aclient_unpause(self, **kwargs) -> ResponseT:
        """
        Unpause all redis clients

        For more information see https://redis.io/commands/client-unpause
        """
    async def aclient_no_evict(self, mode: str) -> Union[Awaitable[str], str]:
        """
        Sets the client eviction mode for the current connection.

        For more information see https://redis.io/commands/client-no-evict
        """
    async def aclient_no_touch(self, mode: str) -> Union[Awaitable[str], str]:
        """
        # The command controls whether commands sent by the client will alter
        # the LRU/LFU of the keys they access.
        # When turned on, the current client will not change LFU/LRU stats,
        # unless it sends the TOUCH command.

        For more information see https://redis.io/commands/client-no-touch
        """
    async def acommand(self, **kwargs):
        """
        Returns dict reply of details about all Redis commands.

        For more information see https://redis.io/commands/command
        """
    async def acommand_info(self, **kwargs) -> None: ...
    async def acommand_count(self, **kwargs) -> ResponseT: ...
    async def acommand_list(self, module: Optional[str] = None, category: Optional[str] = None, pattern: Optional[str] = None) -> ResponseT:
        """
        Return an array of the server's command names.
        You can use one of the following filters:
        ``module``: get the commands that belong to the module
        ``category``: get the commands in the ACL category
        ``pattern``: get the commands that match the given pattern

        For more information see https://redis.io/commands/command-list/
        """
    async def acommand_getkeysandflags(self, *args: List[str]) -> List[Union[str, List[str]]]:
        """
        Returns array of keys from a full Redis command and their usage flags.

        For more information see https://redis.io/commands/command-getkeysandflags
        """
    async def acommand_docs(self, *args) -> None:
        """
        This function throws a NotImplementedError since it is intentionally
        not supported.
        """
    async def aconfig_get(self, pattern: PatternT = '*', *args: List[PatternT], **kwargs) -> ResponseT:
        """
        Return a dictionary of configuration based on the ``pattern``

        For more information see https://redis.io/commands/config-get
        """
    async def aconfig_set(self, name: KeyT, value: EncodableT, *args: List[Union[KeyT, EncodableT]], **kwargs) -> ResponseT:
        """Set config item ``name`` with ``value``

        For more information see https://redis.io/commands/config-set
        """
    async def aconfig_resetstat(self, **kwargs) -> ResponseT:
        """
        Reset runtime statistics

        For more information see https://redis.io/commands/config-resetstat
        """
    async def aconfig_rewrite(self, **kwargs) -> ResponseT:
        """
        Rewrite config file with the minimal change to reflect running config.

        For more information see https://redis.io/commands/config-rewrite
        """
    async def adbsize(self, **kwargs) -> ResponseT:
        """
        Returns the number of keys in the current database

        For more information see https://redis.io/commands/dbsize
        """
    async def adebug_object(self, key: KeyT, **kwargs) -> ResponseT:
        """
        Returns version specific meta information about a given key

        For more information see https://redis.io/commands/debug-object
        """
    async def adebug_segfault(self, **kwargs) -> None: ...
    async def aecho(self, value: EncodableT, **kwargs) -> ResponseT:
        """
        Echo the string back from the server

        For more information see https://redis.io/commands/echo
        """
    async def aflushall(self, asynchronous: bool = False, **kwargs) -> ResponseT:
        """
        Delete all keys in all databases on the current host.

        ``asynchronous`` indicates whether the operation is
        executed asynchronously by the server.

        For more information see https://redis.io/commands/flushall
        """
    async def aflushdb(self, asynchronous: bool = False, **kwargs) -> ResponseT:
        """
        Delete all keys in the current database.

        ``asynchronous`` indicates whether the operation is
        executed asynchronously by the server.

        For more information see https://redis.io/commands/flushdb
        """
    async def async_(self) -> ResponseT:
        """
        Initiates a replication stream from the master.

        For more information see https://redis.io/commands/sync
        """
    async def apsync(self, replicationid: str, offset: int):
        """
        Initiates a replication stream from the master.
        Newer version for `sync`.

        For more information see https://redis.io/commands/sync
        """
    async def aswapdb(self, first: int, second: int, **kwargs) -> ResponseT:
        """
        Swap two databases

        For more information see https://redis.io/commands/swapdb
        """
    async def aselect(self, index: int, **kwargs) -> ResponseT:
        """Select the Redis logical database at index.

        See: https://redis.io/commands/select
        """
    async def ainfo(self, section: Union[str, None] = None, *args: List[str], **kwargs) -> ResponseT:
        """
        Returns a dictionary containing information about the Redis server

        The ``section`` option can be used to select a specific section
        of information

        The section option is not supported by older versions of Redis Server,
        and will generate ResponseError

        For more information see https://redis.io/commands/info
        """
    async def alastsave(self, **kwargs) -> ResponseT:
        """
        Return a Python datetime object representing the last time the
        Redis database was saved to disk

        For more information see https://redis.io/commands/lastsave
        """
    async def alatency_doctor(self) -> None:
        """Raise a NotImplementedError, as the client will not support LATENCY DOCTOR.
        This funcion is best used within the redis-cli.

        For more information see https://redis.io/commands/latency-doctor
        """
    async def alatency_graph(self) -> None:
        """Raise a NotImplementedError, as the client will not support LATENCY GRAPH.
        This funcion is best used within the redis-cli.

        For more information see https://redis.io/commands/latency-graph.
        """
    async def alolwut(self, *version_numbers: Union[str, float], **kwargs) -> ResponseT:
        """
        Get the Redis version and a piece of generative computer art

        See: https://redis.io/commands/lolwut
        """
    async def areset(self) -> ResponseT:
        """Perform a full reset on the connection's server side contenxt.

        See: https://redis.io/commands/reset
        """
    async def amigrate(self, host: str, port: int, keys: KeysT, destination_db: int, timeout: int, copy: bool = False, replace: bool = False, auth: Union[str, None] = None, **kwargs) -> ResponseT:
        """
        Migrate 1 or more keys from the current Redis server to a different
        server specified by the ``host``, ``port`` and ``destination_db``.

        The ``timeout``, specified in milliseconds, indicates the maximum
        time the connection between the two servers can be idle before the
        command is interrupted.

        If ``copy`` is True, the specified ``keys`` are NOT deleted from
        the source server.

        If ``replace`` is True, this operation will overwrite the keys
        on the destination server if they exist.

        If ``auth`` is specified, authenticate to the destination server with
        the password provided.

        For more information see https://redis.io/commands/migrate
        """
    async def aobject(self, infotype: str, key: KeyT, **kwargs) -> ResponseT:
        """
        Return the encoding, idletime, or refcount about the key
        """
    async def amemory_doctor(self, **kwargs) -> None: ...
    async def amemory_help(self, **kwargs) -> None: ...
    async def amemory_stats(self, **kwargs) -> ResponseT:
        """
        Return a dictionary of memory stats

        For more information see https://redis.io/commands/memory-stats
        """
    async def amemory_malloc_stats(self, **kwargs) -> ResponseT:
        """
        Return an internal statistics report from the memory allocator.

        See: https://redis.io/commands/memory-malloc-stats
        """
    async def amemory_usage(self, key: KeyT, samples: Union[int, None] = None, **kwargs) -> ResponseT:
        """
        Return the total memory usage for key, its value and associated
        administrative overheads.

        For nested data structures, ``samples`` is the number of elements to
        sample. If left unspecified, the server's default is 5. Use 0 to sample
        all elements.

        For more information see https://redis.io/commands/memory-usage
        """
    async def amemory_purge(self, **kwargs) -> ResponseT:
        """
        Attempts to purge dirty pages for reclamation by allocator

        For more information see https://redis.io/commands/memory-purge
        """
    async def alatency_histogram(self, *args) -> None:
        """
        This function throws a NotImplementedError since it is intentionally
        not supported.
        """
    async def alatency_history(self, event: str) -> ResponseT:
        """
        Returns the raw data of the ``event``'s latency spikes time series.

        For more information see https://redis.io/commands/latency-history
        """
    async def alatency_latest(self) -> ResponseT:
        """
        Reports the latest latency events logged.

        For more information see https://redis.io/commands/latency-latest
        """
    async def alatency_reset(self, *events: str) -> ResponseT:
        """
        Resets the latency spikes time series of all, or only some, events.

        For more information see https://redis.io/commands/latency-reset
        """
    async def aping(self, **kwargs) -> ResponseT:
        """
        Ping the Redis server

        For more information see https://redis.io/commands/ping
        """
    async def aquit(self, **kwargs) -> ResponseT:
        """
        Ask the server to close the connection.

        For more information see https://redis.io/commands/quit
        """
    async def areplicaof(self, *args, **kwargs) -> ResponseT:
        """
        Update the replication settings of a redis replica, on the fly.

        Examples of valid arguments include:

        NO ONE (set no replication)
        host port (set to the host and port of a redis server)

        For more information see  https://redis.io/commands/replicaof
        """
    async def asave(self, **kwargs) -> ResponseT:
        """
        Tell the Redis server to save its data to disk,
        blocking until the save is complete

        For more information see https://redis.io/commands/save
        """
    async def ashutdown(self, save: bool = False, nosave: bool = False, now: bool = False, force: bool = False, abort: bool = False, **kwargs) -> None:
        """Shutdown the Redis server.  If Redis has persistence configured,
        data will be flushed before shutdown.
        It is possible to specify modifiers to alter the behavior of the command:
        ``save`` will force a DB saving operation even if no save points are configured.
        ``nosave`` will prevent a DB saving operation even if one or more save points
        are configured.
        ``now`` skips waiting for lagging replicas, i.e. it bypasses the first step in
        the shutdown sequence.
        ``force`` ignores any errors that would normally prevent the server from exiting
        ``abort`` cancels an ongoing shutdown and cannot be combined with other flags.

        For more information see https://redis.io/commands/shutdown
        """
    async def aslaveof(self, host: Union[str, None] = None, port: Union[int, None] = None, **kwargs) -> ResponseT:
        """
        Set the server to be a replicated slave of the instance identified
        by the ``host`` and ``port``. If called without arguments, the
        instance is promoted to a master instead.

        For more information see https://redis.io/commands/slaveof
        """
    async def aslowlog_get(self, num: Union[int, None] = None, **kwargs) -> ResponseT:
        """
        Get the entries from the slowlog. If ``num`` is specified, get the
        most recent ``num`` items.

        For more information see https://redis.io/commands/slowlog-get
        """
    async def aslowlog_len(self, **kwargs) -> ResponseT:
        """
        Get the number of items in the slowlog

        For more information see https://redis.io/commands/slowlog-len
        """
    async def aslowlog_reset(self, **kwargs) -> ResponseT:
        """
        Remove all items in the slowlog

        For more information see https://redis.io/commands/slowlog-reset
        """
    async def atime(self, **kwargs) -> ResponseT:
        """
        Returns the server time as a 2-item tuple of ints:
        (seconds since epoch, microseconds into this second).

        For more information see https://redis.io/commands/time
        """
    async def await_(self, num_replicas: int, timeout: int, **kwargs) -> ResponseT:
        """
        Redis synchronous replication
        That returns the number of replicas that processed the query when
        we finally have at least ``num_replicas``, or when the ``timeout`` was
        reached.

        For more information see https://redis.io/commands/wait
        """
    async def awaitaof(self, num_local: int, num_replicas: int, timeout: int, **kwargs) -> ResponseT:
        """
        This command blocks the current client until all previous write
        commands by that client are acknowledged as having been fsynced
        to the AOF of the local Redis and/or at least the specified number
        of replicas.

        For more information see https://redis.io/commands/waitaof
        """
    async def ahello(self) -> None:
        """
        This function throws a NotImplementedError since it is intentionally
        not supported.
        """
    async def afailover(self) -> None:
        """
        This function throws a NotImplementedError since it is intentionally
        not supported.
        """
    async def areset(self) -> None:
        """
        Reset the state of the instance to when it was constructed
        """
    async def aoverflow(self, overflow: str):
        """
        Update the overflow algorithm of successive INCRBY operations
        :param overflow: Overflow algorithm, one of WRAP, SAT, FAIL. See the
            Redis docs for descriptions of these algorithmsself.
        :returns: a :py:class:`BitFieldOperation` instance.
        """
    async def aincrby(self, fmt: str, offset: BitfieldOffsetT, increment: int, overflow: Union[str, None] = None):
        """
        Increment a bitfield by a given amount.
        :param fmt: format-string for the bitfield being updated, e.g. 'u8'
            for an unsigned 8-bit integer.
        :param offset: offset (in number of bits). If prefixed with a
            '#', this is an offset multiplier, e.g. given the arguments
            fmt='u8', offset='#2', the offset will be 16.
        :param int increment: value to increment the bitfield by.
        :param str overflow: overflow algorithm. Defaults to WRAP, but other
            acceptable values are SAT and FAIL. See the Redis docs for
            descriptions of these algorithms.
        :returns: a :py:class:`BitFieldOperation` instance.
        """
    async def aget(self, fmt: str, offset: BitfieldOffsetT):
        """
        Get the value of a given bitfield.
        :param fmt: format-string for the bitfield being read, e.g. 'u8' for
            an unsigned 8-bit integer.
        :param offset: offset (in number of bits). If prefixed with a
            '#', this is an offset multiplier, e.g. given the arguments
            fmt='u8', offset='#2', the offset will be 16.
        :returns: a :py:class:`BitFieldOperation` instance.
        """
    async def aset(self, fmt: str, offset: BitfieldOffsetT, value: int):
        """
        Set the value of a given bitfield.
        :param fmt: format-string for the bitfield being read, e.g. 'u8' for
            an unsigned 8-bit integer.
        :param offset: offset (in number of bits). If prefixed with a
            '#', this is an offset multiplier, e.g. given the arguments
            fmt='u8', offset='#2', the offset will be 16.
        :param int value: value to set at the given position.
        :returns: a :py:class:`BitFieldOperation` instance.
        """
    

    """
    Redis basic key-based commands
    """
    async def aappend(self, key: KeyT, value: EncodableT) -> ResponseT:
        """
        Appends the string ``value`` to the value at ``key``. If ``key``
        doesn't already exist, create it with a value of ``value``.
        Returns the new length of the value at ``key``.

        For more information see https://redis.io/commands/append
        """
    async def abitcount(self, key: KeyT, start: Union[int, None] = None, end: Union[int, None] = None, mode: Optional[str] = None) -> ResponseT:
        """
        Returns the count of set bits in the value of ``key``.  Optional
        ``start`` and ``end`` parameters indicate which bytes to consider

        For more information see https://redis.io/commands/bitcount
        """
    async def abitfield(self, key: KeyT, default_overflow: Union[str, None] = None) -> BitFieldOperation:
        """
        Return a BitFieldOperation instance to conveniently construct one or
        more bitfield operations on ``key``.

        For more information see https://redis.io/commands/bitfield
        """
    async def abitfield_ro(self, key: KeyT, encoding: str, offset: BitfieldOffsetT, items: Optional[list] = None) -> ResponseT:
        """
        Return an array of the specified bitfield values
        where the first value is found using ``encoding`` and ``offset``
        parameters and remaining values are result of corresponding
        encoding/offset pairs in optional list ``items``
        Read-only variant of the BITFIELD command.

        For more information see https://redis.io/commands/bitfield_ro
        """
    async def abitop(self, operation: str, dest: KeyT, *keys: KeyT) -> ResponseT:
        """
        Perform a bitwise operation using ``operation`` between ``keys`` and
        store the result in ``dest``.

        For more information see https://redis.io/commands/bitop
        """
    async def abitpos(self, key: KeyT, bit: int, start: Union[int, None] = None, end: Union[int, None] = None, mode: Optional[str] = None) -> ResponseT:
        """
        Return the position of the first bit set to 1 or 0 in a string.
        ``start`` and ``end`` defines search range. The range is interpreted
        as a range of bytes and not a range of bits, so start=0 and end=2
        means to look at the first three bytes.

        For more information see https://redis.io/commands/bitpos
        """
    async def acopy(self, source: str, destination: str, destination_db: Union[str, None] = None, replace: bool = False) -> ResponseT:
        """
        Copy the value stored in the ``source`` key to the ``destination`` key.

        ``destination_db`` an alternative destination database. By default,
        the ``destination`` key is created in the source Redis database.

        ``replace`` whether the ``destination`` key should be removed before
        copying the value to it. By default, the value is not copied if
        the ``destination`` key already exists.

        For more information see https://redis.io/commands/copy
        """
    async def adecrby(self, name: KeyT, amount: int = 1) -> ResponseT:
        """
        Decrements the value of ``key`` by ``amount``.  If no key exists,
        the value will be initialized as 0 - ``amount``

        For more information see https://redis.io/commands/decrby
        """
    adecr = adecrby
    async def adelete(self, *names: KeyT) -> ResponseT:
        """
        Delete one or more keys specified by ``names``
        """

    async def adump(self, name: KeyT) -> ResponseT:
        """
        Return a serialized version of the value stored at the specified key.
        If key does not exist a nil bulk reply is returned.

        For more information see https://redis.io/commands/dump
        """
    async def aexists(self, *names: KeyT) -> ResponseT:
        """
        Returns the number of ``names`` that exist

        For more information see https://redis.io/commands/exists
        """

    async def aexpire(self, name: KeyT, time: ExpiryT, nx: bool = False, xx: bool = False, gt: bool = False, lt: bool = False) -> ResponseT:
        """
        Set an expire flag on key ``name`` for ``time`` seconds with given
        ``option``. ``time`` can be represented by an integer or a Python timedelta
        object.

        Valid options are:
            NX -> Set expiry only when the key has no expiry
            XX -> Set expiry only when the key has an existing expiry
            GT -> Set expiry only when the new expiry is greater than current one
            LT -> Set expiry only when the new expiry is less than current one

        For more information see https://redis.io/commands/expire
        """
    async def aexpireat(self, name: KeyT, when: AbsExpiryT, nx: bool = False, xx: bool = False, gt: bool = False, lt: bool = False) -> ResponseT:
        """
        Set an expire flag on key ``name`` with given ``option``. ``when``
        can be represented as an integer indicating unix time or a Python
        datetime object.

        Valid options are:
            -> NX -- Set expiry only when the key has no expiry
            -> XX -- Set expiry only when the key has an existing expiry
            -> GT -- Set expiry only when the new expiry is greater than current one
            -> LT -- Set expiry only when the new expiry is less than current one

        For more information see https://redis.io/commands/expireat
        """
    async def aexpiretime(self, key: str) -> int:
        """
        Returns the absolute Unix timestamp (since January 1, 1970) in seconds
        at which the given key will expire.

        For more information see https://redis.io/commands/expiretime
        """
    async def aget(self, name: KeyT) -> ResponseT:
        """
        Return the value at key ``name``, or None if the key doesn't exist

        For more information see https://redis.io/commands/get
        """
    async def agetdel(self, name: KeyT) -> ResponseT:
        """
        Get the value at key ``name`` and delete the key. This command
        is similar to GET, except for the fact that it also deletes
        the key on success (if and only if the key's value type
        is a string).

        For more information see https://redis.io/commands/getdel
        """
    async def agetex(self, name: KeyT, ex: Union[ExpiryT, None] = None, px: Union[ExpiryT, None] = None, exat: Union[AbsExpiryT, None] = None, pxat: Union[AbsExpiryT, None] = None, persist: bool = False) -> ResponseT:
        """
        Get the value of key and optionally set its expiration.
        GETEX is similar to GET, but is a write command with
        additional options. All time parameters can be given as
        datetime.timedelta or integers.

        ``ex`` sets an expire flag on key ``name`` for ``ex`` seconds.

        ``px`` sets an expire flag on key ``name`` for ``px`` milliseconds.

        ``exat`` sets an expire flag on key ``name`` for ``ex`` seconds,
        specified in unix time.

        ``pxat`` sets an expire flag on key ``name`` for ``ex`` milliseconds,
        specified in unix time.

        ``persist`` remove the time to live associated with ``name``.

        For more information see https://redis.io/commands/getex
        """
   
    async def agetbit(self, name: KeyT, offset: int) -> ResponseT:
        """
        Returns an integer indicating the value of ``offset`` in ``name``

        For more information see https://redis.io/commands/getbit
        """
    async def agetrange(self, key: KeyT, start: int, end: int) -> ResponseT:
        """
        Returns the substring of the string value stored at ``key``,
        determined by the offsets ``start`` and ``end`` (both are inclusive)

        For more information see https://redis.io/commands/getrange
        """
    async def agetset(self, name: KeyT, value: EncodableT) -> ResponseT:
        """
        Sets the value at key ``name`` to ``value``
        and returns the old value at key ``name`` atomically.

        As per Redis 6.2, GETSET is considered deprecated.
        Please use SET with GET parameter in new code.

        For more information see https://redis.io/commands/getset
        """
    async def aincrby(self, name: KeyT, amount: int = 1) -> ResponseT:
        """
        Increments the value of ``key`` by ``amount``.  If no key exists,
        the value will be initialized as ``amount``

        For more information see https://redis.io/commands/incrby
        """
    incr = incrby
    async def aincrbyfloat(self, name: KeyT, amount: float = 1.0) -> ResponseT:
        """
        Increments the value at key ``name`` by floating ``amount``.
        If no key exists, the value will be initialized as ``amount``

        For more information see https://redis.io/commands/incrbyfloat
        """
    async def akeys(self, pattern: PatternT = '*', **kwargs) -> ResponseT:
        """
        Returns a list of keys matching ``pattern``

        For more information see https://redis.io/commands/keys
        """
    async def almove(self, first_list: str, second_list: str, src: str = 'LEFT', dest: str = 'RIGHT') -> ResponseT:
        """
        Atomically returns and removes the first/last element of a list,
        pushing it as the first/last element on the destination list.
        Returns the element being popped and pushed.

        For more information see https://redis.io/commands/lmove
        """
    async def ablmove(self, first_list: str, second_list: str, timeout: int, src: str = 'LEFT', dest: str = 'RIGHT') -> ResponseT:
        """
        Blocking version of lmove.

        For more information see https://redis.io/commands/blmove
        """
    async def amget(self, keys: KeysT, *args: EncodableT) -> ResponseT:
        """
        Returns a list of values ordered identically to ``keys``

        For more information see https://redis.io/commands/mget
        """
    async def amset(self, mapping: Mapping[AnyKeyT, EncodableT]) -> ResponseT:
        """
        Sets key/values based on a mapping. Mapping is a dictionary of
        key/value pairs. Both keys and values should be strings or types that
        can be cast to a string via str().

        For more information see https://redis.io/commands/mset
        """
    async def amsetnx(self, mapping: Mapping[AnyKeyT, EncodableT]) -> ResponseT:
        """
        Sets key/values based on a mapping if none of the keys are already set.
        Mapping is a dictionary of key/value pairs. Both keys and values
        should be strings or types that can be cast to a string via str().
        Returns a boolean indicating if the operation was successful.

        For more information see https://redis.io/commands/msetnx
        """
    async def amove(self, name: KeyT, db: int) -> ResponseT:
        """
        Moves the key ``name`` to a different Redis database ``db``

        For more information see https://redis.io/commands/move
        """
    async def apersist(self, name: KeyT) -> ResponseT:
        """
        Removes an expiration on ``name``

        For more information see https://redis.io/commands/persist
        """
    async def apexpire(self, name: KeyT, time: ExpiryT, nx: bool = False, xx: bool = False, gt: bool = False, lt: bool = False) -> ResponseT:
        """
        Set an expire flag on key ``name`` for ``time`` milliseconds
        with given ``option``. ``time`` can be represented by an
        integer or a Python timedelta object.

        Valid options are:
            NX -> Set expiry only when the key has no expiry
            XX -> Set expiry only when the key has an existing expiry
            GT -> Set expiry only when the new expiry is greater than current one
            LT -> Set expiry only when the new expiry is less than current one

        For more information see https://redis.io/commands/pexpire
        """
    async def apexpireat(self, name: KeyT, when: AbsExpiryT, nx: bool = False, xx: bool = False, gt: bool = False, lt: bool = False) -> ResponseT:
        """
        Set an expire flag on key ``name`` with given ``option``. ``when``
        can be represented as an integer representing unix time in
        milliseconds (unix time * 1000) or a Python datetime object.

        Valid options are:
            NX -> Set expiry only when the key has no expiry
            XX -> Set expiry only when the key has an existing expiry
            GT -> Set expiry only when the new expiry is greater than current one
            LT -> Set expiry only when the new expiry is less than current one

        For more information see https://redis.io/commands/pexpireat
        """
    async def apexpiretime(self, key: str) -> int:
        """
        Returns the absolute Unix timestamp (since January 1, 1970) in milliseconds
        at which the given key will expire.

        For more information see https://redis.io/commands/pexpiretime
        """
    async def apsetex(self, name: KeyT, time_ms: ExpiryT, value: EncodableT):
        """
        Set the value of key ``name`` to ``value`` that expires in ``time_ms``
        milliseconds. ``time_ms`` can be represented by an integer or a Python
        timedelta object

        For more information see https://redis.io/commands/psetex
        """
    async def apttl(self, name: KeyT) -> ResponseT:
        """
        Returns the number of milliseconds until the key ``name`` will expire

        For more information see https://redis.io/commands/pttl
        """
    async def ahrandfield(self, key: str, count: int = None, withvalues: bool = False) -> ResponseT:
        """
        Return a random field from the hash value stored at key.

        count: if the argument is positive, return an array of distinct fields.
        If called with a negative count, the behavior changes and the command
        is allowed to return the same field multiple times. In this case,
        the number of returned fields is the absolute value of the
        specified count.
        withvalues: The optional WITHVALUES modifier changes the reply so it
        includes the respective values of the randomly selected hash fields.

        For more information see https://redis.io/commands/hrandfield
        """
    async def arandomkey(self, **kwargs) -> ResponseT:
        """
        Returns the name of a random key

        For more information see https://redis.io/commands/randomkey
        """
    async def arename(self, src: KeyT, dst: KeyT) -> ResponseT:
        """
        Rename key ``src`` to ``dst``

        For more information see https://redis.io/commands/rename
        """
    async def arenamenx(self, src: KeyT, dst: KeyT):
        """
        Rename key ``src`` to ``dst`` if ``dst`` doesn't already exist

        For more information see https://redis.io/commands/renamenx
        """
    async def arestore(self, name: KeyT, ttl: float, value: EncodableT, replace: bool = False, absttl: bool = False, idletime: Union[int, None] = None, frequency: Union[int, None] = None) -> ResponseT:
        """
        Create a key using the provided serialized value, previously obtained
        using DUMP.

        ``replace`` allows an existing key on ``name`` to be overridden. If
        it's not specified an error is raised on collision.

        ``absttl`` if True, specified ``ttl`` should represent an absolute Unix
        timestamp in milliseconds in which the key will expire. (Redis 5.0 or
        greater).

        ``idletime`` Used for eviction, this is the number of seconds the
        key must be idle, prior to execution.

        ``frequency`` Used for eviction, this is the frequency counter of
        the object stored at the key, prior to execution.

        For more information see https://redis.io/commands/restore
        """
    async def aset(self, name: KeyT, value: EncodableT, ex: Union[ExpiryT, None] = None, px: Union[ExpiryT, None] = None, nx: bool = False, xx: bool = False, keepttl: bool = False, get: bool = False, exat: Union[AbsExpiryT, None] = None, pxat: Union[AbsExpiryT, None] = None) -> ResponseT:
        """
        Set the value at key ``name`` to ``value``

        ``ex`` sets an expire flag on key ``name`` for ``ex`` seconds.

        ``px`` sets an expire flag on key ``name`` for ``px`` milliseconds.

        ``nx`` if set to True, set the value at key ``name`` to ``value`` only
            if it does not exist.

        ``xx`` if set to True, set the value at key ``name`` to ``value`` only
            if it already exists.

        ``keepttl`` if True, retain the time to live associated with the key.
            (Available since Redis 6.0)

        ``get`` if True, set the value at key ``name`` to ``value`` and return
            the old value stored at key, or None if the key did not exist.
            (Available since Redis 6.2)

        ``exat`` sets an expire flag on key ``name`` for ``ex`` seconds,
            specified in unix time.

        ``pxat`` sets an expire flag on key ``name`` for ``ex`` milliseconds,
            specified in unix time.

        For more information see https://redis.io/commands/set
        """

    async def asetbit(self, name: KeyT, offset: int, value: int) -> ResponseT:
        """
        Flag the ``offset`` in ``name`` as ``value``. Returns an integer
        indicating the previous value of ``offset``.

        For more information see https://redis.io/commands/setbit
        """
    async def asetex(self, name: KeyT, time: ExpiryT, value: EncodableT) -> ResponseT:
        """
        Set the value of key ``name`` to ``value`` that expires in ``time``
        seconds. ``time`` can be represented by an integer or a Python
        timedelta object.

        For more information see https://redis.io/commands/setex
        """
    async def asetnx(self, name: KeyT, value: EncodableT) -> ResponseT:
        """
        Set the value of key ``name`` to ``value`` if key doesn't exist

        For more information see https://redis.io/commands/setnx
        """
    async def asetrange(self, name: KeyT, offset: int, value: EncodableT) -> ResponseT:
        """
        Overwrite bytes in the value of ``name`` starting at ``offset`` with
        ``value``. If ``offset`` plus the length of ``value`` exceeds the
        length of the original value, the new value will be larger than before.
        If ``offset`` exceeds the length of the original value, null bytes
        will be used to pad between the end of the previous value and the start
        of what's being injected.

        Returns the length of the new string.

        For more information see https://redis.io/commands/setrange
        """
    async def astralgo(self, algo: Literal['LCS'], value1: KeyT, value2: KeyT, specific_argument: Union[Literal['strings'], Literal['keys']] = 'strings', len: bool = False, idx: bool = False, minmatchlen: Union[int, None] = None, withmatchlen: bool = False, **kwargs) -> ResponseT:
        """
        Implements complex algorithms that operate on strings.
        Right now the only algorithm implemented is the LCS algorithm
        (longest common substring). However new algorithms could be
        implemented in the future.

        ``algo`` Right now must be LCS
        ``value1`` and ``value2`` Can be two strings or two keys
        ``specific_argument`` Specifying if the arguments to the algorithm
        will be keys or strings. strings is the default.
        ``len`` Returns just the len of the match.
        ``idx`` Returns the match positions in each string.
        ``minmatchlen`` Restrict the list of matches to the ones of a given
        minimal length. Can be provided only when ``idx`` set to True.
        ``withmatchlen`` Returns the matches with the len of the match.
        Can be provided only when ``idx`` set to True.

        For more information see https://redis.io/commands/stralgo
        """
    async def astrlen(self, name: KeyT) -> ResponseT:
        """
        Return the number of bytes stored in the value of ``name``

        For more information see https://redis.io/commands/strlen
        """
    async def asubstr(self, name: KeyT, start: int, end: int = -1) -> ResponseT:
        """
        Return a substring of the string at key ``name``. ``start`` and ``end``
        are 0-based integers specifying the portion of the string to return.
        """
    async def atouch(self, *args: KeyT) -> ResponseT:
        """
        Alters the last access time of a key(s) ``*args``. A key is ignored
        if it does not exist.

        For more information see https://redis.io/commands/touch
        """
    async def attl(self, name: KeyT) -> ResponseT:
        """
        Returns the number of seconds until the key ``name`` will expire

        For more information see https://redis.io/commands/ttl
        """
    async def atype(self, name: KeyT) -> ResponseT:
        """
        Returns the type of key ``name``

        For more information see https://redis.io/commands/type
        """
    async def awatch(self, *names: KeyT) -> None:
        """
        Watches the values at keys ``names``, or None if the key doesn't exist

        For more information see https://redis.io/commands/watch
        """
    async def aunwatch(self) -> None:
        """
        Unwatches the value at key ``name``, or None of the key doesn't exist

        For more information see https://redis.io/commands/unwatch
        """
    async def aunlink(self, *names: KeyT) -> ResponseT:
        """
        Unlink one or more keys specified by ``names``

        For more information see https://redis.io/commands/unlink
        """
    async def alcs(self, key1: str, key2: str, len: Optional[bool] = False, idx: Optional[bool] = False, minmatchlen: Optional[int] = 0, withmatchlen: Optional[bool] = False) -> Union[str, int, list]:
        """
        Find the longest common subsequence between ``key1`` and ``key2``.
        If ``len`` is true the length of the match will will be returned.
        If ``idx`` is true the match position in each strings will be returned.
        ``minmatchlen`` restrict the list of matches to the ones of
        the given ``minmatchlen``.
        If ``withmatchlen`` the length of the match also will be returned.
        For more information see https://redis.io/commands/lcs
        """
    
    """
    Redis commands for List data type.
    see: https://redis.io/topics/data-types#lists
    """
    async def ablpop(self, keys: List, timeout: Optional[int] = 0) -> Union[Awaitable[list], list]:
        """
        LPOP a value off of the first non-empty list
        named in the ``keys`` list.

        If none of the lists in ``keys`` has a value to LPOP, then block
        for ``timeout`` seconds, or until a value gets pushed on to one
        of the lists.

        If timeout is 0, then block indefinitely.

        For more information see https://redis.io/commands/blpop
        """
    async def abrpop(self, keys: List, timeout: Optional[int] = 0) -> Union[Awaitable[list], list]:
        """
        RPOP a value off of the first non-empty list
        named in the ``keys`` list.

        If none of the lists in ``keys`` has a value to RPOP, then block
        for ``timeout`` seconds, or until a value gets pushed on to one
        of the lists.

        If timeout is 0, then block indefinitely.

        For more information see https://redis.io/commands/brpop
        """
    async def abrpoplpush(self, src: str, dst: str, timeout: Optional[int] = 0) -> Union[Awaitable[Optional[str]], Optional[str]]:
        """
        Pop a value off the tail of ``src``, push it on the head of ``dst``
        and then return it.

        This command blocks until a value is in ``src`` or until ``timeout``
        seconds elapse, whichever is first. A ``timeout`` value of 0 blocks
        forever.

        For more information see https://redis.io/commands/brpoplpush
        """
    async def ablmpop(self, timeout: float, numkeys: int, *args: List[str], direction: str, count: Optional[int] = 1) -> Optional[list]:
        """
        Pop ``count`` values (default 1) from first non-empty in the list
        of provided key names.

        When all lists are empty this command blocks the connection until another
        client pushes to it or until the timeout, timeout of 0 blocks indefinitely

        For more information see https://redis.io/commands/blmpop
        """
    async def almpop(self, num_keys: int, *args: List[str], direction: str, count: Optional[int] = 1) -> Union[Awaitable[list], list]:
        """
        Pop ``count`` values (default 1) first non-empty list key from the list
        of args provided key names.

        For more information see https://redis.io/commands/lmpop
        """
    async def alindex(self, name: str, index: int) -> Union[Awaitable[Optional[str]], Optional[str]]:
        """
        Return the item from list ``name`` at position ``index``

        Negative indexes are supported and will return an item at the
        end of the list

        For more information see https://redis.io/commands/lindex
        """
    async def alinsert(self, name: str, where: str, refvalue: str, value: str) -> Union[Awaitable[int], int]:
        """
        Insert ``value`` in list ``name`` either immediately before or after
        [``where``] ``refvalue``

        Returns the new length of the list on success or -1 if ``refvalue``
        is not in the list.

        For more information see https://redis.io/commands/linsert
        """
    async def allen(self, name: str) -> Union[Awaitable[int], int]:
        """
        Return the length of the list ``name``

        For more information see https://redis.io/commands/llen
        """
    async def alpop(self, name: str, count: Optional[int] = None) -> Union[Awaitable[Union[str, List, None]], Union[str, List, None]]:
        """
        Removes and returns the first elements of the list ``name``.

        By default, the command pops a single element from the beginning of
        the list. When provided with the optional ``count`` argument, the reply
        will consist of up to count elements, depending on the list's length.

        For more information see https://redis.io/commands/lpop
        """
    async def alpush(self, name: str, *values: FieldT) -> Union[Awaitable[int], int]:
        """
        Push ``values`` onto the head of the list ``name``

        For more information see https://redis.io/commands/lpush
        """
    async def alpushx(self, name: str, *values: FieldT) -> Union[Awaitable[int], int]:
        """
        Push ``value`` onto the head of the list ``name`` if ``name`` exists

        For more information see https://redis.io/commands/lpushx
        """
    async def alrange(self, name: str, start: int, end: int) -> Union[Awaitable[list], list]:
        """
        Return a slice of the list ``name`` between
        position ``start`` and ``end``

        ``start`` and ``end`` can be negative numbers just like
        Python slicing notation

        For more information see https://redis.io/commands/lrange
        """
    async def alrem(self, name: str, count: int, value: str) -> Union[Awaitable[int], int]:
        """
        Remove the first ``count`` occurrences of elements equal to ``value``
        from the list stored at ``name``.

        The count argument influences the operation in the following ways:
            count > 0: Remove elements equal to value moving from head to tail.
            count < 0: Remove elements equal to value moving from tail to head.
            count = 0: Remove all elements equal to value.

            For more information see https://redis.io/commands/lrem
        """
    async def alset(self, name: str, index: int, value: str) -> Union[Awaitable[str], str]:
        """
        Set element at ``index`` of list ``name`` to ``value``

        For more information see https://redis.io/commands/lset
        """
    async def altrim(self, name: str, start: int, end: int) -> Union[Awaitable[str], str]:
        """
        Trim the list ``name``, removing all values not within the slice
        between ``start`` and ``end``

        ``start`` and ``end`` can be negative numbers just like
        Python slicing notation

        For more information see https://redis.io/commands/ltrim
        """
    async def arpop(self, name: str, count: Optional[int] = None) -> Union[Awaitable[Union[str, List, None]], Union[str, List, None]]:
        """
        Removes and returns the last elements of the list ``name``.

        By default, the command pops a single element from the end of the list.
        When provided with the optional ``count`` argument, the reply will
        consist of up to count elements, depending on the list's length.

        For more information see https://redis.io/commands/rpop
        """
    async def arpoplpush(self, src: str, dst: str) -> Union[Awaitable[str], str]:
        """
        RPOP a value off of the ``src`` list and atomically LPUSH it
        on to the ``dst`` list.  Returns the value.

        For more information see https://redis.io/commands/rpoplpush
        """
    async def arpush(self, name: str, *values: FieldT) -> Union[Awaitable[int], int]:
        """
        Push ``values`` onto the tail of the list ``name``

        For more information see https://redis.io/commands/rpush
        """
    async def arpushx(self, name: str, *values: str) -> Union[Awaitable[int], int]:
        """
        Push ``value`` onto the tail of the list ``name`` if ``name`` exists

        For more information see https://redis.io/commands/rpushx
        """
    async def alpos(self, name: str, value: str, rank: Optional[int] = None, count: Optional[int] = None, maxlen: Optional[int] = None) -> Union[str, List, None]:
        '''
        Get position of ``value`` within the list ``name``

         If specified, ``rank`` indicates the "rank" of the first element to
         return in case there are multiple copies of ``value`` in the list.
         By default, LPOS returns the position of the first occurrence of
         ``value`` in the list. When ``rank`` 2, LPOS returns the position of
         the second ``value`` in the list. If ``rank`` is negative, LPOS
         searches the list in reverse. For example, -1 would return the
         position of the last occurrence of ``value`` and -2 would return the
         position of the next to last occurrence of ``value``.

         If specified, ``count`` indicates that LPOS should return a list of
         up to ``count`` positions. A ``count`` of 2 would return a list of
         up to 2 positions. A ``count`` of 0 returns a list of all positions
         matching ``value``. When ``count`` is specified and but ``value``
         does not exist in the list, an empty list is returned.

         If specified, ``maxlen`` indicates the maximum number of list
         elements to scan. A ``maxlen`` of 1000 will only return the
         position(s) of items within the first 1000 entries in the list.
         A ``maxlen`` of 0 (the default) will scan the entire list.

         For more information see https://redis.io/commands/lpos
        '''
    async def asort(self, name: str, start: Optional[int] = None, num: Optional[int] = None, by: Optional[str] = None, get: Optional[List[str]] = None, desc: bool = False, alpha: bool = False, store: Optional[str] = None, groups: Optional[bool] = False) -> Union[List, int]:
        '''
        Sort and return the list, set or sorted set at ``name``.

        ``start`` and ``num`` allow for paging through the sorted data

        ``by`` allows using an external key to weight and sort the items.
            Use an "*" to indicate where in the key the item value is located

        ``get`` allows for returning items from external keys rather than the
            sorted data itself.  Use an "*" to indicate where in the key
            the item value is located

        ``desc`` allows for reversing the sort

        ``alpha`` allows for sorting lexicographically rather than numerically

        ``store`` allows for storing the result of the sort into
            the key ``store``

        ``groups`` if set to True and if ``get`` contains at least two
            elements, sort will return a list of tuples, each containing the
            values fetched from the arguments to ``get``.

        For more information see https://redis.io/commands/sort
        '''
    async def asort_ro(self, key: str, start: Optional[int] = None, num: Optional[int] = None, by: Optional[str] = None, get: Optional[List[str]] = None, desc: bool = False, alpha: bool = False) -> list:
        '''
        Returns the elements contained in the list, set or sorted set at key.
        (read-only variant of the SORT command)

        ``start`` and ``num`` allow for paging through the sorted data

        ``by`` allows using an external key to weight and sort the items.
            Use an "*" to indicate where in the key the item value is located

        ``get`` allows for returning items from external keys rather than the
            sorted data itself.  Use an "*" to indicate where in the key
            the item value is located

        ``desc`` allows for reversing the sort

        ``alpha`` allows for sorting lexicographically rather than numerically

        For more information see https://redis.io/commands/sort_ro
        '''

    """
    Redis SCAN commands.
    see: https://redis.io/commands/scan
    """
    async def ascan(self, cursor: int = 0, match: Union[PatternT, None] = None, count: Union[int, None] = None, _type: Union[str, None] = None, **kwargs) -> ResponseT:
        """
        Incrementally return lists of key names. Also return a cursor
        indicating the scan position.

        ``match`` allows for filtering the keys by pattern

        ``count`` provides a hint to Redis about the number of keys to
            return per batch.

        ``_type`` filters the returned values by a particular Redis type.
            Stock Redis instances allow for the following types:
            HASH, LIST, SET, STREAM, STRING, ZSET
            Additionally, Redis modules can expose other types as well.

        For more information see https://redis.io/commands/scan
        """
    async def ascan_iter(self, match: Union[PatternT, None] = None, count: Union[int, None] = None, _type: Union[str, None] = None, **kwargs) -> AsyncIterator:
        """
        Make an iterator using the SCAN command so that the client doesn't
        need to remember the cursor position.

        ``match`` allows for filtering the keys by pattern

        ``count`` provides a hint to Redis about the number of keys to
            return per batch.

        ``_type`` filters the returned values by a particular Redis type.
            Stock Redis instances allow for the following types:
            HASH, LIST, SET, STREAM, STRING, ZSET
            Additionally, Redis modules can expose other types as well.
        """
    async def asscan(self, name: KeyT, cursor: int = 0, match: Union[PatternT, None] = None, count: Union[int, None] = None) -> ResponseT:
        """
        Incrementally return lists of elements in a set. Also return a cursor
        indicating the scan position.

        ``match`` allows for filtering the keys by pattern

        ``count`` allows for hint the minimum number of returns

        For more information see https://redis.io/commands/sscan
        """
    async def asscan_iter(self, name: KeyT, match: Union[PatternT, None] = None, count: Union[int, None] = None) -> AsyncIterator:
        """
        Make an iterator using the SSCAN command so that the client doesn't
        need to remember the cursor position.

        ``match`` allows for filtering the keys by pattern

        ``count`` allows for hint the minimum number of returns
        """
    async def ahscan(self, name: KeyT, cursor: int = 0, match: Union[PatternT, None] = None, count: Union[int, None] = None) -> ResponseT:
        """
        Incrementally return key/value slices in a hash. Also return a cursor
        indicating the scan position.

        ``match`` allows for filtering the keys by pattern

        ``count`` allows for hint the minimum number of returns

        For more information see https://redis.io/commands/hscan
        """
    async def ahscan_iter(self, name: str, match: Union[PatternT, None] = None, count: Union[int, None] = None) -> AsyncIterator:
        """
        Make an iterator using the HSCAN command so that the client doesn't
        need to remember the cursor position.

        ``match`` allows for filtering the keys by pattern

        ``count`` allows for hint the minimum number of returns
        """
    async def azscan(self, name: KeyT, cursor: int = 0, match: Union[PatternT, None] = None, count: Union[int, None] = None, score_cast_func: Union[type, Callable] = ...) -> ResponseT:
        """
        Incrementally return lists of elements in a sorted set. Also return a
        cursor indicating the scan position.

        ``match`` allows for filtering the keys by pattern

        ``count`` allows for hint the minimum number of returns

        ``score_cast_func`` a callable used to cast the score return value

        For more information see https://redis.io/commands/zscan
        """
    async def azscan_iter(self, name: KeyT, match: Union[PatternT, None] = None, count: Union[int, None] = None, score_cast_func: Union[type, Callable] = ...) -> AsyncIterator:
        """
        Make an iterator using the ZSCAN command so that the client doesn't
        need to remember the cursor position.

        ``match`` allows for filtering the keys by pattern

        ``count`` allows for hint the minimum number of returns

        ``score_cast_func`` a callable used to cast the score return value
        """


    """
    Redis commands for Set data type.
    see: https://redis.io/topics/data-types#sets
    """
    async def asadd(self, name: str, *values: FieldT) -> Union[Awaitable[int], int]:
        """
        Add ``value(s)`` to set ``name``

        For more information see https://redis.io/commands/sadd
        """
    async def ascard(self, name: str) -> Union[Awaitable[int], int]:
        """
        Return the number of elements in set ``name``

        For more information see https://redis.io/commands/scard
        """
    async def asdiff(self, keys: List, *args: List) -> Union[Awaitable[list], list]:
        """
        Return the difference of sets specified by ``keys``

        For more information see https://redis.io/commands/sdiff
        """
    async def asdiffstore(self, dest: str, keys: List, *args: List) -> Union[Awaitable[int], int]:
        """
        Store the difference of sets specified by ``keys`` into a new
        set named ``dest``.  Returns the number of keys in the new set.

        For more information see https://redis.io/commands/sdiffstore
        """
    async def asinter(self, keys: List, *args: List) -> Union[Awaitable[list], list]:
        """
        Return the intersection of sets specified by ``keys``

        For more information see https://redis.io/commands/sinter
        """
    async def asintercard(self, numkeys: int, keys: List[str], limit: int = 0) -> Union[Awaitable[int], int]:
        """
        Return the cardinality of the intersect of multiple sets specified by ``keys`.

        When LIMIT provided (defaults to 0 and means unlimited), if the intersection
        cardinality reaches limit partway through the computation, the algorithm will
        exit and yield limit as the cardinality

        For more information see https://redis.io/commands/sintercard
        """
    async def asinterstore(self, dest: str, keys: List, *args: List) -> Union[Awaitable[int], int]:
        """
        Store the intersection of sets specified by ``keys`` into a new
        set named ``dest``.  Returns the number of keys in the new set.

        For more information see https://redis.io/commands/sinterstore
        """
    async def asismember(self, name: str, value: str) -> Union[Awaitable[Union[Literal[0], Literal[1]]], Union[Literal[0], Literal[1]]]:
        """
        Return whether ``value`` is a member of set ``name``:
        - 1 if the value is a member of the set.
        - 0 if the value is not a member of the set or if key does not exist.

        For more information see https://redis.io/commands/sismember
        """
    async def asmembers(self, name: str) -> Union[Awaitable[Set], Set]:
        """
        Return all members of the set ``name``

        For more information see https://redis.io/commands/smembers
        """
    async def asmismember(self, name: str, values: List, *args: List) -> Union[Awaitable[List[Union[Literal[0], Literal[1]]]], List[Union[Literal[0], Literal[1]]]]:
        """
        Return whether each value in ``values`` is a member of the set ``name``
        as a list of ``int`` in the order of ``values``:
        - 1 if the value is a member of the set.
        - 0 if the value is not a member of the set or if key does not exist.

        For more information see https://redis.io/commands/smismember
        """
    async def asmove(self, src: str, dst: str, value: str) -> Union[Awaitable[bool], bool]:
        """
        Move ``value`` from set ``src`` to set ``dst`` atomically

        For more information see https://redis.io/commands/smove
        """
    async def aspop(self, name: str, count: Optional[int] = None) -> Union[str, List, None]:
        """
        Remove and return a random member of set ``name``

        For more information see https://redis.io/commands/spop
        """
    async def asrandmember(self, name: str, number: Optional[int] = None) -> Union[str, List, None]:
        """
        If ``number`` is None, returns a random member of set ``name``.

        If ``number`` is supplied, returns a list of ``number`` random
        members of set ``name``. Note this is only available when running
        Redis 2.6+.

        For more information see https://redis.io/commands/srandmember
        """
    async def asrem(self, name: str, *values: FieldT) -> Union[Awaitable[int], int]:
        """
        Remove ``values`` from set ``name``

        For more information see https://redis.io/commands/srem
        """
    async def asunion(self, keys: List, *args: List) -> Union[Awaitable[List], List]:
        """
        Return the union of sets specified by ``keys``

        For more information see https://redis.io/commands/sunion
        """
    async def asunionstore(self, dest: str, keys: List, *args: List) -> Union[Awaitable[int], int]:
        """
        Store the union of sets specified by ``keys`` into a new
        set named ``dest``.  Returns the number of keys in the new set.

        For more information see https://redis.io/commands/sunionstore
        """
    """
    Redis commands for Stream data type.
    see: https://redis.io/topics/streams-intro
    """
    async def axack(self, name: KeyT, groupname: GroupT, *ids: StreamIdT) -> ResponseT:
        """
        Acknowledges the successful processing of one or more messages.
        name: name of the stream.
        groupname: name of the consumer group.
        *ids: message ids to acknowledge.

        For more information see https://redis.io/commands/xack
        """
    async def axadd(self, name: KeyT, fields: Dict[FieldT, EncodableT], id: StreamIdT = '*', maxlen: Union[int, None] = None, approximate: bool = True, nomkstream: bool = False, minid: Union[StreamIdT, None] = None, limit: Union[int, None] = None) -> ResponseT:
        """
        Add to a stream.
        name: name of the stream
        fields: dict of field/value pairs to insert into the stream
        id: Location to insert this record. By default it is appended.
        maxlen: truncate old stream members beyond this size.
        Can't be specified with minid.
        approximate: actual stream length may be slightly more than maxlen
        nomkstream: When set to true, do not make a stream
        minid: the minimum id in the stream to query.
        Can't be specified with maxlen.
        limit: specifies the maximum number of entries to retrieve

        For more information see https://redis.io/commands/xadd
        """
    async def axautoclaim(self, name: KeyT, groupname: GroupT, consumername: ConsumerT, min_idle_time: int, start_id: StreamIdT = '0-0', count: Union[int, None] = None, justid: bool = False) -> ResponseT:
        """
        Transfers ownership of pending stream entries that match the specified
        criteria. Conceptually, equivalent to calling XPENDING and then XCLAIM,
        but provides a more straightforward way to deal with message delivery
        failures via SCAN-like semantics.
        name: name of the stream.
        groupname: name of the consumer group.
        consumername: name of a consumer that claims the message.
        min_idle_time: filter messages that were idle less than this amount of
        milliseconds.
        start_id: filter messages with equal or greater ID.
        count: optional integer, upper limit of the number of entries that the
        command attempts to claim. Set to 100 by default.
        justid: optional boolean, false by default. Return just an array of IDs
        of messages successfully claimed, without returning the actual message

        For more information see https://redis.io/commands/xautoclaim
        """
    async def axclaim(self, name: KeyT, groupname: GroupT, consumername: ConsumerT, min_idle_time: int, message_ids: Union[List[StreamIdT], Tuple[StreamIdT]], idle: Union[int, None] = None, time: Union[int, None] = None, retrycount: Union[int, None] = None, force: bool = False, justid: bool = False) -> ResponseT:
        """
        Changes the ownership of a pending message.

        name: name of the stream.

        groupname: name of the consumer group.

        consumername: name of a consumer that claims the message.

        min_idle_time: filter messages that were idle less than this amount of
        milliseconds

        message_ids: non-empty list or tuple of message IDs to claim

        idle: optional. Set the idle time (last time it was delivered) of the
        message in ms

        time: optional integer. This is the same as idle but instead of a
        relative amount of milliseconds, it sets the idle time to a specific
        Unix time (in milliseconds).

        retrycount: optional integer. set the retry counter to the specified
        value. This counter is incremented every time a message is delivered
        again.

        force: optional boolean, false by default. Creates the pending message
        entry in the PEL even if certain specified IDs are not already in the
        PEL assigned to a different client.

        justid: optional boolean, false by default. Return just an array of IDs
        of messages successfully claimed, without returning the actual message

        For more information see https://redis.io/commands/xclaim
        """
    async def axdel(self, name: KeyT, *ids: StreamIdT) -> ResponseT:
        """
        Deletes one or more messages from a stream.
        name: name of the stream.
        *ids: message ids to delete.

        For more information see https://redis.io/commands/xdel
        """
    async def axgroup_create(self, name: KeyT, groupname: GroupT, id: StreamIdT = '$', mkstream: bool = False, entries_read: Optional[int] = None) -> ResponseT:
        """
        Create a new consumer group associated with a stream.
        name: name of the stream.
        groupname: name of the consumer group.
        id: ID of the last item in the stream to consider already delivered.

        For more information see https://redis.io/commands/xgroup-create
        """
    async def axgroup_delconsumer(self, name: KeyT, groupname: GroupT, consumername: ConsumerT) -> ResponseT:
        """
        Remove a specific consumer from a consumer group.
        Returns the number of pending messages that the consumer had before it
        was deleted.
        name: name of the stream.
        groupname: name of the consumer group.
        consumername: name of consumer to delete

        For more information see https://redis.io/commands/xgroup-delconsumer
        """
    async def axgroup_destroy(self, name: KeyT, groupname: GroupT) -> ResponseT:
        """
        Destroy a consumer group.
        name: name of the stream.
        groupname: name of the consumer group.

        For more information see https://redis.io/commands/xgroup-destroy
        """
    async def axgroup_createconsumer(self, name: KeyT, groupname: GroupT, consumername: ConsumerT) -> ResponseT:
        """
        Consumers in a consumer group are auto-created every time a new
        consumer name is mentioned by some command.
        They can be explicitly created by using this command.
        name: name of the stream.
        groupname: name of the consumer group.
        consumername: name of consumer to create.

        See: https://redis.io/commands/xgroup-createconsumer
        """
    async def axgroup_setid(self, name: KeyT, groupname: GroupT, id: StreamIdT, entries_read: Optional[int] = None) -> ResponseT:
        """
        Set the consumer group last delivered ID to something else.
        name: name of the stream.
        groupname: name of the consumer group.
        id: ID of the last item in the stream to consider already delivered.

        For more information see https://redis.io/commands/xgroup-setid
        """
    async def axinfo_consumers(self, name: KeyT, groupname: GroupT) -> ResponseT:
        """
        Returns general information about the consumers in the group.
        name: name of the stream.
        groupname: name of the consumer group.

        For more information see https://redis.io/commands/xinfo-consumers
        """
    async def axinfo_groups(self, name: KeyT) -> ResponseT:
        """
        Returns general information about the consumer groups of the stream.
        name: name of the stream.

        For more information see https://redis.io/commands/xinfo-groups
        """
    async def axinfo_stream(self, name: KeyT, full: bool = False) -> ResponseT:
        """
        Returns general information about the stream.
        name: name of the stream.
        full: optional boolean, false by default. Return full summary

        For more information see https://redis.io/commands/xinfo-stream
        """
    async def axlen(self, name: KeyT) -> ResponseT:
        """
        Returns the number of elements in a given stream.

        For more information see https://redis.io/commands/xlen
        """
    async def axpending(self, name: KeyT, groupname: GroupT) -> ResponseT:
        """
        Returns information about pending messages of a group.
        name: name of the stream.
        groupname: name of the consumer group.

        For more information see https://redis.io/commands/xpending
        """
    async def axpending_range(self, name: KeyT, groupname: GroupT, min: StreamIdT, max: StreamIdT, count: int, consumername: Union[ConsumerT, None] = None, idle: Union[int, None] = None) -> ResponseT:
        """
        Returns information about pending messages, in a range.

        name: name of the stream.
        groupname: name of the consumer group.
        idle: available from  version 6.2. filter entries by their
        idle-time, given in milliseconds (optional).
        min: minimum stream ID.
        max: maximum stream ID.
        count: number of messages to return
        consumername: name of a consumer to filter by (optional).
        """
    async def axrange(self, name: KeyT, min: StreamIdT = '-', max: StreamIdT = '+', count: Union[int, None] = None) -> ResponseT:
        """
        Read stream values within an interval.

        name: name of the stream.

        start: first stream ID. defaults to '-',
               meaning the earliest available.

        finish: last stream ID. defaults to '+',
                meaning the latest available.

        count: if set, only return this many items, beginning with the
               earliest available.

        For more information see https://redis.io/commands/xrange
        """
    async def axread(self, streams: Dict[KeyT, StreamIdT], count: Union[int, None] = None, block: Union[int, None] = None) -> ResponseT:
        """
        Block and monitor multiple streams for new data.

        streams: a dict of stream names to stream IDs, where
                   IDs indicate the last ID already seen.

        count: if set, only return this many items, beginning with the
               earliest available.

        block: number of milliseconds to wait, if nothing already present.

        For more information see https://redis.io/commands/xread
        """
    async def axreadgroup(self, groupname: str, consumername: str, streams: Dict[KeyT, StreamIdT], count: Union[int, None] = None, block: Union[int, None] = None, noack: bool = False) -> ResponseT:
        """
        Read from a stream via a consumer group.

        groupname: name of the consumer group.

        consumername: name of the requesting consumer.

        streams: a dict of stream names to stream IDs, where
               IDs indicate the last ID already seen.

        count: if set, only return this many items, beginning with the
               earliest available.

        block: number of milliseconds to wait, if nothing already present.
        noack: do not add messages to the PEL

        For more information see https://redis.io/commands/xreadgroup
        """
    async def axrevrange(self, name: KeyT, max: StreamIdT = '+', min: StreamIdT = '-', count: Union[int, None] = None) -> ResponseT:
        """
        Read stream values within an interval, in reverse order.

        name: name of the stream

        start: first stream ID. defaults to '+',
               meaning the latest available.

        finish: last stream ID. defaults to '-',
                meaning the earliest available.

        count: if set, only return this many items, beginning with the
               latest available.

        For more information see https://redis.io/commands/xrevrange
        """
    async def axtrim(self, name: KeyT, maxlen: Union[int, None] = None, approximate: bool = True, minid: Union[StreamIdT, None] = None, limit: Union[int, None] = None) -> ResponseT:
        """
        Trims old messages from a stream.
        name: name of the stream.
        maxlen: truncate old stream messages beyond this size
        Can't be specified with minid.
        approximate: actual stream length may be slightly more than maxlen
        minid: the minimum id in the stream to query
        Can't be specified with maxlen.
        limit: specifies the maximum number of entries to retrieve

        For more information see https://redis.io/commands/xtrim
        """
    
    """
    Redis commands for Sorted Sets data type.
    see: https://redis.io/topics/data-types-intro#redis-sorted-sets
    """
    async def azadd(self, name: KeyT, mapping: Mapping[AnyKeyT, EncodableT], nx: bool = False, xx: bool = False, ch: bool = False, incr: bool = False, gt: bool = False, lt: bool = False) -> ResponseT:
        """
        Set any number of element-name, score pairs to the key ``name``. Pairs
        are specified as a dict of element-names keys to score values.

        ``nx`` forces ZADD to only create new elements and not to update
        scores for elements that already exist.

        ``xx`` forces ZADD to only update scores of elements that already
        exist. New elements will not be added.

        ``ch`` modifies the return value to be the numbers of elements changed.
        Changed elements include new elements that were added and elements
        whose scores changed.

        ``incr`` modifies ZADD to behave like ZINCRBY. In this mode only a
        single element/score pair can be specified and the score is the amount
        the existing score will be incremented by. When using this mode the
        return value of ZADD will be the new score of the element.

        ``LT`` Only update existing elements if the new score is less than
        the current score. This flag doesn't prevent adding new elements.

        ``GT`` Only update existing elements if the new score is greater than
        the current score. This flag doesn't prevent adding new elements.

        The return value of ZADD varies based on the mode specified. With no
        options, ZADD returns the number of new elements added to the sorted
        set.

        ``NX``, ``LT``, and ``GT`` are mutually exclusive options.

        See: https://redis.io/commands/ZADD
        """
    async def azcard(self, name: KeyT) -> ResponseT:
        """
        Return the number of elements in the sorted set ``name``

        For more information see https://redis.io/commands/zcard
        """
    async def azcount(self, name: KeyT, min: ZScoreBoundT, max: ZScoreBoundT) -> ResponseT:
        """
        Returns the number of elements in the sorted set at key ``name`` with
        a score between ``min`` and ``max``.

        For more information see https://redis.io/commands/zcount
        """
    async def azdiff(self, keys: KeysT, withscores: bool = False) -> ResponseT:
        """
        Returns the difference between the first and all successive input
        sorted sets provided in ``keys``.

        For more information see https://redis.io/commands/zdiff
        """
    async def azdiffstore(self, dest: KeyT, keys: KeysT) -> ResponseT:
        """
        Computes the difference between the first and all successive input
        sorted sets provided in ``keys`` and stores the result in ``dest``.

        For more information see https://redis.io/commands/zdiffstore
        """
    async def azincrby(self, name: KeyT, amount: float, value: EncodableT) -> ResponseT:
        """
        Increment the score of ``value`` in sorted set ``name`` by ``amount``

        For more information see https://redis.io/commands/zincrby
        """
    async def azinter(self, keys: KeysT, aggregate: Union[str, None] = None, withscores: bool = False) -> ResponseT:
        """
        Return the intersect of multiple sorted sets specified by ``keys``.
        With the ``aggregate`` option, it is possible to specify how the
        results of the union are aggregated. This option defaults to SUM,
        where the score of an element is summed across the inputs where it
        exists. When this option is set to either MIN or MAX, the resulting
        set will contain the minimum or maximum score of an element across
        the inputs where it exists.

        For more information see https://redis.io/commands/zinter
        """
    async def azinterstore(self, dest: KeyT, keys: Union[Sequence[KeyT], Mapping[AnyKeyT, float]], aggregate: Union[str, None] = None) -> ResponseT:
        """
        Intersect multiple sorted sets specified by ``keys`` into a new
        sorted set, ``dest``. Scores in the destination will be aggregated
        based on the ``aggregate``. This option defaults to SUM, where the
        score of an element is summed across the inputs where it exists.
        When this option is set to either MIN or MAX, the resulting set will
        contain the minimum or maximum score of an element across the inputs
        where it exists.

        For more information see https://redis.io/commands/zinterstore
        """
    async def azintercard(self, numkeys: int, keys: List[str], limit: int = 0) -> Union[Awaitable[int], int]:
        """
        Return the cardinality of the intersect of multiple sorted sets
        specified by ``keys`.
        When LIMIT provided (defaults to 0 and means unlimited), if the intersection
        cardinality reaches limit partway through the computation, the algorithm will
        exit and yield limit as the cardinality

        For more information see https://redis.io/commands/zintercard
        """
    async def azlexcount(self, name, min, max):
        """
        Return the number of items in the sorted set ``name`` between the
        lexicographical range ``min`` and ``max``.

        For more information see https://redis.io/commands/zlexcount
        """
    async def azpopmax(self, name: KeyT, count: Union[int, None] = None) -> ResponseT:
        """
        Remove and return up to ``count`` members with the highest scores
        from the sorted set ``name``.

        For more information see https://redis.io/commands/zpopmax
        """
    async def azpopmin(self, name: KeyT, count: Union[int, None] = None) -> ResponseT:
        """
        Remove and return up to ``count`` members with the lowest scores
        from the sorted set ``name``.

        For more information see https://redis.io/commands/zpopmin
        """
    async def azrandmember(self, key: KeyT, count: int = None, withscores: bool = False) -> ResponseT:
        """
        Return a random element from the sorted set value stored at key.

        ``count`` if the argument is positive, return an array of distinct
        fields. If called with a negative count, the behavior changes and
        the command is allowed to return the same field multiple times.
        In this case, the number of returned fields is the absolute value
        of the specified count.

        ``withscores`` The optional WITHSCORES modifier changes the reply so it
        includes the respective scores of the randomly selected elements from
        the sorted set.

        For more information see https://redis.io/commands/zrandmember
        """
    async def abzpopmax(self, keys: KeysT, timeout: TimeoutSecT = 0) -> ResponseT:
        """
        ZPOPMAX a value off of the first non-empty sorted set
        named in the ``keys`` list.

        If none of the sorted sets in ``keys`` has a value to ZPOPMAX,
        then block for ``timeout`` seconds, or until a member gets added
        to one of the sorted sets.

        If timeout is 0, then block indefinitely.

        For more information see https://redis.io/commands/bzpopmax
        """
    async def abzpopmin(self, keys: KeysT, timeout: TimeoutSecT = 0) -> ResponseT:
        """
        ZPOPMIN a value off of the first non-empty sorted set
        named in the ``keys`` list.

        If none of the sorted sets in ``keys`` has a value to ZPOPMIN,
        then block for ``timeout`` seconds, or until a member gets added
        to one of the sorted sets.

        If timeout is 0, then block indefinitely.

        For more information see https://redis.io/commands/bzpopmin
        """
    async def azmpop(self, num_keys: int, keys: List[str], min: Optional[bool] = False, max: Optional[bool] = False, count: Optional[int] = 1) -> Union[Awaitable[list], list]:
        """
        Pop ``count`` values (default 1) off of the first non-empty sorted set
        named in the ``keys`` list.
        For more information see https://redis.io/commands/zmpop
        """
    async def abzmpop(self, timeout: float, numkeys: int, keys: List[str], min: Optional[bool] = False, max: Optional[bool] = False, count: Optional[int] = 1) -> Optional[list]:
        """
        Pop ``count`` values (default 1) off of the first non-empty sorted set
        named in the ``keys`` list.

        If none of the sorted sets in ``keys`` has a value to pop,
        then block for ``timeout`` seconds, or until a member gets added
        to one of the sorted sets.

        If timeout is 0, then block indefinitely.

        For more information see https://redis.io/commands/bzmpop
        """
    async def azrange(self, name: KeyT, start: int, end: int, desc: bool = False, withscores: bool = False, score_cast_func: Union[type, Callable] = ..., byscore: bool = False, bylex: bool = False, offset: int = None, num: int = None) -> ResponseT:
        """
        Return a range of values from sorted set ``name`` between
        ``start`` and ``end`` sorted in ascending order.

        ``start`` and ``end`` can be negative, indicating the end of the range.

        ``desc`` a boolean indicating whether to sort the results in reversed
        order.

        ``withscores`` indicates to return the scores along with the values.
        The return type is a list of (value, score) pairs.

        ``score_cast_func`` a callable used to cast the score return value.

        ``byscore`` when set to True, returns the range of elements from the
        sorted set having scores equal or between ``start`` and ``end``.

        ``bylex`` when set to True, returns the range of elements from the
        sorted set between the ``start`` and ``end`` lexicographical closed
        range intervals.
        Valid ``start`` and ``end`` must start with ( or [, in order to specify
        whether the range interval is exclusive or inclusive, respectively.

        ``offset`` and ``num`` are specified, then return a slice of the range.
        Can't be provided when using ``bylex``.

        For more information see https://redis.io/commands/zrange
        """
    async def azrevrange(self, name: KeyT, start: int, end: int, withscores: bool = False, score_cast_func: Union[type, Callable] = ...) -> ResponseT:
        """
        Return a range of values from sorted set ``name`` between
        ``start`` and ``end`` sorted in descending order.

        ``start`` and ``end`` can be negative, indicating the end of the range.

        ``withscores`` indicates to return the scores along with the values
        The return type is a list of (value, score) pairs

        ``score_cast_func`` a callable used to cast the score return value

        For more information see https://redis.io/commands/zrevrange
        """
    async def azrangestore(self, dest: KeyT, name: KeyT, start: int, end: int, byscore: bool = False, bylex: bool = False, desc: bool = False, offset: Union[int, None] = None, num: Union[int, None] = None) -> ResponseT:
        """
        Stores in ``dest`` the result of a range of values from sorted set
        ``name`` between ``start`` and ``end`` sorted in ascending order.

        ``start`` and ``end`` can be negative, indicating the end of the range.

        ``byscore`` when set to True, returns the range of elements from the
        sorted set having scores equal or between ``start`` and ``end``.

        ``bylex`` when set to True, returns the range of elements from the
        sorted set between the ``start`` and ``end`` lexicographical closed
        range intervals.
        Valid ``start`` and ``end`` must start with ( or [, in order to specify
        whether the range interval is exclusive or inclusive, respectively.

        ``desc`` a boolean indicating whether to sort the results in reversed
        order.

        ``offset`` and ``num`` are specified, then return a slice of the range.
        Can't be provided when using ``bylex``.

        For more information see https://redis.io/commands/zrangestore
        """
    async def azrangebylex(self, name: KeyT, min: EncodableT, max: EncodableT, start: Union[int, None] = None, num: Union[int, None] = None) -> ResponseT:
        """
        Return the lexicographical range of values from sorted set ``name``
        between ``min`` and ``max``.

        If ``start`` and ``num`` are specified, then return a slice of the
        range.

        For more information see https://redis.io/commands/zrangebylex
        """
    async def azrevrangebylex(self, name: KeyT, max: EncodableT, min: EncodableT, start: Union[int, None] = None, num: Union[int, None] = None) -> ResponseT:
        """
        Return the reversed lexicographical range of values from sorted set
        ``name`` between ``max`` and ``min``.

        If ``start`` and ``num`` are specified, then return a slice of the
        range.

        For more information see https://redis.io/commands/zrevrangebylex
        """
    async def azrangebyscore(self, name: KeyT, min: ZScoreBoundT, max: ZScoreBoundT, start: Union[int, None] = None, num: Union[int, None] = None, withscores: bool = False, score_cast_func: Union[type, Callable] = ...) -> ResponseT:
        """
        Return a range of values from the sorted set ``name`` with scores
        between ``min`` and ``max``.

        If ``start`` and ``num`` are specified, then return a slice
        of the range.

        ``withscores`` indicates to return the scores along with the values.
        The return type is a list of (value, score) pairs

        `score_cast_func`` a callable used to cast the score return value

        For more information see https://redis.io/commands/zrangebyscore
        """
    async def azrevrangebyscore(self, name: KeyT, max: ZScoreBoundT, min: ZScoreBoundT, start: Union[int, None] = None, num: Union[int, None] = None, withscores: bool = False, score_cast_func: Union[type, Callable] = ...):
        """
        Return a range of values from the sorted set ``name`` with scores
        between ``min`` and ``max`` in descending order.

        If ``start`` and ``num`` are specified, then return a slice
        of the range.

        ``withscores`` indicates to return the scores along with the values.
        The return type is a list of (value, score) pairs

        ``score_cast_func`` a callable used to cast the score return value

        For more information see https://redis.io/commands/zrevrangebyscore
        """
    async def azrank(self, name: KeyT, value: EncodableT, withscore: bool = False) -> ResponseT:
        """
        Returns a 0-based value indicating the rank of ``value`` in sorted set
        ``name``.
        The optional WITHSCORE argument supplements the command's
        reply with the score of the element returned.

        For more information see https://redis.io/commands/zrank
        """
    async def azrem(self, name: KeyT, *values: FieldT) -> ResponseT:
        """
        Remove member ``values`` from sorted set ``name``

        For more information see https://redis.io/commands/zrem
        """
    async def azremrangebylex(self, name: KeyT, min: EncodableT, max: EncodableT) -> ResponseT:
        """
        Remove all elements in the sorted set ``name`` between the
        lexicographical range specified by ``min`` and ``max``.

        Returns the number of elements removed.

        For more information see https://redis.io/commands/zremrangebylex
        """
    async def azremrangebyrank(self, name: KeyT, min: int, max: int) -> ResponseT:
        """
        Remove all elements in the sorted set ``name`` with ranks between
        ``min`` and ``max``. Values are 0-based, ordered from smallest score
        to largest. Values can be negative indicating the highest scores.
        Returns the number of elements removed

        For more information see https://redis.io/commands/zremrangebyrank
        """
    async def azremrangebyscore(self, name: KeyT, min: ZScoreBoundT, max: ZScoreBoundT) -> ResponseT:
        """
        Remove all elements in the sorted set ``name`` with scores
        between ``min`` and ``max``. Returns the number of elements removed.

        For more information see https://redis.io/commands/zremrangebyscore
        """
    async def azrevrank(self, name: KeyT, value: EncodableT, withscore: bool = False) -> ResponseT:
        """
        Returns a 0-based value indicating the descending rank of
        ``value`` in sorted set ``name``.
        The optional ``withscore`` argument supplements the command's
        reply with the score of the element returned.

        For more information see https://redis.io/commands/zrevrank
        """
    async def azscore(self, name: KeyT, value: EncodableT) -> ResponseT:
        """
        Return the score of element ``value`` in sorted set ``name``

        For more information see https://redis.io/commands/zscore
        """
    async def azunion(self, keys: Union[Sequence[KeyT], Mapping[AnyKeyT, float]], aggregate: Union[str, None] = None, withscores: bool = False) -> ResponseT:
        """
        Return the union of multiple sorted sets specified by ``keys``.
        ``keys`` can be provided as dictionary of keys and their weights.
        Scores will be aggregated based on the ``aggregate``, or SUM if
        none is provided.

        For more information see https://redis.io/commands/zunion
        """
    async def azunionstore(self, dest: KeyT, keys: Union[Sequence[KeyT], Mapping[AnyKeyT, float]], aggregate: Union[str, None] = None) -> ResponseT:
        """
        Union multiple sorted sets specified by ``keys`` into
        a new sorted set, ``dest``. Scores in the destination will be
        aggregated based on the ``aggregate``, or SUM if none is provided.

        For more information see https://redis.io/commands/zunionstore
        """
    async def azmscore(self, key: KeyT, members: List[str]) -> ResponseT:
        """
        Returns the scores associated with the specified members
        in the sorted set stored at key.
        ``members`` should be a list of the member name.
        Return type is a list of score.
        If the member does not exist, a None will be returned
        in corresponding position.

        For more information see https://redis.io/commands/zmscore
        """
    """
    Redis commands of HyperLogLogs data type.
    see: https://redis.io/topics/data-types-intro#hyperloglogs
    """
    async def apfadd(self, name: KeyT, *values: FieldT) -> ResponseT:
        """
        Adds the specified elements to the specified HyperLogLog.

        For more information see https://redis.io/commands/pfadd
        """
    async def apfcount(self, *sources: KeyT) -> ResponseT:
        """
        Return the approximated cardinality of
        the set observed by the HyperLogLog at key(s).

        For more information see https://redis.io/commands/pfcount
        """
    async def apfmerge(self, dest: KeyT, *sources: KeyT) -> ResponseT:
        """
        Merge N different HyperLogLogs into a single one.

        For more information see https://redis.io/commands/pfmerge
        """
    
    """
    Redis commands for Hash data type.
    see: https://redis.io/topics/data-types-intro#redis-hashes
    """
    async def ahdel(self, name: str, *keys: List) -> Union[Awaitable[int], int]:
        """
        Delete ``keys`` from hash ``name``

        For more information see https://redis.io/commands/hdel
        """
    async def ahexists(self, name: str, key: str) -> Union[Awaitable[bool], bool]:
        """
        Returns a boolean indicating if ``key`` exists within hash ``name``

        For more information see https://redis.io/commands/hexists
        """
    async def ahget(self, name: str, key: str) -> Union[Awaitable[Optional[str]], Optional[str]]:
        """
        Return the value of ``key`` within the hash ``name``

        For more information see https://redis.io/commands/hget
        """
    async def ahgetall(self, name: str) -> Union[Awaitable[dict], dict]:
        """
        Return a Python dict of the hash's name/value pairs

        For more information see https://redis.io/commands/hgetall
        """
    async def ahincrby(self, name: str, key: str, amount: int = 1) -> Union[Awaitable[int], int]:
        """
        Increment the value of ``key`` in hash ``name`` by ``amount``

        For more information see https://redis.io/commands/hincrby
        """
    async def ahincrbyfloat(self, name: str, key: str, amount: float = 1.0) -> Union[Awaitable[float], float]:
        """
        Increment the value of ``key`` in hash ``name`` by floating ``amount``

        For more information see https://redis.io/commands/hincrbyfloat
        """
    async def ahkeys(self, name: str) -> Union[Awaitable[List], List]:
        """
        Return the list of keys within hash ``name``

        For more information see https://redis.io/commands/hkeys
        """
    async def ahlen(self, name: str) -> Union[Awaitable[int], int]:
        """
        Return the number of elements in hash ``name``

        For more information see https://redis.io/commands/hlen
        """
    async def ahset(self, name: str, key: Optional[str] = None, value: Optional[str] = None, mapping: Optional[dict] = None, items: Optional[list] = None) -> Union[Awaitable[int], int]:
        """
        Set ``key`` to ``value`` within hash ``name``,
        ``mapping`` accepts a dict of key/value pairs that will be
        added to hash ``name``.
        ``items`` accepts a list of key/value pairs that will be
        added to hash ``name``.
        Returns the number of fields that were added.

        For more information see https://redis.io/commands/hset
        """
    async def ahsetnx(self, name: str, key: str, value: str) -> Union[Awaitable[bool], bool]:
        """
        Set ``key`` to ``value`` within hash ``name`` if ``key`` does not
        exist.  Returns 1 if HSETNX created a field, otherwise 0.

        For more information see https://redis.io/commands/hsetnx
        """
    async def ahmset(self, name: str, mapping: dict) -> Union[Awaitable[str], str]:
        """
        Set key to value within hash ``name`` for each corresponding
        key and value from the ``mapping`` dict.

        For more information see https://redis.io/commands/hmset
        """
    async def ahmget(self, name: str, keys: List, *args: List) -> Union[Awaitable[List], List]:
        """
        Returns a list of values ordered identically to ``keys``

        For more information see https://redis.io/commands/hmget
        """
    async def ahvals(self, name: str) -> Union[Awaitable[List], List]:
        """
        Return the list of values within hash ``name``

        For more information see https://redis.io/commands/hvals
        """
    async def ahstrlen(self, name: str, key: str) -> Union[Awaitable[int], int]:
        """
        Return the number of bytes stored in the value of ``key``
        within hash ``name``

        For more information see https://redis.io/commands/hstrlen
        """
    """
    Redis PubSub commands.
    see https://redis.io/topics/pubsub
    """
    async def apublish(self, channel: ChannelT, message: EncodableT, **kwargs) -> ResponseT:
        """
        Publish ``message`` on ``channel``.
        Returns the number of subscribers the message was delivered to.

        For more information see https://redis.io/commands/publish
        """
    async def aspublish(self, shard_channel: ChannelT, message: EncodableT) -> ResponseT:
        """
        Posts a message to the given shard channel.
        Returns the number of clients that received the message

        For more information see https://redis.io/commands/spublish
        """
    async def apubsub_channels(self, pattern: PatternT = '*', **kwargs) -> ResponseT:
        """
        Return a list of channels that have at least one subscriber

        For more information see https://redis.io/commands/pubsub-channels
        """
    async def apubsub_shardchannels(self, pattern: PatternT = '*', **kwargs) -> ResponseT:
        """
        Return a list of shard_channels that have at least one subscriber

        For more information see https://redis.io/commands/pubsub-shardchannels
        """
    async def apubsub_numpat(self, **kwargs) -> ResponseT:
        """
        Returns the number of subscriptions to patterns

        For more information see https://redis.io/commands/pubsub-numpat
        """
    async def apubsub_numsub(self, *args: ChannelT, **kwargs) -> ResponseT:
        """
        Return a list of (channel, number of subscribers) tuples
        for each channel given in ``*args``

        For more information see https://redis.io/commands/pubsub-numsub
        """
    async def apubsub_shardnumsub(self, *args: ChannelT, **kwargs) -> ResponseT:
        """
        Return a list of (shard_channel, number of subscribers) tuples
        for each channel given in ``*args``

        For more information see https://redis.io/commands/pubsub-shardnumsub
        """

    """
    Redis Lua script commands. see:
    https://redis.com/ebook/part-3-next-steps/chapter-11-scripting-redis-with-lua/
    """
    async def aeval(self, script: str, numkeys: int, *keys_and_args: list) -> Union[Awaitable[str], str]:
        """
        Execute the Lua ``script``, specifying the ``numkeys`` the script
        will touch and the key names and argument values in ``keys_and_args``.
        Returns the result of the script.

        In practice, use the object returned by ``register_script``. This
        function exists purely for Redis API completion.

        For more information see  https://redis.io/commands/eval
        """
    async def aeval_ro(self, script: str, numkeys: int, *keys_and_args: list) -> Union[Awaitable[str], str]:
        """
        The read-only variant of the EVAL command

        Execute the read-only Lua ``script`` specifying the ``numkeys`` the script
        will touch and the key names and argument values in ``keys_and_args``.
        Returns the result of the script.

        For more information see  https://redis.io/commands/eval_ro
        """
    async def aevalsha(self, sha: str, numkeys: int, *keys_and_args: list) -> Union[Awaitable[str], str]:
        """
        Use the ``sha`` to execute a Lua script already registered via EVAL
        or SCRIPT LOAD. Specify the ``numkeys`` the script will touch and the
        key names and argument values in ``keys_and_args``. Returns the result
        of the script.

        In practice, use the object returned by ``register_script``. This
        function exists purely for Redis API completion.

        For more information see  https://redis.io/commands/evalsha
        """
    async def aevalsha_ro(self, sha: str, numkeys: int, *keys_and_args: list) -> Union[Awaitable[str], str]:
        """
        The read-only variant of the EVALSHA command

        Use the ``sha`` to execute a read-only Lua script already registered via EVAL
        or SCRIPT LOAD. Specify the ``numkeys`` the script will touch and the
        key names and argument values in ``keys_and_args``. Returns the result
        of the script.

        For more information see  https://redis.io/commands/evalsha_ro
        """
    async def ascript_exists(self, *args: str) -> ResponseT:
        """
        Check if a script exists in the script cache by specifying the SHAs of
        each script as ``args``. Returns a list of boolean values indicating if
        if each already script exists in the cache.

        For more information see  https://redis.io/commands/script-exists
        """
    async def ascript_debug(self, *args) -> None: ...
    async def ascript_flush(self, sync_type: Union[Literal['SYNC'], Literal['ASYNC']] = None) -> ResponseT:
        """Flush all scripts from the script cache.

        ``sync_type`` is by default SYNC (synchronous) but it can also be
                      ASYNC.

        For more information see  https://redis.io/commands/script-flush
        """
    async def ascript_kill(self) -> ResponseT:
        """
        Kill the currently executing Lua script

        For more information see https://redis.io/commands/script-kill
        """
    async def ascript_load(self, script: ScriptTextT) -> ResponseT:
        """
        Load a Lua ``script`` into the script cache. Returns the SHA.

        For more information see https://redis.io/commands/script-load
        """
    async def aregister_script(self, script: ScriptTextT) -> Script:
        """
        Register a Lua ``script`` specifying the ``keys`` it will touch.
        Returns a Script object that is callable and hides the complexity of
        deal with scripts, keys, and shas. This is the preferred way to work
        with Lua scripts.
        """
    
    """
    Redis Geospatial commands.
    see: https://redis.com/redis-best-practices/indexing-patterns/geospatial/
    """
    async def ageoadd(self, name: KeyT, values: Sequence[EncodableT], nx: bool = False, xx: bool = False, ch: bool = False) -> ResponseT:
        """
        Add the specified geospatial items to the specified key identified
        by the ``name`` argument. The Geospatial items are given as ordered
        members of the ``values`` argument, each item or place is formed by
        the triad longitude, latitude and name.

        Note: You can use ZREM to remove elements.

        ``nx`` forces ZADD to only create new elements and not to update
        scores for elements that already exist.

        ``xx`` forces ZADD to only update scores of elements that already
        exist. New elements will not be added.

        ``ch`` modifies the return value to be the numbers of elements changed.
        Changed elements include new elements that were added and elements
        whose scores changed.

        For more information see https://redis.io/commands/geoadd
        """
    async def ageodist(self, name: KeyT, place1: FieldT, place2: FieldT, unit: Union[str, None] = None) -> ResponseT:
        """
        Return the distance between ``place1`` and ``place2`` members of the
        ``name`` key.
        The units must be one of the following : m, km mi, ft. By default
        meters are used.

        For more information see https://redis.io/commands/geodist
        """
    async def ageohash(self, name: KeyT, *values: FieldT) -> ResponseT:
        """
        Return the geo hash string for each item of ``values`` members of
        the specified key identified by the ``name`` argument.

        For more information see https://redis.io/commands/geohash
        """
    async def ageopos(self, name: KeyT, *values: FieldT) -> ResponseT:
        """
        Return the positions of each item of ``values`` as members of
        the specified key identified by the ``name`` argument. Each position
        is represented by the pairs lon and lat.

        For more information see https://redis.io/commands/geopos
        """
    async def ageoradius(self, name: KeyT, longitude: float, latitude: float, radius: float, unit: Union[str, None] = None, withdist: bool = False, withcoord: bool = False, withhash: bool = False, count: Union[int, None] = None, sort: Union[str, None] = None, store: Union[KeyT, None] = None, store_dist: Union[KeyT, None] = None, any: bool = False) -> ResponseT:
        """
        Return the members of the specified key identified by the
        ``name`` argument which are within the borders of the area specified
        with the ``latitude`` and ``longitude`` location and the maximum
        distance from the center specified by the ``radius`` value.

        The units must be one of the following : m, km mi, ft. By default

        ``withdist`` indicates to return the distances of each place.

        ``withcoord`` indicates to return the latitude and longitude of
        each place.

        ``withhash`` indicates to return the geohash string of each place.

        ``count`` indicates to return the number of elements up to N.

        ``sort`` indicates to return the places in a sorted way, ASC for
        nearest to fairest and DESC for fairest to nearest.

        ``store`` indicates to save the places names in a sorted set named
        with a specific key, each element of the destination sorted set is
        populated with the score got from the original geo sorted set.

        ``store_dist`` indicates to save the places names in a sorted set
        named with a specific key, instead of ``store`` the sorted set
        destination score is set with the distance.

        For more information see https://redis.io/commands/georadius
        """
    async def ageoradiusbymember(self, name: KeyT, member: FieldT, radius: float, unit: Union[str, None] = None, withdist: bool = False, withcoord: bool = False, withhash: bool = False, count: Union[int, None] = None, sort: Union[str, None] = None, store: Union[KeyT, None] = None, store_dist: Union[KeyT, None] = None, any: bool = False) -> ResponseT:
        """
        This command is exactly like ``georadius`` with the sole difference
        that instead of taking, as the center of the area to query, a longitude
        and latitude value, it takes the name of a member already existing
        inside the geospatial index represented by the sorted set.

        For more information see https://redis.io/commands/georadiusbymember
        """
    async def ageosearch(self, name: KeyT, member: Union[FieldT, None] = None, longitude: Union[float, None] = None, latitude: Union[float, None] = None, unit: str = 'm', radius: Union[float, None] = None, width: Union[float, None] = None, height: Union[float, None] = None, sort: Union[str, None] = None, count: Union[int, None] = None, any: bool = False, withcoord: bool = False, withdist: bool = False, withhash: bool = False) -> ResponseT:
        """
        Return the members of specified key identified by the
        ``name`` argument, which are within the borders of the
        area specified by a given shape. This command extends the
        GEORADIUS command, so in addition to searching within circular
        areas, it supports searching within rectangular areas.

        This command should be used in place of the deprecated
        GEORADIUS and GEORADIUSBYMEMBER commands.

        ``member`` Use the position of the given existing
         member in the sorted set. Can't be given with ``longitude``
         and ``latitude``.

        ``longitude`` and ``latitude`` Use the position given by
        this coordinates. Can't be given with ``member``
        ``radius`` Similar to GEORADIUS, search inside circular
        area according the given radius. Can't be given with
        ``height`` and ``width``.
        ``height`` and ``width`` Search inside an axis-aligned
        rectangle, determined by the given height and width.
        Can't be given with ``radius``

        ``unit`` must be one of the following : m, km, mi, ft.
        `m` for meters (the default value), `km` for kilometers,
        `mi` for miles and `ft` for feet.

        ``sort`` indicates to return the places in a sorted way,
        ASC for nearest to furthest and DESC for furthest to nearest.

        ``count`` limit the results to the first count matching items.

        ``any`` is set to True, the command will return as soon as
        enough matches are found. Can't be provided without ``count``

        ``withdist`` indicates to return the distances of each place.
        ``withcoord`` indicates to return the latitude and longitude of
        each place.

        ``withhash`` indicates to return the geohash string of each place.

        For more information see https://redis.io/commands/geosearch
        """
    async def ageosearchstore(self, dest: KeyT, name: KeyT, member: Union[FieldT, None] = None, longitude: Union[float, None] = None, latitude: Union[float, None] = None, unit: str = 'm', radius: Union[float, None] = None, width: Union[float, None] = None, height: Union[float, None] = None, sort: Union[str, None] = None, count: Union[int, None] = None, any: bool = False, storedist: bool = False) -> ResponseT:
        """
        This command is like GEOSEARCH, but stores the result in
        ``dest``. By default, it stores the results in the destination
        sorted set with their geospatial information.
        if ``store_dist`` set to True, the command will stores the
        items in a sorted set populated with their distance from the
        center of the circle or box, as a floating-point number.

        For more information see https://redis.io/commands/geosearchstore
        """

    """
    Redis Module commands.
    see: https://redis.io/topics/modules-intro
    """
    async def amodule_load(self, path, *args) -> ResponseT:
        """
        Loads the module from ``path``.
        Passes all ``*args`` to the module, during loading.
        Raises ``ModuleError`` if a module is not found at ``path``.

        For more information see https://redis.io/commands/module-load
        """
    async def amodule_loadex(self, path: str, options: Optional[List[str]] = None, args: Optional[List[str]] = None) -> ResponseT:
        """
        Loads a module from a dynamic library at runtime with configuration directives.

        For more information see https://redis.io/commands/module-loadex
        """
    async def amodule_unload(self, name) -> ResponseT:
        """
        Unloads the module ``name``.
        Raises ``ModuleError`` if ``name`` is not in loaded modules.

        For more information see https://redis.io/commands/module-unload
        """
    async def amodule_list(self) -> ResponseT:
        """
        Returns a list of dictionaries containing the name and version of
        all loaded modules.

        For more information see https://redis.io/commands/module-list
        """
    async def acommand_info(self) -> None: ...
    async def acommand_count(self) -> ResponseT: ...
    async def acommand_getkeys(self, *args) -> ResponseT: ...
    async def acommand(self) -> ResponseT: ...


    """
    Class for Redis Cluster commands
    """
    async def acluster(self, cluster_arg, *args, **kwargs) -> ResponseT: ...
    async def areadwrite(self, **kwargs) -> ResponseT:
        """
        Disables read queries for a connection to a Redis Cluster slave node.

        For more information see https://redis.io/commands/readwrite
        """
    async def areadonly(self, **kwargs) -> ResponseT:
        """
        Enables read queries for a connection to a Redis Cluster replica node.

        For more information see https://redis.io/commands/readonly
        """
    
    """
    Redis Function commands
    """
    async def afunction_load(self, code: str, replace: Optional[bool] = False) -> Union[Awaitable[str], str]:
        """
        Load a library to Redis.
        :param code: the source code (must start with
        Shebang statement that provides a metadata about the library)
        :param replace: changes the behavior to overwrite the existing library
        with the new contents.
        Return the library name that was loaded.

        For more information see https://redis.io/commands/function-load
        """
    async def afunction_delete(self, library: str) -> Union[Awaitable[str], str]:
        """
        Delete the library called ``library`` and all its functions.

        For more information see https://redis.io/commands/function-delete
        """
    async def afunction_flush(self, mode: str = 'SYNC') -> Union[Awaitable[str], str]:
        """
        Deletes all the libraries.

        For more information see https://redis.io/commands/function-flush
        """
    async def afunction_list(self, library: Optional[str] = '*', withcode: Optional[bool] = False) -> Union[Awaitable[List], List]:
        """
        Return information about the functions and libraries.
        :param library: pecify a pattern for matching library names
        :param withcode: cause the server to include the libraries source
         implementation in the reply
        """
    async def afcall(self, function, numkeys: int, *keys_and_args: Optional[List]) -> Union[Awaitable[str], str]:
        """
        Invoke a function.

        For more information see https://redis.io/commands/fcall
        """
    async def afcall_ro(self, function, numkeys: int, *keys_and_args: Optional[List]) -> Union[Awaitable[str], str]:
        """
        This is a read-only variant of the FCALL command that cannot
        execute commands that modify data.

        For more information see https://redis.io/commands/fcal_ro
        """
    async def afunction_dump(self) -> Union[Awaitable[str], str]:
        """
        Return the serialized payload of loaded libraries.

        For more information see https://redis.io/commands/function-dump
        """
    async def afunction_restore(self, payload: str, policy: Optional[str] = 'APPEND') -> Union[Awaitable[str], str]:
        """
        Restore libraries from the serialized ``payload``.
        You can use the optional policy argument to provide a policy
        for handling existing libraries.

        For more information see https://redis.io/commands/function-restore
        """
    async def afunction_kill(self) -> Union[Awaitable[str], str]:
        """
        Kill a function that is currently executing.

        For more information see https://redis.io/commands/function-kill
        """
    async def afunction_stats(self) -> Union[Awaitable[List], List]:
        """
        Return information about the function that's currently running
        and information about the available execution engines.

        For more information see https://redis.io/commands/function-stats
        """

    async def atfunction_load(self, lib_code: str, replace: bool = False, config: Union[str, None] = None) -> ResponseT:
        """
        Load a new library to RedisGears.

        ``lib_code`` - the library code.
        ``config`` - a string representation of a JSON object
        that will be provided to the library on load time,
        for more information refer to
        https://github.com/RedisGears/RedisGears/blob/master/docs/function_advance_topics.md#library-configuration
        ``replace`` - an optional argument, instructs RedisGears to replace the
        function if its already exists

        For more information see https://redis.io/commands/tfunction-load/
        """
    async def atfunction_delete(self, lib_name: str) -> ResponseT:
        """
        Delete a library from RedisGears.

        ``lib_name`` the library name to delete.

        For more information see https://redis.io/commands/tfunction-delete/
        """
    async def atfunction_list(self, with_code: bool = False, verbose: int = 0, lib_name: Union[str, None] = None) -> ResponseT:
        """
        List the functions with additional information about each function.

        ``with_code`` Show libraries code.
        ``verbose`` output verbosity level, higher number will increase verbosity level
        ``lib_name`` specifying a library name (can be used multiple times to show multiple libraries in a single command) # noqa

        For more information see https://redis.io/commands/tfunction-list/
        """
    async def atfcall(self, lib_name: str, func_name: str, keys: KeysT = None, *args: List) -> ResponseT:
        """
        Invoke a function.

        ``lib_name`` - the library name contains the function.
        ``func_name`` - the function name to run.
        ``keys`` - the keys that will be touched by the function.
        ``args`` - Additional argument to pass to the function.

        For more information see https://redis.io/commands/tfcall/
        """
    async def atfcall_async(self, lib_name: str, func_name: str, keys: KeysT = None, *args: List) -> ResponseT:
        """
        Invoke an async function (coroutine).

        ``lib_name`` - the library name contains the function.
        ``func_name`` - the function name to run.
        ``keys`` - the keys that will be touched by the function.
        ``args`` - Additional argument to pass to the function.

        For more information see https://redis.io/commands/tfcall/
        """
        """
    ACL Commands
    """

    def acl_cat(self, category: Union[str, None] = None, **kwargs) -> ResponseT:
        """
        Returns a list of categories or commands within a category.

        If ``category`` is not supplied, returns a list of all categories.
        If ``category`` is supplied, returns a list of all commands within
        that category.

        For more information see https://redis.io/commands/acl-cat
        """
    def acl_dryrun(self, username, *args, **kwargs):
        """
        Simulate the execution of a given command by a given ``username``.

        For more information see https://redis.io/commands/acl-dryrun
        """
    def acl_deluser(self, *username: str, **kwargs) -> ResponseT:
        """
        Delete the ACL for the specified ``username``s

        For more information see https://redis.io/commands/acl-deluser
        """
    def acl_genpass(self, bits: Union[int, None] = None, **kwargs) -> ResponseT:
        """Generate a random password value.
        If ``bits`` is supplied then use this number of bits, rounded to
        the next multiple of 4.
        See: https://redis.io/commands/acl-genpass
        """
    def acl_getuser(self, username: str, **kwargs) -> ResponseT:
        """
        Get the ACL details for the specified ``username``.

        If ``username`` does not exist, return None

        For more information see https://redis.io/commands/acl-getuser
        """
    def acl_help(self, **kwargs) -> ResponseT:
        """The ACL HELP command returns helpful text describing
        the different subcommands.

        For more information see https://redis.io/commands/acl-help
        """
    def acl_list(self, **kwargs) -> ResponseT:
        """
        Return a list of all ACLs on the server

        For more information see https://redis.io/commands/acl-list
        """
    def acl_log(self, count: Union[int, None] = None, **kwargs) -> ResponseT:
        """
        Get ACL logs as a list.
        :param int count: Get logs[0:count].
        :rtype: List.

        For more information see https://redis.io/commands/acl-log
        """
    def acl_log_reset(self, **kwargs) -> ResponseT:
        """
        Reset ACL logs.
        :rtype: Boolean.

        For more information see https://redis.io/commands/acl-log
        """
    def acl_load(self, **kwargs) -> ResponseT:
        """
        Load ACL rules from the configured ``aclfile``.

        Note that the server must be configured with the ``aclfile``
        directive to be able to load ACL rules from an aclfile.

        For more information see https://redis.io/commands/acl-load
        """
    def acl_save(self, **kwargs) -> ResponseT:
        """
        Save ACL rules to the configured ``aclfile``.

        Note that the server must be configured with the ``aclfile``
        directive to be able to save ACL rules to an aclfile.

        For more information see https://redis.io/commands/acl-save
        """
    def acl_setuser(self, username: str, enabled: bool = False, nopass: bool = False, passwords: Union[str, Iterable[str], None] = None, hashed_passwords: Union[str, Iterable[str], None] = None, categories: Optional[Iterable[str]] = None, commands: Optional[Iterable[str]] = None, keys: Optional[Iterable[KeyT]] = None, channels: Optional[Iterable[ChannelT]] = None, selectors: Optional[Iterable[Tuple[str, KeyT]]] = None, reset: bool = False, reset_keys: bool = False, reset_channels: bool = False, reset_passwords: bool = False, **kwargs) -> ResponseT:
        """
        Create or update an ACL user.

        Create or update the ACL for ``username``. If the user already exists,
        the existing ACL is completely overwritten and replaced with the
        specified values.

        ``enabled`` is a boolean indicating whether the user should be allowed
        to authenticate or not. Defaults to ``False``.

        ``nopass`` is a boolean indicating whether the can authenticate without
        a password. This cannot be True if ``passwords`` are also specified.

        ``passwords`` if specified is a list of plain text passwords
        to add to or remove from the user. Each password must be prefixed with
        a '+' to add or a '-' to remove. For convenience, the value of
        ``passwords`` can be a simple prefixed string when adding or
        removing a single password.

        ``hashed_passwords`` if specified is a list of SHA-256 hashed passwords
        to add to or remove from the user. Each hashed password must be
        prefixed with a '+' to add or a '-' to remove. For convenience,
        the value of ``hashed_passwords`` can be a simple prefixed string when
        adding or removing a single password.

        ``categories`` if specified is a list of strings representing category
        permissions. Each string must be prefixed with either a '+' to add the
        category permission or a '-' to remove the category permission.

        ``commands`` if specified is a list of strings representing command
        permissions. Each string must be prefixed with either a '+' to add the
        command permission or a '-' to remove the command permission.

        ``keys`` if specified is a list of key patterns to grant the user
        access to. Keys patterns allow '*' to support wildcard matching. For
        example, '*' grants access to all keys while 'cache:*' grants access
        to all keys that are prefixed with 'cache:'. ``keys`` should not be
        prefixed with a '~'.

        ``reset`` is a boolean indicating whether the user should be fully
        reset prior to applying the new ACL. Setting this to True will
        remove all existing passwords, flags and privileges from the user and
        then apply the specified rules. If this is False, the user's existing
        passwords, flags and privileges will be kept and any new specified
        rules will be applied on top.

        ``reset_keys`` is a boolean indicating whether the user's key
        permissions should be reset prior to applying any new key permissions
        specified in ``keys``. If this is False, the user's existing
        key permissions will be kept and any new specified key permissions
        will be applied on top.

        ``reset_channels`` is a boolean indicating whether the user's channel
        permissions should be reset prior to applying any new channel permissions
        specified in ``channels``.If this is False, the user's existing
        channel permissions will be kept and any new specified channel permissions
        will be applied on top.

        ``reset_passwords`` is a boolean indicating whether to remove all
        existing passwords and the 'nopass' flag from the user prior to
        applying any new passwords specified in 'passwords' or
        'hashed_passwords'. If this is False, the user's existing passwords
        and 'nopass' status will be kept and any new specified passwords
        or hashed_passwords will be applied on top.

        For more information see https://redis.io/commands/acl-setuser
        """
    def acl_users(self, **kwargs) -> ResponseT:
        """Returns a list of all registered users on the server.

        For more information see https://redis.io/commands/acl-users
        """
    def acl_whoami(self, **kwargs) -> ResponseT:
        """Get the username for the current connection

        For more information see https://redis.io/commands/acl-whoami
        """

    """
    Redis management commands
    """
    def auth(self, password: str, username: Optional[str] = None, **kwargs):
        '''
        Authenticates the user. If you do not pass username, Redis will try to
        authenticate for the "default" user. If you do pass username, it will
        authenticate for the given user.
        For more information see https://redis.io/commands/auth
        '''
    def bgrewriteaof(self, **kwargs):
        """Tell the Redis server to rewrite the AOF file from data in memory.

        For more information see https://redis.io/commands/bgrewriteaof
        """
    def bgsave(self, schedule: bool = True, **kwargs) -> ResponseT:
        """
        Tell the Redis server to save its data to disk.  Unlike save(),
        this method is asynchronous and returns immediately.

        For more information see https://redis.io/commands/bgsave
        """
    def role(self) -> ResponseT:
        """
        Provide information on the role of a Redis instance in
        the context of replication, by returning if the instance
        is currently a master, slave, or sentinel.

        For more information see https://redis.io/commands/role
        """
    def client_kill(self, address: str, **kwargs) -> ResponseT:
        """Disconnects the client at ``address`` (ip:port)

        For more information see https://redis.io/commands/client-kill
        """
    def client_kill_filter(self, _id: Union[str, None] = None, _type: Union[str, None] = None, addr: Union[str, None] = None, skipme: Union[bool, None] = None, laddr: Union[bool, None] = None, user: str = None, **kwargs) -> ResponseT:
        """
        Disconnects client(s) using a variety of filter options
        :param _id: Kills a client by its unique ID field
        :param _type: Kills a client by type where type is one of 'normal',
        'master', 'slave' or 'pubsub'
        :param addr: Kills a client by its 'address:port'
        :param skipme: If True, then the client calling the command
        will not get killed even if it is identified by one of the filter
        options. If skipme is not provided, the server defaults to skipme=True
        :param laddr: Kills a client by its 'local (bind) address:port'
        :param user: Kills a client for a specific user name
        """
    def client_info(self, **kwargs) -> ResponseT:
        """
        Returns information and statistics about the current
        client connection.

        For more information see https://redis.io/commands/client-info
        """
    def client_list(self, _type: Union[str, None] = None, client_id: List[EncodableT] = [], **kwargs) -> ResponseT:
        """
        Returns a list of currently connected clients.
        If type of client specified, only that type will be returned.

        :param _type: optional. one of the client types (normal, master,
         replica, pubsub)
        :param client_id: optional. a list of client ids

        For more information see https://redis.io/commands/client-list
        """
    def client_getname(self, **kwargs) -> ResponseT:
        """
        Returns the current connection name

        For more information see https://redis.io/commands/client-getname
        """
    def client_getredir(self, **kwargs) -> ResponseT:
        """
        Returns the ID (an integer) of the client to whom we are
        redirecting tracking notifications.

        see: https://redis.io/commands/client-getredir
        """
    def client_reply(self, reply: Union[Literal['ON'], Literal['OFF'], Literal['SKIP']], **kwargs) -> ResponseT:
        """
        Enable and disable redis server replies.

        ``reply`` Must be ON OFF or SKIP,
        ON - The default most with server replies to commands
        OFF - Disable server responses to commands
        SKIP - Skip the response of the immediately following command.

        Note: When setting OFF or SKIP replies, you will need a client object
        with a timeout specified in seconds, and will need to catch the
        TimeoutError.
        The test_client_reply unit test illustrates this, and
        conftest.py has a client with a timeout.

        See https://redis.io/commands/client-reply
        """
    def client_id(self, **kwargs) -> ResponseT:
        """
        Returns the current connection id

        For more information see https://redis.io/commands/client-id
        """
    def client_tracking_on(self, clientid: Union[int, None] = None, prefix: Sequence[KeyT] = [], bcast: bool = False, optin: bool = False, optout: bool = False, noloop: bool = False) -> ResponseT:
        """
        Turn on the tracking mode.
        For more information about the options look at client_tracking func.

        See https://redis.io/commands/client-tracking
        """
    def client_tracking_off(self, clientid: Union[int, None] = None, prefix: Sequence[KeyT] = [], bcast: bool = False, optin: bool = False, optout: bool = False, noloop: bool = False) -> ResponseT:
        """
        Turn off the tracking mode.
        For more information about the options look at client_tracking func.

        See https://redis.io/commands/client-tracking
        """
    def client_tracking(self, on: bool = True, clientid: Union[int, None] = None, prefix: Sequence[KeyT] = [], bcast: bool = False, optin: bool = False, optout: bool = False, noloop: bool = False, **kwargs) -> ResponseT:
        """
        Enables the tracking feature of the Redis server, that is used
        for server assisted client side caching.

        ``on`` indicate for tracking on or tracking off. The dafualt is on.

        ``clientid`` send invalidation messages to the connection with
        the specified ID.

        ``bcast`` enable tracking in broadcasting mode. In this mode
        invalidation messages are reported for all the prefixes
        specified, regardless of the keys requested by the connection.

        ``optin``  when broadcasting is NOT active, normally don't track
        keys in read only commands, unless they are called immediately
        after a CLIENT CACHING yes command.

        ``optout`` when broadcasting is NOT active, normally track keys in
        read only commands, unless they are called immediately after a
        CLIENT CACHING no command.

        ``noloop`` don't send notifications about keys modified by this
        connection itself.

        ``prefix``  for broadcasting, register a given key prefix, so that
        notifications will be provided only for keys starting with this string.

        See https://redis.io/commands/client-tracking
        """
    def client_trackinginfo(self, **kwargs) -> ResponseT:
        """
        Returns the information about the current client connection's
        use of the server assisted client side cache.

        See https://redis.io/commands/client-trackinginfo
        """
    def client_setname(self, name: str, **kwargs) -> ResponseT:
        """
        Sets the current connection name

        For more information see https://redis.io/commands/client-setname

        .. note::
           This method sets client name only for **current** connection.

           If you want to set a common name for all connections managed
           by this client, use ``client_name`` constructor argument.
        """
    def client_setinfo(self, attr: str, value: str, **kwargs) -> ResponseT:
        """
        Sets the current connection library name or version
        For mor information see https://redis.io/commands/client-setinfo
        """
    def client_unblock(self, client_id: int, error: bool = False, **kwargs) -> ResponseT:
        """
        Unblocks a connection by its client id.
        If ``error`` is True, unblocks the client with a special error message.
        If ``error`` is False (default), the client is unblocked using the
        regular timeout mechanism.

        For more information see https://redis.io/commands/client-unblock
        """
    def client_pause(self, timeout: int, all: bool = True, **kwargs) -> ResponseT:
        """
        Suspend all the Redis clients for the specified amount of time.


        For more information see https://redis.io/commands/client-pause

        :param timeout: milliseconds to pause clients
        :param all: If true (default) all client commands are blocked.
        otherwise, clients are only blocked if they attempt to execute
        a write command.
        For the WRITE mode, some commands have special behavior:
        EVAL/EVALSHA: Will block client for all scripts.
        PUBLISH: Will block client.
        PFCOUNT: Will block client.
        WAIT: Acknowledgments will be delayed, so this command will
        appear blocked.
        """
    def client_unpause(self, **kwargs) -> ResponseT:
        """
        Unpause all redis clients

        For more information see https://redis.io/commands/client-unpause
        """
    def client_no_evict(self, mode: str) -> Union[Awaitable[str], str]:
        """
        Sets the client eviction mode for the current connection.

        For more information see https://redis.io/commands/client-no-evict
        """
    def client_no_touch(self, mode: str) -> Union[Awaitable[str], str]:
        """
        # The command controls whether commands sent by the client will alter
        # the LRU/LFU of the keys they access.
        # When turned on, the current client will not change LFU/LRU stats,
        # unless it sends the TOUCH command.

        For more information see https://redis.io/commands/client-no-touch
        """
    def command(self, **kwargs):
        """
        Returns dict reply of details about all Redis commands.

        For more information see https://redis.io/commands/command
        """
    def command_info(self, **kwargs) -> None: ...
    def command_count(self, **kwargs) -> ResponseT: ...
    def command_list(self, module: Optional[str] = None, category: Optional[str] = None, pattern: Optional[str] = None) -> ResponseT:
        """
        Return an array of the server's command names.
        You can use one of the following filters:
        ``module``: get the commands that belong to the module
        ``category``: get the commands in the ACL category
        ``pattern``: get the commands that match the given pattern

        For more information see https://redis.io/commands/command-list/
        """
    def command_getkeysandflags(self, *args: List[str]) -> List[Union[str, List[str]]]:
        """
        Returns array of keys from a full Redis command and their usage flags.

        For more information see https://redis.io/commands/command-getkeysandflags
        """
    def command_docs(self, *args) -> None:
        """
        This function throws a NotImplementedError since it is intentionally
        not supported.
        """
    def config_get(self, pattern: PatternT = '*', *args: List[PatternT], **kwargs) -> ResponseT:
        """
        Return a dictionary of configuration based on the ``pattern``

        For more information see https://redis.io/commands/config-get
        """
    def config_set(self, name: KeyT, value: EncodableT, *args: List[Union[KeyT, EncodableT]], **kwargs) -> ResponseT:
        """Set config item ``name`` with ``value``

        For more information see https://redis.io/commands/config-set
        """
    def config_resetstat(self, **kwargs) -> ResponseT:
        """
        Reset runtime statistics

        For more information see https://redis.io/commands/config-resetstat
        """
    def config_rewrite(self, **kwargs) -> ResponseT:
        """
        Rewrite config file with the minimal change to reflect running config.

        For more information see https://redis.io/commands/config-rewrite
        """
    def dbsize(self, **kwargs) -> ResponseT:
        """
        Returns the number of keys in the current database

        For more information see https://redis.io/commands/dbsize
        """
    def debug_object(self, key: KeyT, **kwargs) -> ResponseT:
        """
        Returns version specific meta information about a given key

        For more information see https://redis.io/commands/debug-object
        """
    def debug_segfault(self, **kwargs) -> None: ...
    def echo(self, value: EncodableT, **kwargs) -> ResponseT:
        """
        Echo the string back from the server

        For more information see https://redis.io/commands/echo
        """
    def flushall(self, asynchronous: bool = False, **kwargs) -> ResponseT:
        """
        Delete all keys in all databases on the current host.

        ``asynchronous`` indicates whether the operation is
        executed asynchronously by the server.

        For more information see https://redis.io/commands/flushall
        """
    def flushdb(self, asynchronous: bool = False, **kwargs) -> ResponseT:
        """
        Delete all keys in the current database.

        ``asynchronous`` indicates whether the operation is
        executed asynchronously by the server.

        For more information see https://redis.io/commands/flushdb
        """
    def sync(self) -> ResponseT:
        """
        Initiates a replication stream from the master.

        For more information see https://redis.io/commands/sync
        """
    def psync(self, replicationid: str, offset: int):
        """
        Initiates a replication stream from the master.
        Newer version for `sync`.

        For more information see https://redis.io/commands/sync
        """
    def swapdb(self, first: int, second: int, **kwargs) -> ResponseT:
        """
        Swap two databases

        For more information see https://redis.io/commands/swapdb
        """
    def select(self, index: int, **kwargs) -> ResponseT:
        """Select the Redis logical database at index.

        See: https://redis.io/commands/select
        """
    def info(self, section: Union[str, None] = None, *args: List[str], **kwargs) -> ResponseT:
        """
        Returns a dictionary containing information about the Redis server

        The ``section`` option can be used to select a specific section
        of information

        The section option is not supported by older versions of Redis Server,
        and will generate ResponseError

        For more information see https://redis.io/commands/info
        """
    def lastsave(self, **kwargs) -> ResponseT:
        """
        Return a Python datetime object representing the last time the
        Redis database was saved to disk

        For more information see https://redis.io/commands/lastsave
        """
    def latency_doctor(self) -> None:
        """Raise a NotImplementedError, as the client will not support LATENCY DOCTOR.
        This funcion is best used within the redis-cli.

        For more information see https://redis.io/commands/latency-doctor
        """
    def latency_graph(self) -> None:
        """Raise a NotImplementedError, as the client will not support LATENCY GRAPH.
        This funcion is best used within the redis-cli.

        For more information see https://redis.io/commands/latency-graph.
        """
    def lolwut(self, *version_numbers: Union[str, float], **kwargs) -> ResponseT:
        """
        Get the Redis version and a piece of generative computer art

        See: https://redis.io/commands/lolwut
        """
    def reset(self) -> ResponseT:
        """Perform a full reset on the connection's server side contenxt.

        See: https://redis.io/commands/reset
        """
    def migrate(self, host: str, port: int, keys: KeysT, destination_db: int, timeout: int, copy: bool = False, replace: bool = False, auth: Union[str, None] = None, **kwargs) -> ResponseT:
        """
        Migrate 1 or more keys from the current Redis server to a different
        server specified by the ``host``, ``port`` and ``destination_db``.

        The ``timeout``, specified in milliseconds, indicates the maximum
        time the connection between the two servers can be idle before the
        command is interrupted.

        If ``copy`` is True, the specified ``keys`` are NOT deleted from
        the source server.

        If ``replace`` is True, this operation will overwrite the keys
        on the destination server if they exist.

        If ``auth`` is specified, authenticate to the destination server with
        the password provided.

        For more information see https://redis.io/commands/migrate
        """
    def object(self, infotype: str, key: KeyT, **kwargs) -> ResponseT:
        """
        Return the encoding, idletime, or refcount about the key
        """
    def memory_doctor(self, **kwargs) -> None: ...
    def memory_help(self, **kwargs) -> None: ...
    def memory_stats(self, **kwargs) -> ResponseT:
        """
        Return a dictionary of memory stats

        For more information see https://redis.io/commands/memory-stats
        """
    def memory_malloc_stats(self, **kwargs) -> ResponseT:
        """
        Return an internal statistics report from the memory allocator.

        See: https://redis.io/commands/memory-malloc-stats
        """
    def memory_usage(self, key: KeyT, samples: Union[int, None] = None, **kwargs) -> ResponseT:
        """
        Return the total memory usage for key, its value and associated
        administrative overheads.

        For nested data structures, ``samples`` is the number of elements to
        sample. If left unspecified, the server's default is 5. Use 0 to sample
        all elements.

        For more information see https://redis.io/commands/memory-usage
        """
    def memory_purge(self, **kwargs) -> ResponseT:
        """
        Attempts to purge dirty pages for reclamation by allocator

        For more information see https://redis.io/commands/memory-purge
        """
    def latency_histogram(self, *args) -> None:
        """
        This function throws a NotImplementedError since it is intentionally
        not supported.
        """
    def latency_history(self, event: str) -> ResponseT:
        """
        Returns the raw data of the ``event``'s latency spikes time series.

        For more information see https://redis.io/commands/latency-history
        """
    def latency_latest(self) -> ResponseT:
        """
        Reports the latest latency events logged.

        For more information see https://redis.io/commands/latency-latest
        """
    def latency_reset(self, *events: str) -> ResponseT:
        """
        Resets the latency spikes time series of all, or only some, events.

        For more information see https://redis.io/commands/latency-reset
        """
    def ping(self, **kwargs) -> ResponseT:
        """
        Ping the Redis server

        For more information see https://redis.io/commands/ping
        """
    def quit(self, **kwargs) -> ResponseT:
        """
        Ask the server to close the connection.

        For more information see https://redis.io/commands/quit
        """
    def replicaof(self, *args, **kwargs) -> ResponseT:
        """
        Update the replication settings of a redis replica, on the fly.

        Examples of valid arguments include:

        NO ONE (set no replication)
        host port (set to the host and port of a redis server)

        For more information see  https://redis.io/commands/replicaof
        """
    def save(self, **kwargs) -> ResponseT:
        """
        Tell the Redis server to save its data to disk,
        blocking until the save is complete

        For more information see https://redis.io/commands/save
        """
    def shutdown(self, save: bool = False, nosave: bool = False, now: bool = False, force: bool = False, abort: bool = False, **kwargs) -> None:
        """Shutdown the Redis server.  If Redis has persistence configured,
        data will be flushed before shutdown.
        It is possible to specify modifiers to alter the behavior of the command:
        ``save`` will force a DB saving operation even if no save points are configured.
        ``nosave`` will prevent a DB saving operation even if one or more save points
        are configured.
        ``now`` skips waiting for lagging replicas, i.e. it bypasses the first step in
        the shutdown sequence.
        ``force`` ignores any errors that would normally prevent the server from exiting
        ``abort`` cancels an ongoing shutdown and cannot be combined with other flags.

        For more information see https://redis.io/commands/shutdown
        """
    def slaveof(self, host: Union[str, None] = None, port: Union[int, None] = None, **kwargs) -> ResponseT:
        """
        Set the server to be a replicated slave of the instance identified
        by the ``host`` and ``port``. If called without arguments, the
        instance is promoted to a master instead.

        For more information see https://redis.io/commands/slaveof
        """
    def slowlog_get(self, num: Union[int, None] = None, **kwargs) -> ResponseT:
        """
        Get the entries from the slowlog. If ``num`` is specified, get the
        most recent ``num`` items.

        For more information see https://redis.io/commands/slowlog-get
        """
    def slowlog_len(self, **kwargs) -> ResponseT:
        """
        Get the number of items in the slowlog

        For more information see https://redis.io/commands/slowlog-len
        """
    def slowlog_reset(self, **kwargs) -> ResponseT:
        """
        Remove all items in the slowlog

        For more information see https://redis.io/commands/slowlog-reset
        """
    def time(self, **kwargs) -> ResponseT:
        """
        Returns the server time as a 2-item tuple of ints:
        (seconds since epoch, microseconds into this second).

        For more information see https://redis.io/commands/time
        """
    def wait(self, num_replicas: int, timeout: int, **kwargs) -> ResponseT:
        """
        Redis synchronous replication
        That returns the number of replicas that processed the query when
        we finally have at least ``num_replicas``, or when the ``timeout`` was
        reached.

        For more information see https://redis.io/commands/wait
        """
    def waitaof(self, num_local: int, num_replicas: int, timeout: int, **kwargs) -> ResponseT:
        """
        This command blocks the current client until all previous write
        commands by that client are acknowledged as having been fsynced
        to the AOF of the local Redis and/or at least the specified number
        of replicas.

        For more information see https://redis.io/commands/waitaof
        """
    def hello(self) -> None:
        """
        This function throws a NotImplementedError since it is intentionally
        not supported.
        """
    def failover(self) -> None:
        """
        This function throws a NotImplementedError since it is intentionally
        not supported.
        """
    def reset(self) -> None:
        """
        Reset the state of the instance to when it was constructed
        """
    def overflow(self, overflow: str):
        """
        Update the overflow algorithm of successive INCRBY operations
        :param overflow: Overflow algorithm, one of WRAP, SAT, FAIL. See the
            Redis docs for descriptions of these algorithmsself.
        :returns: a :py:class:`BitFieldOperation` instance.
        """
    def incrby(self, fmt: str, offset: BitfieldOffsetT, increment: int, overflow: Union[str, None] = None):
        """
        Increment a bitfield by a given amount.
        :param fmt: format-string for the bitfield being updated, e.g. 'u8'
            for an unsigned 8-bit integer.
        :param offset: offset (in number of bits). If prefixed with a
            '#', this is an offset multiplier, e.g. given the arguments
            fmt='u8', offset='#2', the offset will be 16.
        :param int increment: value to increment the bitfield by.
        :param str overflow: overflow algorithm. Defaults to WRAP, but other
            acceptable values are SAT and FAIL. See the Redis docs for
            descriptions of these algorithms.
        :returns: a :py:class:`BitFieldOperation` instance.
        """
    def get(self, fmt: str, offset: BitfieldOffsetT):
        """
        Get the value of a given bitfield.
        :param fmt: format-string for the bitfield being read, e.g. 'u8' for
            an unsigned 8-bit integer.
        :param offset: offset (in number of bits). If prefixed with a
            '#', this is an offset multiplier, e.g. given the arguments
            fmt='u8', offset='#2', the offset will be 16.
        :returns: a :py:class:`BitFieldOperation` instance.
        """
    def set(self, fmt: str, offset: BitfieldOffsetT, value: int):
        """
        Set the value of a given bitfield.
        :param fmt: format-string for the bitfield being read, e.g. 'u8' for
            an unsigned 8-bit integer.
        :param offset: offset (in number of bits). If prefixed with a
            '#', this is an offset multiplier, e.g. given the arguments
            fmt='u8', offset='#2', the offset will be 16.
        :param int value: value to set at the given position.
        :returns: a :py:class:`BitFieldOperation` instance.
        """
    

    """
    Redis basic key-based commands
    """
    def append(self, key: KeyT, value: EncodableT) -> ResponseT:
        """
        Appends the string ``value`` to the value at ``key``. If ``key``
        doesn't already exist, create it with a value of ``value``.
        Returns the new length of the value at ``key``.

        For more information see https://redis.io/commands/append
        """
    def bitcount(self, key: KeyT, start: Union[int, None] = None, end: Union[int, None] = None, mode: Optional[str] = None) -> ResponseT:
        """
        Returns the count of set bits in the value of ``key``.  Optional
        ``start`` and ``end`` parameters indicate which bytes to consider

        For more information see https://redis.io/commands/bitcount
        """
    def bitfield(self, key: KeyT, default_overflow: Union[str, None] = None) -> BitFieldOperation:
        """
        Return a BitFieldOperation instance to conveniently construct one or
        more bitfield operations on ``key``.

        For more information see https://redis.io/commands/bitfield
        """
    def bitfield_ro(self, key: KeyT, encoding: str, offset: BitfieldOffsetT, items: Optional[list] = None) -> ResponseT:
        """
        Return an array of the specified bitfield values
        where the first value is found using ``encoding`` and ``offset``
        parameters and remaining values are result of corresponding
        encoding/offset pairs in optional list ``items``
        Read-only variant of the BITFIELD command.

        For more information see https://redis.io/commands/bitfield_ro
        """
    def bitop(self, operation: str, dest: KeyT, *keys: KeyT) -> ResponseT:
        """
        Perform a bitwise operation using ``operation`` between ``keys`` and
        store the result in ``dest``.

        For more information see https://redis.io/commands/bitop
        """
    def bitpos(self, key: KeyT, bit: int, start: Union[int, None] = None, end: Union[int, None] = None, mode: Optional[str] = None) -> ResponseT:
        """
        Return the position of the first bit set to 1 or 0 in a string.
        ``start`` and ``end`` defines search range. The range is interpreted
        as a range of bytes and not a range of bits, so start=0 and end=2
        means to look at the first three bytes.

        For more information see https://redis.io/commands/bitpos
        """
    def copy(self, source: str, destination: str, destination_db: Union[str, None] = None, replace: bool = False) -> ResponseT:
        """
        Copy the value stored in the ``source`` key to the ``destination`` key.

        ``destination_db`` an alternative destination database. By default,
        the ``destination`` key is created in the source Redis database.

        ``replace`` whether the ``destination`` key should be removed before
        copying the value to it. By default, the value is not copied if
        the ``destination`` key already exists.

        For more information see https://redis.io/commands/copy
        """
    def decrby(self, name: KeyT, amount: int = 1) -> ResponseT:
        """
        Decrements the value of ``key`` by ``amount``.  If no key exists,
        the value will be initialized as 0 - ``amount``

        For more information see https://redis.io/commands/decrby
        """
    decr = decrby
    def delete(self, *names: KeyT) -> ResponseT:
        """
        Delete one or more keys specified by ``names``
        """

    def dump(self, name: KeyT) -> ResponseT:
        """
        Return a serialized version of the value stored at the specified key.
        If key does not exist a nil bulk reply is returned.

        For more information see https://redis.io/commands/dump
        """
    def exists(self, *names: KeyT) -> ResponseT:
        """
        Returns the number of ``names`` that exist

        For more information see https://redis.io/commands/exists
        """

    def expire(self, name: KeyT, time: ExpiryT, nx: bool = False, xx: bool = False, gt: bool = False, lt: bool = False) -> ResponseT:
        """
        Set an expire flag on key ``name`` for ``time`` seconds with given
        ``option``. ``time`` can be represented by an integer or a Python timedelta
        object.

        Valid options are:
            NX -> Set expiry only when the key has no expiry
            XX -> Set expiry only when the key has an existing expiry
            GT -> Set expiry only when the new expiry is greater than current one
            LT -> Set expiry only when the new expiry is less than current one

        For more information see https://redis.io/commands/expire
        """
    def expireat(self, name: KeyT, when: AbsExpiryT, nx: bool = False, xx: bool = False, gt: bool = False, lt: bool = False) -> ResponseT:
        """
        Set an expire flag on key ``name`` with given ``option``. ``when``
        can be represented as an integer indicating unix time or a Python
        datetime object.

        Valid options are:
            -> NX -- Set expiry only when the key has no expiry
            -> XX -- Set expiry only when the key has an existing expiry
            -> GT -- Set expiry only when the new expiry is greater than current one
            -> LT -- Set expiry only when the new expiry is less than current one

        For more information see https://redis.io/commands/expireat
        """
    def expiretime(self, key: str) -> int:
        """
        Returns the absolute Unix timestamp (since January 1, 1970) in seconds
        at which the given key will expire.

        For more information see https://redis.io/commands/expiretime
        """
    def get(self, name: KeyT) -> ResponseT:
        """
        Return the value at key ``name``, or None if the key doesn't exist

        For more information see https://redis.io/commands/get
        """
    def getdel(self, name: KeyT) -> ResponseT:
        """
        Get the value at key ``name`` and delete the key. This command
        is similar to GET, except for the fact that it also deletes
        the key on success (if and only if the key's value type
        is a string).

        For more information see https://redis.io/commands/getdel
        """
    def getex(self, name: KeyT, ex: Union[ExpiryT, None] = None, px: Union[ExpiryT, None] = None, exat: Union[AbsExpiryT, None] = None, pxat: Union[AbsExpiryT, None] = None, persist: bool = False) -> ResponseT:
        """
        Get the value of key and optionally set its expiration.
        GETEX is similar to GET, but is a write command with
        additional options. All time parameters can be given as
        datetime.timedelta or integers.

        ``ex`` sets an expire flag on key ``name`` for ``ex`` seconds.

        ``px`` sets an expire flag on key ``name`` for ``px`` milliseconds.

        ``exat`` sets an expire flag on key ``name`` for ``ex`` seconds,
        specified in unix time.

        ``pxat`` sets an expire flag on key ``name`` for ``ex`` milliseconds,
        specified in unix time.

        ``persist`` remove the time to live associated with ``name``.

        For more information see https://redis.io/commands/getex
        """
   
    def getbit(self, name: KeyT, offset: int) -> ResponseT:
        """
        Returns an integer indicating the value of ``offset`` in ``name``

        For more information see https://redis.io/commands/getbit
        """
    def getrange(self, key: KeyT, start: int, end: int) -> ResponseT:
        """
        Returns the substring of the string value stored at ``key``,
        determined by the offsets ``start`` and ``end`` (both are inclusive)

        For more information see https://redis.io/commands/getrange
        """
    def getset(self, name: KeyT, value: EncodableT) -> ResponseT:
        """
        Sets the value at key ``name`` to ``value``
        and returns the old value at key ``name`` atomically.

        As per Redis 6.2, GETSET is considered deprecated.
        Please use SET with GET parameter in new code.

        For more information see https://redis.io/commands/getset
        """
    def incrby(self, name: KeyT, amount: int = 1) -> ResponseT:
        """
        Increments the value of ``key`` by ``amount``.  If no key exists,
        the value will be initialized as ``amount``

        For more information see https://redis.io/commands/incrby
        """
    incr = incrby
    def incrbyfloat(self, name: KeyT, amount: float = 1.0) -> ResponseT:
        """
        Increments the value at key ``name`` by floating ``amount``.
        If no key exists, the value will be initialized as ``amount``

        For more information see https://redis.io/commands/incrbyfloat
        """
    def keys(self, pattern: PatternT = '*', **kwargs) -> ResponseT:
        """
        Returns a list of keys matching ``pattern``

        For more information see https://redis.io/commands/keys
        """
    def lmove(self, first_list: str, second_list: str, src: str = 'LEFT', dest: str = 'RIGHT') -> ResponseT:
        """
        Atomically returns and removes the first/last element of a list,
        pushing it as the first/last element on the destination list.
        Returns the element being popped and pushed.

        For more information see https://redis.io/commands/lmove
        """
    def blmove(self, first_list: str, second_list: str, timeout: int, src: str = 'LEFT', dest: str = 'RIGHT') -> ResponseT:
        """
        Blocking version of lmove.

        For more information see https://redis.io/commands/blmove
        """
    def mget(self, keys: KeysT, *args: EncodableT) -> ResponseT:
        """
        Returns a list of values ordered identically to ``keys``

        For more information see https://redis.io/commands/mget
        """
    def mset(self, mapping: Mapping[AnyKeyT, EncodableT]) -> ResponseT:
        """
        Sets key/values based on a mapping. Mapping is a dictionary of
        key/value pairs. Both keys and values should be strings or types that
        can be cast to a string via str().

        For more information see https://redis.io/commands/mset
        """
    def msetnx(self, mapping: Mapping[AnyKeyT, EncodableT]) -> ResponseT:
        """
        Sets key/values based on a mapping if none of the keys are already set.
        Mapping is a dictionary of key/value pairs. Both keys and values
        should be strings or types that can be cast to a string via str().
        Returns a boolean indicating if the operation was successful.

        For more information see https://redis.io/commands/msetnx
        """
    def move(self, name: KeyT, db: int) -> ResponseT:
        """
        Moves the key ``name`` to a different Redis database ``db``

        For more information see https://redis.io/commands/move
        """
    def persist(self, name: KeyT) -> ResponseT:
        """
        Removes an expiration on ``name``

        For more information see https://redis.io/commands/persist
        """
    def pexpire(self, name: KeyT, time: ExpiryT, nx: bool = False, xx: bool = False, gt: bool = False, lt: bool = False) -> ResponseT:
        """
        Set an expire flag on key ``name`` for ``time`` milliseconds
        with given ``option``. ``time`` can be represented by an
        integer or a Python timedelta object.

        Valid options are:
            NX -> Set expiry only when the key has no expiry
            XX -> Set expiry only when the key has an existing expiry
            GT -> Set expiry only when the new expiry is greater than current one
            LT -> Set expiry only when the new expiry is less than current one

        For more information see https://redis.io/commands/pexpire
        """
    def pexpireat(self, name: KeyT, when: AbsExpiryT, nx: bool = False, xx: bool = False, gt: bool = False, lt: bool = False) -> ResponseT:
        """
        Set an expire flag on key ``name`` with given ``option``. ``when``
        can be represented as an integer representing unix time in
        milliseconds (unix time * 1000) or a Python datetime object.

        Valid options are:
            NX -> Set expiry only when the key has no expiry
            XX -> Set expiry only when the key has an existing expiry
            GT -> Set expiry only when the new expiry is greater than current one
            LT -> Set expiry only when the new expiry is less than current one

        For more information see https://redis.io/commands/pexpireat
        """
    def pexpiretime(self, key: str) -> int:
        """
        Returns the absolute Unix timestamp (since January 1, 1970) in milliseconds
        at which the given key will expire.

        For more information see https://redis.io/commands/pexpiretime
        """
    def psetex(self, name: KeyT, time_ms: ExpiryT, value: EncodableT):
        """
        Set the value of key ``name`` to ``value`` that expires in ``time_ms``
        milliseconds. ``time_ms`` can be represented by an integer or a Python
        timedelta object

        For more information see https://redis.io/commands/psetex
        """
    def pttl(self, name: KeyT) -> ResponseT:
        """
        Returns the number of milliseconds until the key ``name`` will expire

        For more information see https://redis.io/commands/pttl
        """
    def hrandfield(self, key: str, count: int = None, withvalues: bool = False) -> ResponseT:
        """
        Return a random field from the hash value stored at key.

        count: if the argument is positive, return an array of distinct fields.
        If called with a negative count, the behavior changes and the command
        is allowed to return the same field multiple times. In this case,
        the number of returned fields is the absolute value of the
        specified count.
        withvalues: The optional WITHVALUES modifier changes the reply so it
        includes the respective values of the randomly selected hash fields.

        For more information see https://redis.io/commands/hrandfield
        """
    def randomkey(self, **kwargs) -> ResponseT:
        """
        Returns the name of a random key

        For more information see https://redis.io/commands/randomkey
        """
    def rename(self, src: KeyT, dst: KeyT) -> ResponseT:
        """
        Rename key ``src`` to ``dst``

        For more information see https://redis.io/commands/rename
        """
    def renamenx(self, src: KeyT, dst: KeyT):
        """
        Rename key ``src`` to ``dst`` if ``dst`` doesn't already exist

        For more information see https://redis.io/commands/renamenx
        """
    def restore(self, name: KeyT, ttl: float, value: EncodableT, replace: bool = False, absttl: bool = False, idletime: Union[int, None] = None, frequency: Union[int, None] = None) -> ResponseT:
        """
        Create a key using the provided serialized value, previously obtained
        using DUMP.

        ``replace`` allows an existing key on ``name`` to be overridden. If
        it's not specified an error is raised on collision.

        ``absttl`` if True, specified ``ttl`` should represent an absolute Unix
        timestamp in milliseconds in which the key will expire. (Redis 5.0 or
        greater).

        ``idletime`` Used for eviction, this is the number of seconds the
        key must be idle, prior to execution.

        ``frequency`` Used for eviction, this is the frequency counter of
        the object stored at the key, prior to execution.

        For more information see https://redis.io/commands/restore
        """
    def set(self, name: KeyT, value: EncodableT, ex: Union[ExpiryT, None] = None, px: Union[ExpiryT, None] = None, nx: bool = False, xx: bool = False, keepttl: bool = False, get: bool = False, exat: Union[AbsExpiryT, None] = None, pxat: Union[AbsExpiryT, None] = None) -> ResponseT:
        """
        Set the value at key ``name`` to ``value``

        ``ex`` sets an expire flag on key ``name`` for ``ex`` seconds.

        ``px`` sets an expire flag on key ``name`` for ``px`` milliseconds.

        ``nx`` if set to True, set the value at key ``name`` to ``value`` only
            if it does not exist.

        ``xx`` if set to True, set the value at key ``name`` to ``value`` only
            if it already exists.

        ``keepttl`` if True, retain the time to live associated with the key.
            (Available since Redis 6.0)

        ``get`` if True, set the value at key ``name`` to ``value`` and return
            the old value stored at key, or None if the key did not exist.
            (Available since Redis 6.2)

        ``exat`` sets an expire flag on key ``name`` for ``ex`` seconds,
            specified in unix time.

        ``pxat`` sets an expire flag on key ``name`` for ``ex`` milliseconds,
            specified in unix time.

        For more information see https://redis.io/commands/set
        """

    def setbit(self, name: KeyT, offset: int, value: int) -> ResponseT:
        """
        Flag the ``offset`` in ``name`` as ``value``. Returns an integer
        indicating the previous value of ``offset``.

        For more information see https://redis.io/commands/setbit
        """
    def setex(self, name: KeyT, time: ExpiryT, value: EncodableT) -> ResponseT:
        """
        Set the value of key ``name`` to ``value`` that expires in ``time``
        seconds. ``time`` can be represented by an integer or a Python
        timedelta object.

        For more information see https://redis.io/commands/setex
        """
    def setnx(self, name: KeyT, value: EncodableT) -> ResponseT:
        """
        Set the value of key ``name`` to ``value`` if key doesn't exist

        For more information see https://redis.io/commands/setnx
        """
    def setrange(self, name: KeyT, offset: int, value: EncodableT) -> ResponseT:
        """
        Overwrite bytes in the value of ``name`` starting at ``offset`` with
        ``value``. If ``offset`` plus the length of ``value`` exceeds the
        length of the original value, the new value will be larger than before.
        If ``offset`` exceeds the length of the original value, null bytes
        will be used to pad between the end of the previous value and the start
        of what's being injected.

        Returns the length of the new string.

        For more information see https://redis.io/commands/setrange
        """
    def stralgo(self, algo: Literal['LCS'], value1: KeyT, value2: KeyT, specific_argument: Union[Literal['strings'], Literal['keys']] = 'strings', len: bool = False, idx: bool = False, minmatchlen: Union[int, None] = None, withmatchlen: bool = False, **kwargs) -> ResponseT:
        """
        Implements complex algorithms that operate on strings.
        Right now the only algorithm implemented is the LCS algorithm
        (longest common substring). However new algorithms could be
        implemented in the future.

        ``algo`` Right now must be LCS
        ``value1`` and ``value2`` Can be two strings or two keys
        ``specific_argument`` Specifying if the arguments to the algorithm
        will be keys or strings. strings is the default.
        ``len`` Returns just the len of the match.
        ``idx`` Returns the match positions in each string.
        ``minmatchlen`` Restrict the list of matches to the ones of a given
        minimal length. Can be provided only when ``idx`` set to True.
        ``withmatchlen`` Returns the matches with the len of the match.
        Can be provided only when ``idx`` set to True.

        For more information see https://redis.io/commands/stralgo
        """
    def strlen(self, name: KeyT) -> ResponseT:
        """
        Return the number of bytes stored in the value of ``name``

        For more information see https://redis.io/commands/strlen
        """
    def substr(self, name: KeyT, start: int, end: int = -1) -> ResponseT:
        """
        Return a substring of the string at key ``name``. ``start`` and ``end``
        are 0-based integers specifying the portion of the string to return.
        """
    def touch(self, *args: KeyT) -> ResponseT:
        """
        Alters the last access time of a key(s) ``*args``. A key is ignored
        if it does not exist.

        For more information see https://redis.io/commands/touch
        """
    def ttl(self, name: KeyT) -> ResponseT:
        """
        Returns the number of seconds until the key ``name`` will expire

        For more information see https://redis.io/commands/ttl
        """
    def type(self, name: KeyT) -> ResponseT:
        """
        Returns the type of key ``name``

        For more information see https://redis.io/commands/type
        """
    def watch(self, *names: KeyT) -> None:
        """
        Watches the values at keys ``names``, or None if the key doesn't exist

        For more information see https://redis.io/commands/watch
        """
    def unwatch(self) -> None:
        """
        Unwatches the value at key ``name``, or None of the key doesn't exist

        For more information see https://redis.io/commands/unwatch
        """
    def unlink(self, *names: KeyT) -> ResponseT:
        """
        Unlink one or more keys specified by ``names``

        For more information see https://redis.io/commands/unlink
        """
    def lcs(self, key1: str, key2: str, len: Optional[bool] = False, idx: Optional[bool] = False, minmatchlen: Optional[int] = 0, withmatchlen: Optional[bool] = False) -> Union[str, int, list]:
        """
        Find the longest common subsequence between ``key1`` and ``key2``.
        If ``len`` is true the length of the match will will be returned.
        If ``idx`` is true the match position in each strings will be returned.
        ``minmatchlen`` restrict the list of matches to the ones of
        the given ``minmatchlen``.
        If ``withmatchlen`` the length of the match also will be returned.
        For more information see https://redis.io/commands/lcs
        """
    
    """
    Redis commands for List data type.
    see: https://redis.io/topics/data-types#lists
    """
    def blpop(self, keys: List, timeout: Optional[int] = 0) -> Union[Awaitable[list], list]:
        """
        LPOP a value off of the first non-empty list
        named in the ``keys`` list.

        If none of the lists in ``keys`` has a value to LPOP, then block
        for ``timeout`` seconds, or until a value gets pushed on to one
        of the lists.

        If timeout is 0, then block indefinitely.

        For more information see https://redis.io/commands/blpop
        """
    def brpop(self, keys: List, timeout: Optional[int] = 0) -> Union[Awaitable[list], list]:
        """
        RPOP a value off of the first non-empty list
        named in the ``keys`` list.

        If none of the lists in ``keys`` has a value to RPOP, then block
        for ``timeout`` seconds, or until a value gets pushed on to one
        of the lists.

        If timeout is 0, then block indefinitely.

        For more information see https://redis.io/commands/brpop
        """
    def brpoplpush(self, src: str, dst: str, timeout: Optional[int] = 0) -> Union[Awaitable[Optional[str]], Optional[str]]:
        """
        Pop a value off the tail of ``src``, push it on the head of ``dst``
        and then return it.

        This command blocks until a value is in ``src`` or until ``timeout``
        seconds elapse, whichever is first. A ``timeout`` value of 0 blocks
        forever.

        For more information see https://redis.io/commands/brpoplpush
        """
    def blmpop(self, timeout: float, numkeys: int, *args: List[str], direction: str, count: Optional[int] = 1) -> Optional[list]:
        """
        Pop ``count`` values (default 1) from first non-empty in the list
        of provided key names.

        When all lists are empty this command blocks the connection until another
        client pushes to it or until the timeout, timeout of 0 blocks indefinitely

        For more information see https://redis.io/commands/blmpop
        """
    def lmpop(self, num_keys: int, *args: List[str], direction: str, count: Optional[int] = 1) -> Union[Awaitable[list], list]:
        """
        Pop ``count`` values (default 1) first non-empty list key from the list
        of args provided key names.

        For more information see https://redis.io/commands/lmpop
        """
    def lindex(self, name: str, index: int) -> Union[Awaitable[Optional[str]], Optional[str]]:
        """
        Return the item from list ``name`` at position ``index``

        Negative indexes are supported and will return an item at the
        end of the list

        For more information see https://redis.io/commands/lindex
        """
    def linsert(self, name: str, where: str, refvalue: str, value: str) -> Union[Awaitable[int], int]:
        """
        Insert ``value`` in list ``name`` either immediately before or after
        [``where``] ``refvalue``

        Returns the new length of the list on success or -1 if ``refvalue``
        is not in the list.

        For more information see https://redis.io/commands/linsert
        """
    def llen(self, name: str) -> Union[Awaitable[int], int]:
        """
        Return the length of the list ``name``

        For more information see https://redis.io/commands/llen
        """
    def lpop(self, name: str, count: Optional[int] = None) -> Union[Awaitable[Union[str, List, None]], Union[str, List, None]]:
        """
        Removes and returns the first elements of the list ``name``.

        By default, the command pops a single element from the beginning of
        the list. When provided with the optional ``count`` argument, the reply
        will consist of up to count elements, depending on the list's length.

        For more information see https://redis.io/commands/lpop
        """
    def lpush(self, name: str, *values: FieldT) -> Union[Awaitable[int], int]:
        """
        Push ``values`` onto the head of the list ``name``

        For more information see https://redis.io/commands/lpush
        """
    def lpushx(self, name: str, *values: FieldT) -> Union[Awaitable[int], int]:
        """
        Push ``value`` onto the head of the list ``name`` if ``name`` exists

        For more information see https://redis.io/commands/lpushx
        """
    def lrange(self, name: str, start: int, end: int) -> Union[Awaitable[list], list]:
        """
        Return a slice of the list ``name`` between
        position ``start`` and ``end``

        ``start`` and ``end`` can be negative numbers just like
        Python slicing notation

        For more information see https://redis.io/commands/lrange
        """
    def lrem(self, name: str, count: int, value: str) -> Union[Awaitable[int], int]:
        """
        Remove the first ``count`` occurrences of elements equal to ``value``
        from the list stored at ``name``.

        The count argument influences the operation in the following ways:
            count > 0: Remove elements equal to value moving from head to tail.
            count < 0: Remove elements equal to value moving from tail to head.
            count = 0: Remove all elements equal to value.

            For more information see https://redis.io/commands/lrem
        """
    def lset(self, name: str, index: int, value: str) -> Union[Awaitable[str], str]:
        """
        Set element at ``index`` of list ``name`` to ``value``

        For more information see https://redis.io/commands/lset
        """
    def ltrim(self, name: str, start: int, end: int) -> Union[Awaitable[str], str]:
        """
        Trim the list ``name``, removing all values not within the slice
        between ``start`` and ``end``

        ``start`` and ``end`` can be negative numbers just like
        Python slicing notation

        For more information see https://redis.io/commands/ltrim
        """
    def rpop(self, name: str, count: Optional[int] = None) -> Union[Awaitable[Union[str, List, None]], Union[str, List, None]]:
        """
        Removes and returns the last elements of the list ``name``.

        By default, the command pops a single element from the end of the list.
        When provided with the optional ``count`` argument, the reply will
        consist of up to count elements, depending on the list's length.

        For more information see https://redis.io/commands/rpop
        """
    def rpoplpush(self, src: str, dst: str) -> Union[Awaitable[str], str]:
        """
        RPOP a value off of the ``src`` list and atomically LPUSH it
        on to the ``dst`` list.  Returns the value.

        For more information see https://redis.io/commands/rpoplpush
        """
    def rpush(self, name: str, *values: FieldT) -> Union[Awaitable[int], int]:
        """
        Push ``values`` onto the tail of the list ``name``

        For more information see https://redis.io/commands/rpush
        """
    def rpushx(self, name: str, *values: str) -> Union[Awaitable[int], int]:
        """
        Push ``value`` onto the tail of the list ``name`` if ``name`` exists

        For more information see https://redis.io/commands/rpushx
        """
    def lpos(self, name: str, value: str, rank: Optional[int] = None, count: Optional[int] = None, maxlen: Optional[int] = None) -> Union[str, List, None]:
        '''
        Get position of ``value`` within the list ``name``

         If specified, ``rank`` indicates the "rank" of the first element to
         return in case there are multiple copies of ``value`` in the list.
         By default, LPOS returns the position of the first occurrence of
         ``value`` in the list. When ``rank`` 2, LPOS returns the position of
         the second ``value`` in the list. If ``rank`` is negative, LPOS
         searches the list in reverse. For example, -1 would return the
         position of the last occurrence of ``value`` and -2 would return the
         position of the next to last occurrence of ``value``.

         If specified, ``count`` indicates that LPOS should return a list of
         up to ``count`` positions. A ``count`` of 2 would return a list of
         up to 2 positions. A ``count`` of 0 returns a list of all positions
         matching ``value``. When ``count`` is specified and but ``value``
         does not exist in the list, an empty list is returned.

         If specified, ``maxlen`` indicates the maximum number of list
         elements to scan. A ``maxlen`` of 1000 will only return the
         position(s) of items within the first 1000 entries in the list.
         A ``maxlen`` of 0 (the default) will scan the entire list.

         For more information see https://redis.io/commands/lpos
        '''
    def sort(self, name: str, start: Optional[int] = None, num: Optional[int] = None, by: Optional[str] = None, get: Optional[List[str]] = None, desc: bool = False, alpha: bool = False, store: Optional[str] = None, groups: Optional[bool] = False) -> Union[List, int]:
        '''
        Sort and return the list, set or sorted set at ``name``.

        ``start`` and ``num`` allow for paging through the sorted data

        ``by`` allows using an external key to weight and sort the items.
            Use an "*" to indicate where in the key the item value is located

        ``get`` allows for returning items from external keys rather than the
            sorted data itself.  Use an "*" to indicate where in the key
            the item value is located

        ``desc`` allows for reversing the sort

        ``alpha`` allows for sorting lexicographically rather than numerically

        ``store`` allows for storing the result of the sort into
            the key ``store``

        ``groups`` if set to True and if ``get`` contains at least two
            elements, sort will return a list of tuples, each containing the
            values fetched from the arguments to ``get``.

        For more information see https://redis.io/commands/sort
        '''
    def sort_ro(self, key: str, start: Optional[int] = None, num: Optional[int] = None, by: Optional[str] = None, get: Optional[List[str]] = None, desc: bool = False, alpha: bool = False) -> list:
        '''
        Returns the elements contained in the list, set or sorted set at key.
        (read-only variant of the SORT command)

        ``start`` and ``num`` allow for paging through the sorted data

        ``by`` allows using an external key to weight and sort the items.
            Use an "*" to indicate where in the key the item value is located

        ``get`` allows for returning items from external keys rather than the
            sorted data itself.  Use an "*" to indicate where in the key
            the item value is located

        ``desc`` allows for reversing the sort

        ``alpha`` allows for sorting lexicographically rather than numerically

        For more information see https://redis.io/commands/sort_ro
        '''

    """
    Redis SCAN commands.
    see: https://redis.io/commands/scan
    """
    def scan(self, cursor: int = 0, match: Union[PatternT, None] = None, count: Union[int, None] = None, _type: Union[str, None] = None, **kwargs) -> ResponseT:
        """
        Incrementally return lists of key names. Also return a cursor
        indicating the scan position.

        ``match`` allows for filtering the keys by pattern

        ``count`` provides a hint to Redis about the number of keys to
            return per batch.

        ``_type`` filters the returned values by a particular Redis type.
            Stock Redis instances allow for the following types:
            HASH, LIST, SET, STREAM, STRING, ZSET
            Additionally, Redis modules can expose other types as well.

        For more information see https://redis.io/commands/scan
        """
    def scan_iter(self, match: Union[PatternT, None] = None, count: Union[int, None] = None, _type: Union[str, None] = None, **kwargs) -> Iterator:
        """
        Make an iterator using the SCAN command so that the client doesn't
        need to remember the cursor position.

        ``match`` allows for filtering the keys by pattern

        ``count`` provides a hint to Redis about the number of keys to
            return per batch.

        ``_type`` filters the returned values by a particular Redis type.
            Stock Redis instances allow for the following types:
            HASH, LIST, SET, STREAM, STRING, ZSET
            Additionally, Redis modules can expose other types as well.
        """
    def sscan(self, name: KeyT, cursor: int = 0, match: Union[PatternT, None] = None, count: Union[int, None] = None) -> ResponseT:
        """
        Incrementally return lists of elements in a set. Also return a cursor
        indicating the scan position.

        ``match`` allows for filtering the keys by pattern

        ``count`` allows for hint the minimum number of returns

        For more information see https://redis.io/commands/sscan
        """
    def sscan_iter(self, name: KeyT, match: Union[PatternT, None] = None, count: Union[int, None] = None) -> Iterator:
        """
        Make an iterator using the SSCAN command so that the client doesn't
        need to remember the cursor position.

        ``match`` allows for filtering the keys by pattern

        ``count`` allows for hint the minimum number of returns
        """
    def hscan(self, name: KeyT, cursor: int = 0, match: Union[PatternT, None] = None, count: Union[int, None] = None) -> ResponseT:
        """
        Incrementally return key/value slices in a hash. Also return a cursor
        indicating the scan position.

        ``match`` allows for filtering the keys by pattern

        ``count`` allows for hint the minimum number of returns

        For more information see https://redis.io/commands/hscan
        """
    def hscan_iter(self, name: str, match: Union[PatternT, None] = None, count: Union[int, None] = None) -> Iterator:
        """
        Make an iterator using the HSCAN command so that the client doesn't
        need to remember the cursor position.

        ``match`` allows for filtering the keys by pattern

        ``count`` allows for hint the minimum number of returns
        """
    def zscan(self, name: KeyT, cursor: int = 0, match: Union[PatternT, None] = None, count: Union[int, None] = None, score_cast_func: Union[type, Callable] = ...) -> ResponseT:
        """
        Incrementally return lists of elements in a sorted set. Also return a
        cursor indicating the scan position.

        ``match`` allows for filtering the keys by pattern

        ``count`` allows for hint the minimum number of returns

        ``score_cast_func`` a callable used to cast the score return value

        For more information see https://redis.io/commands/zscan
        """
    def zscan_iter(self, name: KeyT, match: Union[PatternT, None] = None, count: Union[int, None] = None, score_cast_func: Union[type, Callable] = ...) -> Iterator:
        """
        Make an iterator using the ZSCAN command so that the client doesn't
        need to remember the cursor position.

        ``match`` allows for filtering the keys by pattern

        ``count`` allows for hint the minimum number of returns

        ``score_cast_func`` a callable used to cast the score return value
        """


    """
    Redis commands for Set data type.
    see: https://redis.io/topics/data-types#sets
    """
    def sadd(self, name: str, *values: FieldT) -> Union[Awaitable[int], int]:
        """
        Add ``value(s)`` to set ``name``

        For more information see https://redis.io/commands/sadd
        """
    def scard(self, name: str) -> Union[Awaitable[int], int]:
        """
        Return the number of elements in set ``name``

        For more information see https://redis.io/commands/scard
        """
    def sdiff(self, keys: List, *args: List) -> Union[Awaitable[list], list]:
        """
        Return the difference of sets specified by ``keys``

        For more information see https://redis.io/commands/sdiff
        """
    def sdiffstore(self, dest: str, keys: List, *args: List) -> Union[Awaitable[int], int]:
        """
        Store the difference of sets specified by ``keys`` into a new
        set named ``dest``.  Returns the number of keys in the new set.

        For more information see https://redis.io/commands/sdiffstore
        """
    def sinter(self, keys: List, *args: List) -> Union[Awaitable[list], list]:
        """
        Return the intersection of sets specified by ``keys``

        For more information see https://redis.io/commands/sinter
        """
    def sintercard(self, numkeys: int, keys: List[str], limit: int = 0) -> Union[Awaitable[int], int]:
        """
        Return the cardinality of the intersect of multiple sets specified by ``keys`.

        When LIMIT provided (defaults to 0 and means unlimited), if the intersection
        cardinality reaches limit partway through the computation, the algorithm will
        exit and yield limit as the cardinality

        For more information see https://redis.io/commands/sintercard
        """
    def sinterstore(self, dest: str, keys: List, *args: List) -> Union[Awaitable[int], int]:
        """
        Store the intersection of sets specified by ``keys`` into a new
        set named ``dest``.  Returns the number of keys in the new set.

        For more information see https://redis.io/commands/sinterstore
        """
    def sismember(self, name: str, value: str) -> Union[Awaitable[Union[Literal[0], Literal[1]]], Union[Literal[0], Literal[1]]]:
        """
        Return whether ``value`` is a member of set ``name``:
        - 1 if the value is a member of the set.
        - 0 if the value is not a member of the set or if key does not exist.

        For more information see https://redis.io/commands/sismember
        """
    def smembers(self, name: str) -> Union[Awaitable[Set], Set]:
        """
        Return all members of the set ``name``

        For more information see https://redis.io/commands/smembers
        """
    def smismember(self, name: str, values: List, *args: List) -> Union[Awaitable[List[Union[Literal[0], Literal[1]]]], List[Union[Literal[0], Literal[1]]]]:
        """
        Return whether each value in ``values`` is a member of the set ``name``
        as a list of ``int`` in the order of ``values``:
        - 1 if the value is a member of the set.
        - 0 if the value is not a member of the set or if key does not exist.

        For more information see https://redis.io/commands/smismember
        """
    def smove(self, src: str, dst: str, value: str) -> Union[Awaitable[bool], bool]:
        """
        Move ``value`` from set ``src`` to set ``dst`` atomically

        For more information see https://redis.io/commands/smove
        """
    def spop(self, name: str, count: Optional[int] = None) -> Union[str, List, None]:
        """
        Remove and return a random member of set ``name``

        For more information see https://redis.io/commands/spop
        """
    def srandmember(self, name: str, number: Optional[int] = None) -> Union[str, List, None]:
        """
        If ``number`` is None, returns a random member of set ``name``.

        If ``number`` is supplied, returns a list of ``number`` random
        members of set ``name``. Note this is only available when running
        Redis 2.6+.

        For more information see https://redis.io/commands/srandmember
        """
    def srem(self, name: str, *values: FieldT) -> Union[Awaitable[int], int]:
        """
        Remove ``values`` from set ``name``

        For more information see https://redis.io/commands/srem
        """
    def sunion(self, keys: List, *args: List) -> Union[Awaitable[List], List]:
        """
        Return the union of sets specified by ``keys``

        For more information see https://redis.io/commands/sunion
        """
    def sunionstore(self, dest: str, keys: List, *args: List) -> Union[Awaitable[int], int]:
        """
        Store the union of sets specified by ``keys`` into a new
        set named ``dest``.  Returns the number of keys in the new set.

        For more information see https://redis.io/commands/sunionstore
        """
    """
    Redis commands for Stream data type.
    see: https://redis.io/topics/streams-intro
    """
    def xack(self, name: KeyT, groupname: GroupT, *ids: StreamIdT) -> ResponseT:
        """
        Acknowledges the successful processing of one or more messages.
        name: name of the stream.
        groupname: name of the consumer group.
        *ids: message ids to acknowledge.

        For more information see https://redis.io/commands/xack
        """
    def xadd(self, name: KeyT, fields: Dict[FieldT, EncodableT], id: StreamIdT = '*', maxlen: Union[int, None] = None, approximate: bool = True, nomkstream: bool = False, minid: Union[StreamIdT, None] = None, limit: Union[int, None] = None) -> ResponseT:
        """
        Add to a stream.
        name: name of the stream
        fields: dict of field/value pairs to insert into the stream
        id: Location to insert this record. By default it is appended.
        maxlen: truncate old stream members beyond this size.
        Can't be specified with minid.
        approximate: actual stream length may be slightly more than maxlen
        nomkstream: When set to true, do not make a stream
        minid: the minimum id in the stream to query.
        Can't be specified with maxlen.
        limit: specifies the maximum number of entries to retrieve

        For more information see https://redis.io/commands/xadd
        """
    def xautoclaim(self, name: KeyT, groupname: GroupT, consumername: ConsumerT, min_idle_time: int, start_id: StreamIdT = '0-0', count: Union[int, None] = None, justid: bool = False) -> ResponseT:
        """
        Transfers ownership of pending stream entries that match the specified
        criteria. Conceptually, equivalent to calling XPENDING and then XCLAIM,
        but provides a more straightforward way to deal with message delivery
        failures via SCAN-like semantics.
        name: name of the stream.
        groupname: name of the consumer group.
        consumername: name of a consumer that claims the message.
        min_idle_time: filter messages that were idle less than this amount of
        milliseconds.
        start_id: filter messages with equal or greater ID.
        count: optional integer, upper limit of the number of entries that the
        command attempts to claim. Set to 100 by default.
        justid: optional boolean, false by default. Return just an array of IDs
        of messages successfully claimed, without returning the actual message

        For more information see https://redis.io/commands/xautoclaim
        """
    def xclaim(self, name: KeyT, groupname: GroupT, consumername: ConsumerT, min_idle_time: int, message_ids: Union[List[StreamIdT], Tuple[StreamIdT]], idle: Union[int, None] = None, time: Union[int, None] = None, retrycount: Union[int, None] = None, force: bool = False, justid: bool = False) -> ResponseT:
        """
        Changes the ownership of a pending message.

        name: name of the stream.

        groupname: name of the consumer group.

        consumername: name of a consumer that claims the message.

        min_idle_time: filter messages that were idle less than this amount of
        milliseconds

        message_ids: non-empty list or tuple of message IDs to claim

        idle: optional. Set the idle time (last time it was delivered) of the
        message in ms

        time: optional integer. This is the same as idle but instead of a
        relative amount of milliseconds, it sets the idle time to a specific
        Unix time (in milliseconds).

        retrycount: optional integer. set the retry counter to the specified
        value. This counter is incremented every time a message is delivered
        again.

        force: optional boolean, false by default. Creates the pending message
        entry in the PEL even if certain specified IDs are not already in the
        PEL assigned to a different client.

        justid: optional boolean, false by default. Return just an array of IDs
        of messages successfully claimed, without returning the actual message

        For more information see https://redis.io/commands/xclaim
        """
    def xdel(self, name: KeyT, *ids: StreamIdT) -> ResponseT:
        """
        Deletes one or more messages from a stream.
        name: name of the stream.
        *ids: message ids to delete.

        For more information see https://redis.io/commands/xdel
        """
    def xgroup_create(self, name: KeyT, groupname: GroupT, id: StreamIdT = '$', mkstream: bool = False, entries_read: Optional[int] = None) -> ResponseT:
        """
        Create a new consumer group associated with a stream.
        name: name of the stream.
        groupname: name of the consumer group.
        id: ID of the last item in the stream to consider already delivered.

        For more information see https://redis.io/commands/xgroup-create
        """
    def xgroup_delconsumer(self, name: KeyT, groupname: GroupT, consumername: ConsumerT) -> ResponseT:
        """
        Remove a specific consumer from a consumer group.
        Returns the number of pending messages that the consumer had before it
        was deleted.
        name: name of the stream.
        groupname: name of the consumer group.
        consumername: name of consumer to delete

        For more information see https://redis.io/commands/xgroup-delconsumer
        """
    def xgroup_destroy(self, name: KeyT, groupname: GroupT) -> ResponseT:
        """
        Destroy a consumer group.
        name: name of the stream.
        groupname: name of the consumer group.

        For more information see https://redis.io/commands/xgroup-destroy
        """
    def xgroup_createconsumer(self, name: KeyT, groupname: GroupT, consumername: ConsumerT) -> ResponseT:
        """
        Consumers in a consumer group are auto-created every time a new
        consumer name is mentioned by some command.
        They can be explicitly created by using this command.
        name: name of the stream.
        groupname: name of the consumer group.
        consumername: name of consumer to create.

        See: https://redis.io/commands/xgroup-createconsumer
        """
    def xgroup_setid(self, name: KeyT, groupname: GroupT, id: StreamIdT, entries_read: Optional[int] = None) -> ResponseT:
        """
        Set the consumer group last delivered ID to something else.
        name: name of the stream.
        groupname: name of the consumer group.
        id: ID of the last item in the stream to consider already delivered.

        For more information see https://redis.io/commands/xgroup-setid
        """
    def xinfo_consumers(self, name: KeyT, groupname: GroupT) -> ResponseT:
        """
        Returns general information about the consumers in the group.
        name: name of the stream.
        groupname: name of the consumer group.

        For more information see https://redis.io/commands/xinfo-consumers
        """
    def xinfo_groups(self, name: KeyT) -> ResponseT:
        """
        Returns general information about the consumer groups of the stream.
        name: name of the stream.

        For more information see https://redis.io/commands/xinfo-groups
        """
    def xinfo_stream(self, name: KeyT, full: bool = False) -> ResponseT:
        """
        Returns general information about the stream.
        name: name of the stream.
        full: optional boolean, false by default. Return full summary

        For more information see https://redis.io/commands/xinfo-stream
        """
    def xlen(self, name: KeyT) -> ResponseT:
        """
        Returns the number of elements in a given stream.

        For more information see https://redis.io/commands/xlen
        """
    def xpending(self, name: KeyT, groupname: GroupT) -> ResponseT:
        """
        Returns information about pending messages of a group.
        name: name of the stream.
        groupname: name of the consumer group.

        For more information see https://redis.io/commands/xpending
        """
    def xpending_range(self, name: KeyT, groupname: GroupT, min: StreamIdT, max: StreamIdT, count: int, consumername: Union[ConsumerT, None] = None, idle: Union[int, None] = None) -> ResponseT:
        """
        Returns information about pending messages, in a range.

        name: name of the stream.
        groupname: name of the consumer group.
        idle: available from  version 6.2. filter entries by their
        idle-time, given in milliseconds (optional).
        min: minimum stream ID.
        max: maximum stream ID.
        count: number of messages to return
        consumername: name of a consumer to filter by (optional).
        """
    def xrange(self, name: KeyT, min: StreamIdT = '-', max: StreamIdT = '+', count: Union[int, None] = None) -> ResponseT:
        """
        Read stream values within an interval.

        name: name of the stream.

        start: first stream ID. defaults to '-',
               meaning the earliest available.

        finish: last stream ID. defaults to '+',
                meaning the latest available.

        count: if set, only return this many items, beginning with the
               earliest available.

        For more information see https://redis.io/commands/xrange
        """
    def xread(self, streams: Dict[KeyT, StreamIdT], count: Union[int, None] = None, block: Union[int, None] = None) -> ResponseT:
        """
        Block and monitor multiple streams for new data.

        streams: a dict of stream names to stream IDs, where
                   IDs indicate the last ID already seen.

        count: if set, only return this many items, beginning with the
               earliest available.

        block: number of milliseconds to wait, if nothing already present.

        For more information see https://redis.io/commands/xread
        """
    def xreadgroup(self, groupname: str, consumername: str, streams: Dict[KeyT, StreamIdT], count: Union[int, None] = None, block: Union[int, None] = None, noack: bool = False) -> ResponseT:
        """
        Read from a stream via a consumer group.

        groupname: name of the consumer group.

        consumername: name of the requesting consumer.

        streams: a dict of stream names to stream IDs, where
               IDs indicate the last ID already seen.

        count: if set, only return this many items, beginning with the
               earliest available.

        block: number of milliseconds to wait, if nothing already present.
        noack: do not add messages to the PEL

        For more information see https://redis.io/commands/xreadgroup
        """
    def xrevrange(self, name: KeyT, max: StreamIdT = '+', min: StreamIdT = '-', count: Union[int, None] = None) -> ResponseT:
        """
        Read stream values within an interval, in reverse order.

        name: name of the stream

        start: first stream ID. defaults to '+',
               meaning the latest available.

        finish: last stream ID. defaults to '-',
                meaning the earliest available.

        count: if set, only return this many items, beginning with the
               latest available.

        For more information see https://redis.io/commands/xrevrange
        """
    def xtrim(self, name: KeyT, maxlen: Union[int, None] = None, approximate: bool = True, minid: Union[StreamIdT, None] = None, limit: Union[int, None] = None) -> ResponseT:
        """
        Trims old messages from a stream.
        name: name of the stream.
        maxlen: truncate old stream messages beyond this size
        Can't be specified with minid.
        approximate: actual stream length may be slightly more than maxlen
        minid: the minimum id in the stream to query
        Can't be specified with maxlen.
        limit: specifies the maximum number of entries to retrieve

        For more information see https://redis.io/commands/xtrim
        """
    
    """
    Redis commands for Sorted Sets data type.
    see: https://redis.io/topics/data-types-intro#redis-sorted-sets
    """
    def zadd(self, name: KeyT, mapping: Mapping[AnyKeyT, EncodableT], nx: bool = False, xx: bool = False, ch: bool = False, incr: bool = False, gt: bool = False, lt: bool = False) -> ResponseT:
        """
        Set any number of element-name, score pairs to the key ``name``. Pairs
        are specified as a dict of element-names keys to score values.

        ``nx`` forces ZADD to only create new elements and not to update
        scores for elements that already exist.

        ``xx`` forces ZADD to only update scores of elements that already
        exist. New elements will not be added.

        ``ch`` modifies the return value to be the numbers of elements changed.
        Changed elements include new elements that were added and elements
        whose scores changed.

        ``incr`` modifies ZADD to behave like ZINCRBY. In this mode only a
        single element/score pair can be specified and the score is the amount
        the existing score will be incremented by. When using this mode the
        return value of ZADD will be the new score of the element.

        ``LT`` Only update existing elements if the new score is less than
        the current score. This flag doesn't prevent adding new elements.

        ``GT`` Only update existing elements if the new score is greater than
        the current score. This flag doesn't prevent adding new elements.

        The return value of ZADD varies based on the mode specified. With no
        options, ZADD returns the number of new elements added to the sorted
        set.

        ``NX``, ``LT``, and ``GT`` are mutually exclusive options.

        See: https://redis.io/commands/ZADD
        """
    def zcard(self, name: KeyT) -> ResponseT:
        """
        Return the number of elements in the sorted set ``name``

        For more information see https://redis.io/commands/zcard
        """
    def zcount(self, name: KeyT, min: ZScoreBoundT, max: ZScoreBoundT) -> ResponseT:
        """
        Returns the number of elements in the sorted set at key ``name`` with
        a score between ``min`` and ``max``.

        For more information see https://redis.io/commands/zcount
        """
    def zdiff(self, keys: KeysT, withscores: bool = False) -> ResponseT:
        """
        Returns the difference between the first and all successive input
        sorted sets provided in ``keys``.

        For more information see https://redis.io/commands/zdiff
        """
    def zdiffstore(self, dest: KeyT, keys: KeysT) -> ResponseT:
        """
        Computes the difference between the first and all successive input
        sorted sets provided in ``keys`` and stores the result in ``dest``.

        For more information see https://redis.io/commands/zdiffstore
        """
    def zincrby(self, name: KeyT, amount: float, value: EncodableT) -> ResponseT:
        """
        Increment the score of ``value`` in sorted set ``name`` by ``amount``

        For more information see https://redis.io/commands/zincrby
        """
    def zinter(self, keys: KeysT, aggregate: Union[str, None] = None, withscores: bool = False) -> ResponseT:
        """
        Return the intersect of multiple sorted sets specified by ``keys``.
        With the ``aggregate`` option, it is possible to specify how the
        results of the union are aggregated. This option defaults to SUM,
        where the score of an element is summed across the inputs where it
        exists. When this option is set to either MIN or MAX, the resulting
        set will contain the minimum or maximum score of an element across
        the inputs where it exists.

        For more information see https://redis.io/commands/zinter
        """
    def zinterstore(self, dest: KeyT, keys: Union[Sequence[KeyT], Mapping[AnyKeyT, float]], aggregate: Union[str, None] = None) -> ResponseT:
        """
        Intersect multiple sorted sets specified by ``keys`` into a new
        sorted set, ``dest``. Scores in the destination will be aggregated
        based on the ``aggregate``. This option defaults to SUM, where the
        score of an element is summed across the inputs where it exists.
        When this option is set to either MIN or MAX, the resulting set will
        contain the minimum or maximum score of an element across the inputs
        where it exists.

        For more information see https://redis.io/commands/zinterstore
        """
    def zintercard(self, numkeys: int, keys: List[str], limit: int = 0) -> Union[Awaitable[int], int]:
        """
        Return the cardinality of the intersect of multiple sorted sets
        specified by ``keys`.
        When LIMIT provided (defaults to 0 and means unlimited), if the intersection
        cardinality reaches limit partway through the computation, the algorithm will
        exit and yield limit as the cardinality

        For more information see https://redis.io/commands/zintercard
        """
    def zlexcount(self, name, min, max):
        """
        Return the number of items in the sorted set ``name`` between the
        lexicographical range ``min`` and ``max``.

        For more information see https://redis.io/commands/zlexcount
        """
    def zpopmax(self, name: KeyT, count: Union[int, None] = None) -> ResponseT:
        """
        Remove and return up to ``count`` members with the highest scores
        from the sorted set ``name``.

        For more information see https://redis.io/commands/zpopmax
        """
    def zpopmin(self, name: KeyT, count: Union[int, None] = None) -> ResponseT:
        """
        Remove and return up to ``count`` members with the lowest scores
        from the sorted set ``name``.

        For more information see https://redis.io/commands/zpopmin
        """
    def zrandmember(self, key: KeyT, count: int = None, withscores: bool = False) -> ResponseT:
        """
        Return a random element from the sorted set value stored at key.

        ``count`` if the argument is positive, return an array of distinct
        fields. If called with a negative count, the behavior changes and
        the command is allowed to return the same field multiple times.
        In this case, the number of returned fields is the absolute value
        of the specified count.

        ``withscores`` The optional WITHSCORES modifier changes the reply so it
        includes the respective scores of the randomly selected elements from
        the sorted set.

        For more information see https://redis.io/commands/zrandmember
        """
    def bzpopmax(self, keys: KeysT, timeout: TimeoutSecT = 0) -> ResponseT:
        """
        ZPOPMAX a value off of the first non-empty sorted set
        named in the ``keys`` list.

        If none of the sorted sets in ``keys`` has a value to ZPOPMAX,
        then block for ``timeout`` seconds, or until a member gets added
        to one of the sorted sets.

        If timeout is 0, then block indefinitely.

        For more information see https://redis.io/commands/bzpopmax
        """
    def bzpopmin(self, keys: KeysT, timeout: TimeoutSecT = 0) -> ResponseT:
        """
        ZPOPMIN a value off of the first non-empty sorted set
        named in the ``keys`` list.

        If none of the sorted sets in ``keys`` has a value to ZPOPMIN,
        then block for ``timeout`` seconds, or until a member gets added
        to one of the sorted sets.

        If timeout is 0, then block indefinitely.

        For more information see https://redis.io/commands/bzpopmin
        """
    def zmpop(self, num_keys: int, keys: List[str], min: Optional[bool] = False, max: Optional[bool] = False, count: Optional[int] = 1) -> Union[Awaitable[list], list]:
        """
        Pop ``count`` values (default 1) off of the first non-empty sorted set
        named in the ``keys`` list.
        For more information see https://redis.io/commands/zmpop
        """
    def bzmpop(self, timeout: float, numkeys: int, keys: List[str], min: Optional[bool] = False, max: Optional[bool] = False, count: Optional[int] = 1) -> Optional[list]:
        """
        Pop ``count`` values (default 1) off of the first non-empty sorted set
        named in the ``keys`` list.

        If none of the sorted sets in ``keys`` has a value to pop,
        then block for ``timeout`` seconds, or until a member gets added
        to one of the sorted sets.

        If timeout is 0, then block indefinitely.

        For more information see https://redis.io/commands/bzmpop
        """
    def zrange(self, name: KeyT, start: int, end: int, desc: bool = False, withscores: bool = False, score_cast_func: Union[type, Callable] = ..., byscore: bool = False, bylex: bool = False, offset: int = None, num: int = None) -> ResponseT:
        """
        Return a range of values from sorted set ``name`` between
        ``start`` and ``end`` sorted in ascending order.

        ``start`` and ``end`` can be negative, indicating the end of the range.

        ``desc`` a boolean indicating whether to sort the results in reversed
        order.

        ``withscores`` indicates to return the scores along with the values.
        The return type is a list of (value, score) pairs.

        ``score_cast_func`` a callable used to cast the score return value.

        ``byscore`` when set to True, returns the range of elements from the
        sorted set having scores equal or between ``start`` and ``end``.

        ``bylex`` when set to True, returns the range of elements from the
        sorted set between the ``start`` and ``end`` lexicographical closed
        range intervals.
        Valid ``start`` and ``end`` must start with ( or [, in order to specify
        whether the range interval is exclusive or inclusive, respectively.

        ``offset`` and ``num`` are specified, then return a slice of the range.
        Can't be provided when using ``bylex``.

        For more information see https://redis.io/commands/zrange
        """
    def zrevrange(self, name: KeyT, start: int, end: int, withscores: bool = False, score_cast_func: Union[type, Callable] = ...) -> ResponseT:
        """
        Return a range of values from sorted set ``name`` between
        ``start`` and ``end`` sorted in descending order.

        ``start`` and ``end`` can be negative, indicating the end of the range.

        ``withscores`` indicates to return the scores along with the values
        The return type is a list of (value, score) pairs

        ``score_cast_func`` a callable used to cast the score return value

        For more information see https://redis.io/commands/zrevrange
        """
    def zrangestore(self, dest: KeyT, name: KeyT, start: int, end: int, byscore: bool = False, bylex: bool = False, desc: bool = False, offset: Union[int, None] = None, num: Union[int, None] = None) -> ResponseT:
        """
        Stores in ``dest`` the result of a range of values from sorted set
        ``name`` between ``start`` and ``end`` sorted in ascending order.

        ``start`` and ``end`` can be negative, indicating the end of the range.

        ``byscore`` when set to True, returns the range of elements from the
        sorted set having scores equal or between ``start`` and ``end``.

        ``bylex`` when set to True, returns the range of elements from the
        sorted set between the ``start`` and ``end`` lexicographical closed
        range intervals.
        Valid ``start`` and ``end`` must start with ( or [, in order to specify
        whether the range interval is exclusive or inclusive, respectively.

        ``desc`` a boolean indicating whether to sort the results in reversed
        order.

        ``offset`` and ``num`` are specified, then return a slice of the range.
        Can't be provided when using ``bylex``.

        For more information see https://redis.io/commands/zrangestore
        """
    def zrangebylex(self, name: KeyT, min: EncodableT, max: EncodableT, start: Union[int, None] = None, num: Union[int, None] = None) -> ResponseT:
        """
        Return the lexicographical range of values from sorted set ``name``
        between ``min`` and ``max``.

        If ``start`` and ``num`` are specified, then return a slice of the
        range.

        For more information see https://redis.io/commands/zrangebylex
        """
    def zrevrangebylex(self, name: KeyT, max: EncodableT, min: EncodableT, start: Union[int, None] = None, num: Union[int, None] = None) -> ResponseT:
        """
        Return the reversed lexicographical range of values from sorted set
        ``name`` between ``max`` and ``min``.

        If ``start`` and ``num`` are specified, then return a slice of the
        range.

        For more information see https://redis.io/commands/zrevrangebylex
        """
    def zrangebyscore(self, name: KeyT, min: ZScoreBoundT, max: ZScoreBoundT, start: Union[int, None] = None, num: Union[int, None] = None, withscores: bool = False, score_cast_func: Union[type, Callable] = ...) -> ResponseT:
        """
        Return a range of values from the sorted set ``name`` with scores
        between ``min`` and ``max``.

        If ``start`` and ``num`` are specified, then return a slice
        of the range.

        ``withscores`` indicates to return the scores along with the values.
        The return type is a list of (value, score) pairs

        `score_cast_func`` a callable used to cast the score return value

        For more information see https://redis.io/commands/zrangebyscore
        """
    def zrevrangebyscore(self, name: KeyT, max: ZScoreBoundT, min: ZScoreBoundT, start: Union[int, None] = None, num: Union[int, None] = None, withscores: bool = False, score_cast_func: Union[type, Callable] = ...):
        """
        Return a range of values from the sorted set ``name`` with scores
        between ``min`` and ``max`` in descending order.

        If ``start`` and ``num`` are specified, then return a slice
        of the range.

        ``withscores`` indicates to return the scores along with the values.
        The return type is a list of (value, score) pairs

        ``score_cast_func`` a callable used to cast the score return value

        For more information see https://redis.io/commands/zrevrangebyscore
        """
    def zrank(self, name: KeyT, value: EncodableT, withscore: bool = False) -> ResponseT:
        """
        Returns a 0-based value indicating the rank of ``value`` in sorted set
        ``name``.
        The optional WITHSCORE argument supplements the command's
        reply with the score of the element returned.

        For more information see https://redis.io/commands/zrank
        """
    def zrem(self, name: KeyT, *values: FieldT) -> ResponseT:
        """
        Remove member ``values`` from sorted set ``name``

        For more information see https://redis.io/commands/zrem
        """
    def zremrangebylex(self, name: KeyT, min: EncodableT, max: EncodableT) -> ResponseT:
        """
        Remove all elements in the sorted set ``name`` between the
        lexicographical range specified by ``min`` and ``max``.

        Returns the number of elements removed.

        For more information see https://redis.io/commands/zremrangebylex
        """
    def zremrangebyrank(self, name: KeyT, min: int, max: int) -> ResponseT:
        """
        Remove all elements in the sorted set ``name`` with ranks between
        ``min`` and ``max``. Values are 0-based, ordered from smallest score
        to largest. Values can be negative indicating the highest scores.
        Returns the number of elements removed

        For more information see https://redis.io/commands/zremrangebyrank
        """
    def zremrangebyscore(self, name: KeyT, min: ZScoreBoundT, max: ZScoreBoundT) -> ResponseT:
        """
        Remove all elements in the sorted set ``name`` with scores
        between ``min`` and ``max``. Returns the number of elements removed.

        For more information see https://redis.io/commands/zremrangebyscore
        """
    def zrevrank(self, name: KeyT, value: EncodableT, withscore: bool = False) -> ResponseT:
        """
        Returns a 0-based value indicating the descending rank of
        ``value`` in sorted set ``name``.
        The optional ``withscore`` argument supplements the command's
        reply with the score of the element returned.

        For more information see https://redis.io/commands/zrevrank
        """
    def zscore(self, name: KeyT, value: EncodableT) -> ResponseT:
        """
        Return the score of element ``value`` in sorted set ``name``

        For more information see https://redis.io/commands/zscore
        """
    def zunion(self, keys: Union[Sequence[KeyT], Mapping[AnyKeyT, float]], aggregate: Union[str, None] = None, withscores: bool = False) -> ResponseT:
        """
        Return the union of multiple sorted sets specified by ``keys``.
        ``keys`` can be provided as dictionary of keys and their weights.
        Scores will be aggregated based on the ``aggregate``, or SUM if
        none is provided.

        For more information see https://redis.io/commands/zunion
        """
    def zunionstore(self, dest: KeyT, keys: Union[Sequence[KeyT], Mapping[AnyKeyT, float]], aggregate: Union[str, None] = None) -> ResponseT:
        """
        Union multiple sorted sets specified by ``keys`` into
        a new sorted set, ``dest``. Scores in the destination will be
        aggregated based on the ``aggregate``, or SUM if none is provided.

        For more information see https://redis.io/commands/zunionstore
        """
    def zmscore(self, key: KeyT, members: List[str]) -> ResponseT:
        """
        Returns the scores associated with the specified members
        in the sorted set stored at key.
        ``members`` should be a list of the member name.
        Return type is a list of score.
        If the member does not exist, a None will be returned
        in corresponding position.

        For more information see https://redis.io/commands/zmscore
        """
    """
    Redis commands of HyperLogLogs data type.
    see: https://redis.io/topics/data-types-intro#hyperloglogs
    """
    def pfadd(self, name: KeyT, *values: FieldT) -> ResponseT:
        """
        Adds the specified elements to the specified HyperLogLog.

        For more information see https://redis.io/commands/pfadd
        """
    def pfcount(self, *sources: KeyT) -> ResponseT:
        """
        Return the approximated cardinality of
        the set observed by the HyperLogLog at key(s).

        For more information see https://redis.io/commands/pfcount
        """
    def pfmerge(self, dest: KeyT, *sources: KeyT) -> ResponseT:
        """
        Merge N different HyperLogLogs into a single one.

        For more information see https://redis.io/commands/pfmerge
        """
    
    """
    Redis commands for Hash data type.
    see: https://redis.io/topics/data-types-intro#redis-hashes
    """
    def hdel(self, name: str, *keys: List) -> Union[Awaitable[int], int]:
        """
        Delete ``keys`` from hash ``name``

        For more information see https://redis.io/commands/hdel
        """
    def hexists(self, name: str, key: str) -> Union[Awaitable[bool], bool]:
        """
        Returns a boolean indicating if ``key`` exists within hash ``name``

        For more information see https://redis.io/commands/hexists
        """
    def hget(self, name: str, key: str) -> Union[Awaitable[Optional[str]], Optional[str]]:
        """
        Return the value of ``key`` within the hash ``name``

        For more information see https://redis.io/commands/hget
        """
    def hgetall(self, name: str) -> Union[Awaitable[dict], dict]:
        """
        Return a Python dict of the hash's name/value pairs

        For more information see https://redis.io/commands/hgetall
        """
    def hincrby(self, name: str, key: str, amount: int = 1) -> Union[Awaitable[int], int]:
        """
        Increment the value of ``key`` in hash ``name`` by ``amount``

        For more information see https://redis.io/commands/hincrby
        """
    def hincrbyfloat(self, name: str, key: str, amount: float = 1.0) -> Union[Awaitable[float], float]:
        """
        Increment the value of ``key`` in hash ``name`` by floating ``amount``

        For more information see https://redis.io/commands/hincrbyfloat
        """
    def hkeys(self, name: str) -> Union[Awaitable[List], List]:
        """
        Return the list of keys within hash ``name``

        For more information see https://redis.io/commands/hkeys
        """
    def hlen(self, name: str) -> Union[Awaitable[int], int]:
        """
        Return the number of elements in hash ``name``

        For more information see https://redis.io/commands/hlen
        """
    def hset(self, name: str, key: Optional[str] = None, value: Optional[str] = None, mapping: Optional[dict] = None, items: Optional[list] = None) -> Union[Awaitable[int], int]:
        """
        Set ``key`` to ``value`` within hash ``name``,
        ``mapping`` accepts a dict of key/value pairs that will be
        added to hash ``name``.
        ``items`` accepts a list of key/value pairs that will be
        added to hash ``name``.
        Returns the number of fields that were added.

        For more information see https://redis.io/commands/hset
        """
    def hsetnx(self, name: str, key: str, value: str) -> Union[Awaitable[bool], bool]:
        """
        Set ``key`` to ``value`` within hash ``name`` if ``key`` does not
        exist.  Returns 1 if HSETNX created a field, otherwise 0.

        For more information see https://redis.io/commands/hsetnx
        """
    def hmset(self, name: str, mapping: dict) -> Union[Awaitable[str], str]:
        """
        Set key to value within hash ``name`` for each corresponding
        key and value from the ``mapping`` dict.

        For more information see https://redis.io/commands/hmset
        """
    def hmget(self, name: str, keys: List, *args: List) -> Union[Awaitable[List], List]:
        """
        Returns a list of values ordered identically to ``keys``

        For more information see https://redis.io/commands/hmget
        """
    def hvals(self, name: str) -> Union[Awaitable[List], List]:
        """
        Return the list of values within hash ``name``

        For more information see https://redis.io/commands/hvals
        """
    def hstrlen(self, name: str, key: str) -> Union[Awaitable[int], int]:
        """
        Return the number of bytes stored in the value of ``key``
        within hash ``name``

        For more information see https://redis.io/commands/hstrlen
        """
    """
    Redis PubSub commands.
    see https://redis.io/topics/pubsub
    """
    def publish(self, channel: ChannelT, message: EncodableT, **kwargs) -> ResponseT:
        """
        Publish ``message`` on ``channel``.
        Returns the number of subscribers the message was delivered to.

        For more information see https://redis.io/commands/publish
        """
    def spublish(self, shard_channel: ChannelT, message: EncodableT) -> ResponseT:
        """
        Posts a message to the given shard channel.
        Returns the number of clients that received the message

        For more information see https://redis.io/commands/spublish
        """
    def pubsub_channels(self, pattern: PatternT = '*', **kwargs) -> ResponseT:
        """
        Return a list of channels that have at least one subscriber

        For more information see https://redis.io/commands/pubsub-channels
        """
    def pubsub_shardchannels(self, pattern: PatternT = '*', **kwargs) -> ResponseT:
        """
        Return a list of shard_channels that have at least one subscriber

        For more information see https://redis.io/commands/pubsub-shardchannels
        """
    def pubsub_numpat(self, **kwargs) -> ResponseT:
        """
        Returns the number of subscriptions to patterns

        For more information see https://redis.io/commands/pubsub-numpat
        """
    def pubsub_numsub(self, *args: ChannelT, **kwargs) -> ResponseT:
        """
        Return a list of (channel, number of subscribers) tuples
        for each channel given in ``*args``

        For more information see https://redis.io/commands/pubsub-numsub
        """
    def pubsub_shardnumsub(self, *args: ChannelT, **kwargs) -> ResponseT:
        """
        Return a list of (shard_channel, number of subscribers) tuples
        for each channel given in ``*args``

        For more information see https://redis.io/commands/pubsub-shardnumsub
        """

    """
    Redis Lua script commands. see:
    https://redis.com/ebook/part-3-next-steps/chapter-11-scripting-redis-with-lua/
    """
    def eval(self, script: str, numkeys: int, *keys_and_args: list) -> Union[Awaitable[str], str]:
        """
        Execute the Lua ``script``, specifying the ``numkeys`` the script
        will touch and the key names and argument values in ``keys_and_args``.
        Returns the result of the script.

        In practice, use the object returned by ``register_script``. This
        function exists purely for Redis API completion.

        For more information see  https://redis.io/commands/eval
        """
    def eval_ro(self, script: str, numkeys: int, *keys_and_args: list) -> Union[Awaitable[str], str]:
        """
        The read-only variant of the EVAL command

        Execute the read-only Lua ``script`` specifying the ``numkeys`` the script
        will touch and the key names and argument values in ``keys_and_args``.
        Returns the result of the script.

        For more information see  https://redis.io/commands/eval_ro
        """
    def evalsha(self, sha: str, numkeys: int, *keys_and_args: list) -> Union[Awaitable[str], str]:
        """
        Use the ``sha`` to execute a Lua script already registered via EVAL
        or SCRIPT LOAD. Specify the ``numkeys`` the script will touch and the
        key names and argument values in ``keys_and_args``. Returns the result
        of the script.

        In practice, use the object returned by ``register_script``. This
        function exists purely for Redis API completion.

        For more information see  https://redis.io/commands/evalsha
        """
    def evalsha_ro(self, sha: str, numkeys: int, *keys_and_args: list) -> Union[Awaitable[str], str]:
        """
        The read-only variant of the EVALSHA command

        Use the ``sha`` to execute a read-only Lua script already registered via EVAL
        or SCRIPT LOAD. Specify the ``numkeys`` the script will touch and the
        key names and argument values in ``keys_and_args``. Returns the result
        of the script.

        For more information see  https://redis.io/commands/evalsha_ro
        """
    def script_exists(self, *args: str) -> ResponseT:
        """
        Check if a script exists in the script cache by specifying the SHAs of
        each script as ``args``. Returns a list of boolean values indicating if
        if each already script exists in the cache.

        For more information see  https://redis.io/commands/script-exists
        """
    def script_debug(self, *args) -> None: ...
    def script_flush(self, sync_type: Union[Literal['SYNC'], Literal['ASYNC']] = None) -> ResponseT:
        """Flush all scripts from the script cache.

        ``sync_type`` is by default SYNC (synchronous) but it can also be
                      ASYNC.

        For more information see  https://redis.io/commands/script-flush
        """
    def script_kill(self) -> ResponseT:
        """
        Kill the currently executing Lua script

        For more information see https://redis.io/commands/script-kill
        """
    def script_load(self, script: ScriptTextT) -> ResponseT:
        """
        Load a Lua ``script`` into the script cache. Returns the SHA.

        For more information see https://redis.io/commands/script-load
        """
    def register_script(self, script: ScriptTextT) -> Script:
        """
        Register a Lua ``script`` specifying the ``keys`` it will touch.
        Returns a Script object that is callable and hides the complexity of
        deal with scripts, keys, and shas. This is the preferred way to work
        with Lua scripts.
        """
    
    """
    Redis Geospatial commands.
    see: https://redis.com/redis-best-practices/indexing-patterns/geospatial/
    """
    def geoadd(self, name: KeyT, values: Sequence[EncodableT], nx: bool = False, xx: bool = False, ch: bool = False) -> ResponseT:
        """
        Add the specified geospatial items to the specified key identified
        by the ``name`` argument. The Geospatial items are given as ordered
        members of the ``values`` argument, each item or place is formed by
        the triad longitude, latitude and name.

        Note: You can use ZREM to remove elements.

        ``nx`` forces ZADD to only create new elements and not to update
        scores for elements that already exist.

        ``xx`` forces ZADD to only update scores of elements that already
        exist. New elements will not be added.

        ``ch`` modifies the return value to be the numbers of elements changed.
        Changed elements include new elements that were added and elements
        whose scores changed.

        For more information see https://redis.io/commands/geoadd
        """
    def geodist(self, name: KeyT, place1: FieldT, place2: FieldT, unit: Union[str, None] = None) -> ResponseT:
        """
        Return the distance between ``place1`` and ``place2`` members of the
        ``name`` key.
        The units must be one of the following : m, km mi, ft. By default
        meters are used.

        For more information see https://redis.io/commands/geodist
        """
    def geohash(self, name: KeyT, *values: FieldT) -> ResponseT:
        """
        Return the geo hash string for each item of ``values`` members of
        the specified key identified by the ``name`` argument.

        For more information see https://redis.io/commands/geohash
        """
    def geopos(self, name: KeyT, *values: FieldT) -> ResponseT:
        """
        Return the positions of each item of ``values`` as members of
        the specified key identified by the ``name`` argument. Each position
        is represented by the pairs lon and lat.

        For more information see https://redis.io/commands/geopos
        """
    def georadius(self, name: KeyT, longitude: float, latitude: float, radius: float, unit: Union[str, None] = None, withdist: bool = False, withcoord: bool = False, withhash: bool = False, count: Union[int, None] = None, sort: Union[str, None] = None, store: Union[KeyT, None] = None, store_dist: Union[KeyT, None] = None, any: bool = False) -> ResponseT:
        """
        Return the members of the specified key identified by the
        ``name`` argument which are within the borders of the area specified
        with the ``latitude`` and ``longitude`` location and the maximum
        distance from the center specified by the ``radius`` value.

        The units must be one of the following : m, km mi, ft. By default

        ``withdist`` indicates to return the distances of each place.

        ``withcoord`` indicates to return the latitude and longitude of
        each place.

        ``withhash`` indicates to return the geohash string of each place.

        ``count`` indicates to return the number of elements up to N.

        ``sort`` indicates to return the places in a sorted way, ASC for
        nearest to fairest and DESC for fairest to nearest.

        ``store`` indicates to save the places names in a sorted set named
        with a specific key, each element of the destination sorted set is
        populated with the score got from the original geo sorted set.

        ``store_dist`` indicates to save the places names in a sorted set
        named with a specific key, instead of ``store`` the sorted set
        destination score is set with the distance.

        For more information see https://redis.io/commands/georadius
        """
    def georadiusbymember(self, name: KeyT, member: FieldT, radius: float, unit: Union[str, None] = None, withdist: bool = False, withcoord: bool = False, withhash: bool = False, count: Union[int, None] = None, sort: Union[str, None] = None, store: Union[KeyT, None] = None, store_dist: Union[KeyT, None] = None, any: bool = False) -> ResponseT:
        """
        This command is exactly like ``georadius`` with the sole difference
        that instead of taking, as the center of the area to query, a longitude
        and latitude value, it takes the name of a member already existing
        inside the geospatial index represented by the sorted set.

        For more information see https://redis.io/commands/georadiusbymember
        """
    def geosearch(self, name: KeyT, member: Union[FieldT, None] = None, longitude: Union[float, None] = None, latitude: Union[float, None] = None, unit: str = 'm', radius: Union[float, None] = None, width: Union[float, None] = None, height: Union[float, None] = None, sort: Union[str, None] = None, count: Union[int, None] = None, any: bool = False, withcoord: bool = False, withdist: bool = False, withhash: bool = False) -> ResponseT:
        """
        Return the members of specified key identified by the
        ``name`` argument, which are within the borders of the
        area specified by a given shape. This command extends the
        GEORADIUS command, so in addition to searching within circular
        areas, it supports searching within rectangular areas.

        This command should be used in place of the deprecated
        GEORADIUS and GEORADIUSBYMEMBER commands.

        ``member`` Use the position of the given existing
         member in the sorted set. Can't be given with ``longitude``
         and ``latitude``.

        ``longitude`` and ``latitude`` Use the position given by
        this coordinates. Can't be given with ``member``
        ``radius`` Similar to GEORADIUS, search inside circular
        area according the given radius. Can't be given with
        ``height`` and ``width``.
        ``height`` and ``width`` Search inside an axis-aligned
        rectangle, determined by the given height and width.
        Can't be given with ``radius``

        ``unit`` must be one of the following : m, km, mi, ft.
        `m` for meters (the default value), `km` for kilometers,
        `mi` for miles and `ft` for feet.

        ``sort`` indicates to return the places in a sorted way,
        ASC for nearest to furthest and DESC for furthest to nearest.

        ``count`` limit the results to the first count matching items.

        ``any`` is set to True, the command will return as soon as
        enough matches are found. Can't be provided without ``count``

        ``withdist`` indicates to return the distances of each place.
        ``withcoord`` indicates to return the latitude and longitude of
        each place.

        ``withhash`` indicates to return the geohash string of each place.

        For more information see https://redis.io/commands/geosearch
        """
    def geosearchstore(self, dest: KeyT, name: KeyT, member: Union[FieldT, None] = None, longitude: Union[float, None] = None, latitude: Union[float, None] = None, unit: str = 'm', radius: Union[float, None] = None, width: Union[float, None] = None, height: Union[float, None] = None, sort: Union[str, None] = None, count: Union[int, None] = None, any: bool = False, storedist: bool = False) -> ResponseT:
        """
        This command is like GEOSEARCH, but stores the result in
        ``dest``. By default, it stores the results in the destination
        sorted set with their geospatial information.
        if ``store_dist`` set to True, the command will stores the
        items in a sorted set populated with their distance from the
        center of the circle or box, as a floating-point number.

        For more information see https://redis.io/commands/geosearchstore
        """

    """
    Redis Module commands.
    see: https://redis.io/topics/modules-intro
    """
    def module_load(self, path, *args) -> ResponseT:
        """
        Loads the module from ``path``.
        Passes all ``*args`` to the module, during loading.
        Raises ``ModuleError`` if a module is not found at ``path``.

        For more information see https://redis.io/commands/module-load
        """
    def module_loadex(self, path: str, options: Optional[List[str]] = None, args: Optional[List[str]] = None) -> ResponseT:
        """
        Loads a module from a dynamic library at runtime with configuration directives.

        For more information see https://redis.io/commands/module-loadex
        """
    def module_unload(self, name) -> ResponseT:
        """
        Unloads the module ``name``.
        Raises ``ModuleError`` if ``name`` is not in loaded modules.

        For more information see https://redis.io/commands/module-unload
        """
    def module_list(self) -> ResponseT:
        """
        Returns a list of dictionaries containing the name and version of
        all loaded modules.

        For more information see https://redis.io/commands/module-list
        """
    def command_info(self) -> None: ...
    def command_count(self) -> ResponseT: ...
    def command_getkeys(self, *args) -> ResponseT: ...
    def command(self) -> ResponseT: ...


    """
    Class for Redis Cluster commands
    """
    def cluster(self, cluster_arg, *args, **kwargs) -> ResponseT: ...
    def readwrite(self, **kwargs) -> ResponseT:
        """
        Disables read queries for a connection to a Redis Cluster slave node.

        For more information see https://redis.io/commands/readwrite
        """
    def readonly(self, **kwargs) -> ResponseT:
        """
        Enables read queries for a connection to a Redis Cluster replica node.

        For more information see https://redis.io/commands/readonly
        """
    
    """
    Redis Function commands
    """
    def function_load(self, code: str, replace: Optional[bool] = False) -> Union[Awaitable[str], str]:
        """
        Load a library to Redis.
        :param code: the source code (must start with
        Shebang statement that provides a metadata about the library)
        :param replace: changes the behavior to overwrite the existing library
        with the new contents.
        Return the library name that was loaded.

        For more information see https://redis.io/commands/function-load
        """
    def function_delete(self, library: str) -> Union[Awaitable[str], str]:
        """
        Delete the library called ``library`` and all its functions.

        For more information see https://redis.io/commands/function-delete
        """
    def function_flush(self, mode: str = 'SYNC') -> Union[Awaitable[str], str]:
        """
        Deletes all the libraries.

        For more information see https://redis.io/commands/function-flush
        """
    def function_list(self, library: Optional[str] = '*', withcode: Optional[bool] = False) -> Union[Awaitable[List], List]:
        """
        Return information about the functions and libraries.
        :param library: pecify a pattern for matching library names
        :param withcode: cause the server to include the libraries source
         implementation in the reply
        """
    def fcall(self, function, numkeys: int, *keys_and_args: Optional[List]) -> Union[Awaitable[str], str]:
        """
        Invoke a function.

        For more information see https://redis.io/commands/fcall
        """
    def fcall_ro(self, function, numkeys: int, *keys_and_args: Optional[List]) -> Union[Awaitable[str], str]:
        """
        This is a read-only variant of the FCALL command that cannot
        execute commands that modify data.

        For more information see https://redis.io/commands/fcal_ro
        """
    def function_dump(self) -> Union[Awaitable[str], str]:
        """
        Return the serialized payload of loaded libraries.

        For more information see https://redis.io/commands/function-dump
        """
    def function_restore(self, payload: str, policy: Optional[str] = 'APPEND') -> Union[Awaitable[str], str]:
        """
        Restore libraries from the serialized ``payload``.
        You can use the optional policy argument to provide a policy
        for handling existing libraries.

        For more information see https://redis.io/commands/function-restore
        """
    def function_kill(self) -> Union[Awaitable[str], str]:
        """
        Kill a function that is currently executing.

        For more information see https://redis.io/commands/function-kill
        """
    def function_stats(self) -> Union[Awaitable[List], List]:
        """
        Return information about the function that's currently running
        and information about the available execution engines.

        For more information see https://redis.io/commands/function-stats
        """

    def tfunction_load(self, lib_code: str, replace: bool = False, config: Union[str, None] = None) -> ResponseT:
        """
        Load a new library to RedisGears.

        ``lib_code`` - the library code.
        ``config`` - a string representation of a JSON object
        that will be provided to the library on load time,
        for more information refer to
        https://github.com/RedisGears/RedisGears/blob/master/docs/function_advance_topics.md#library-configuration
        ``replace`` - an optional argument, instructs RedisGears to replace the
        function if its already exists

        For more information see https://redis.io/commands/tfunction-load/
        """
    def tfunction_delete(self, lib_name: str) -> ResponseT:
        """
        Delete a library from RedisGears.

        ``lib_name`` the library name to delete.

        For more information see https://redis.io/commands/tfunction-delete/
        """
    def tfunction_list(self, with_code: bool = False, verbose: int = 0, lib_name: Union[str, None] = None) -> ResponseT:
        """
        List the functions with additional information about each function.

        ``with_code`` Show libraries code.
        ``verbose`` output verbosity level, higher number will increase verbosity level
        ``lib_name`` specifying a library name (can be used multiple times to show multiple libraries in a single command) # noqa

        For more information see https://redis.io/commands/tfunction-list/
        """
    def tfcall(self, lib_name: str, func_name: str, keys: KeysT = None, *args: List) -> ResponseT:
        """
        Invoke a function.

        ``lib_name`` - the library name contains the function.
        ``func_name`` - the function name to run.
        ``keys`` - the keys that will be touched by the function.
        ``args`` - Additional argument to pass to the function.

        For more information see https://redis.io/commands/tfcall/
        """
    def tfcall_async(self, lib_name: str, func_name: str, keys: KeysT = None, *args: List) -> ResponseT:
        """
        Invoke an async function (coroutine).

        ``lib_name`` - the library name contains the function.
        ``func_name`` - the function name to run.
        ``keys`` - the keys that will be touched by the function.
        ``args`` - Additional argument to pass to the function.

        For more information see https://redis.io/commands/tfcall/
        """
    