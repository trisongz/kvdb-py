# Pickle

Pickle is a binary serialization format that is specific to Python. It is a very powerful serialization format that can serialize almost any Python object. However, it is not recommended to use pickle to serialize and deserialize data from untrusted sources, as it can lead to security vulnerabilities.

It is only used as the default serializer for `Jobs` to ensure that the `Job` can be serialized and deserialized across different Python environments.

By default, the `pickle` serializer uses the the first available sub-library in the following order of priority:
- `cloudpickle`
- `dill`
- `pickle`

## References

- [cloudpickle](https://github.com/cloudpipe/cloudpickle)
- [dill](https://github.com/uqfoundation/dill)

---

## API Reference

::: kvdb.io.serializers._pickle.PickleSerializer
    rendering:
        show_root_heading: true
        show_source: true
        show_api_link: true
        show_inheritance: true
        show_inherited_methods: true
        show_inherited_attributes: true
        show_inherited_properties: true