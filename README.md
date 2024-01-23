# kvdb-py
 Key-Value DB Python Client Abstraction built on top of Redis

## Overview

This library builds upon the experience of my previous library, [aiokeydb-py]() and the learnings and take-aways from maintaining it and using it in production. While `aiokeydb` supports `redispy` < 5.0, this library only supports `redispy` >= 5.0. 

The goals of this library are:

- Provide a simple abstraction over the Redis client that allows both async and sync code, and adding minor tweaks in underlying implementation to make it more performant, and dynamic.

- Provide a unified interface for interacting with various Key-Value DBs, such as Redis, Memcached, etc. Inspired by (gokv)[https://github.com/philippgille/gokv]

- Enable interacting with multiple Key-Value DBs at the same time, with the same API

- Enable usage of Key-Value DBs in the same manner as a native Python dictionary

- Provide a task queue implementation that can be used to distribute work across multiple workers.

### Why not use `redispy` directly?

`Redispy` is a great library, and this library itself is built on top of it. However, `redispy` lacks certain quality of life features that make it ready to use out of the box without having to extend the library to support these features. The implementation of `redispy` assumes that you are using either/or the async or sync client, and does not provide a unified interface for both, where in some cases, you might want to use the async client, and in some cases, you might want to use the sync client. This library provides a unified interface for both, and allows you to use both the async and sync client at the same time, with the same API.

Additionally, `kvdb` has a management client that allows you to manage multiple Key-Value DBs, as well as managing the underlying connection pools.

## Installation

```bash
pip install kvdb-py
```

