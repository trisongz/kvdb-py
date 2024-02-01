# Overview

Serialization plays an important role in the `KVDB` library. It allows you to store almost any type of object when using any `set/get` methods without having to worry about serializing and deserializing prior. 

The `kvdb` library provides several default serializers and compression algorithms to choose from, and provides extensibility to add custom serializers and compression algorithms.

**Default Supported Serializers:**

- [JSON](../api/serializers/json.md)
- [MessagePack](../api/serializers/msgpack.md)
- [Pickle](../api/serializers/pickle.md)

A session can be configured to use a serializer when serializing and deserializing data in-flight. This allows you to store almost any type of object when using any `set/get` methods without having to worry about serializing and deserializing prior.

Even with `json`, almost all data types and objects can be serialized by utilizing an intelligent deterministic storing of the object's metadata on serialization and then reconstructing the object on deserialization. This is done by storing the object's type and any additional metadata required to reconstruct the object. 

Serialization has first-class support for `pydantic` models and `dataclasses`.

This can be done by passing a serializer to the `get_session()` method. 
It is currently not recommended to mix serialization with sub-dependent libraries that may do encoding and decoding prior to passing the data to KV Store, as it can lead to serialization errors.

The following is a list of the arguments that can be passed to the `get_session()` method:

*  `serializer`: The serializer to use when serializing and deserializing data. Defaults to `None`. Set to `auto`, which defaults to `json` to automatically use a serializer based on the data type. Each type supports sub-libraries which will be used if they are installed. Additionally, you can pass a custom kwarg to try to import the serializer.
  Supported serializers (and sub-libraries based on priority):
    * `json`: The JSON serializer.
      Kwarg: `jsonlib`
      - [x] `simdjson`
      - [x] `orjson`
      - [x] `ujson`
      - [x] `json`
    * `msgpack`: The MessagePack serializer.
    * `pickle`: The pickle serializer.
      Kwarg: `picklelib`
        - [x] `cloudpickle`
        - [x] `dill`
        - [x] `pickle`

* `serializer_kwargs`: The keyword arguments to pass to the serializer when serializing and deserializing data. Defaults to `None`.
* `compression`: The compression algorithm to use when compressing and decompressing data. Defaults to `None`. 
  Supported compression algorithms:
    * `zstd`
    * `lz4`
    * `gzip`
    * `zlib`
* `compression_level`: The compression level to use when compressing data. Defaults to `None`, which will use the default compression level for the compression algorithm.
* `compression_enabled`: Whether or not compression should be enabled. Defaults to `None`. If `True` and `compression` is `None`, then it will be determined based on which compression algorithms are available. If `False`, then compression will be disabled.

## Serialization Classes

The following is the base class that serializers from:

::: kvdb.io.serializers.base.BaseSerializer
    rendering:
        show_root_heading: true
        show_source: true
        show_api_link: true
        show_inheritance: true
        show_inherited_methods: true
        show_inherited_attributes: true
        show_inherited_properties: true