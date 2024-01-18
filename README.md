# kvdb-py
 Key-Value DB Python Client Abstraction built on top of Redis

## Overview

This library builds upon the experience of my previous library, [aiokeydb-py]() and the learnings and take-aways from maintaining it. 

The goals of this library are:

- Provide a simple abstraction over the Redis client that allows both async and sync code to use the same API

- Provide a unified interface for interacting with various Key-Value DBs, such as Redis, Memcached, etc. Inspired by (gokv)[https://github.com/philippgille/gokv]

- Enable interacting with multiple Key-Value DBs at the same time, with the same API

- Enable usage of Key-Value DBs in the same manner as a native Python dictionary

- Provide a job queue implementation that can be used to distribute work across multiple workers.

