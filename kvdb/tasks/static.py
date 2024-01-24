ScheduleScript = """
if redis.call('EXISTS', KEYS[1]) == 0 then
    redis.call('SETEX', KEYS[1], ARGV[1], 1)
    local jobs = redis.call('ZRANGEBYSCORE', KEYS[2], 1, ARGV[2])

    if next(jobs) then
        local scores = {}
        for _, v in ipairs(jobs) do
            table.insert(scores, 0)
            table.insert(scores, v)
        end
        redis.call('ZADD', KEYS[2], unpack(scores))
        redis.call('RPUSH', KEYS[3], unpack(jobs))
    end

    return jobs
end
"""

CleanupScript = """
if redis.call('EXISTS', KEYS[1]) == 0 then
    redis.call('SETEX', KEYS[1], ARGV[1], 1)
    return redis.call('LRANGE', KEYS[2], 0, -1)
end
"""

EnqueueScript = """
if not redis.call('ZSCORE', KEYS[1], KEYS[2]) and redis.call('EXISTS', KEYS[4]) == 0 then
    redis.call('SET', KEYS[2], ARGV[1])
    redis.call('ZADD', KEYS[1], ARGV[2], KEYS[2])
    if ARGV[2] == '0' then redis.call('RPUSH', KEYS[3], KEYS[2]) end
    return 1
else
    return nil
end
"""


QueueScripts = {
    'schedule': ScheduleScript,
    'cleanup': CleanupScript,
    'enqueue': EnqueueScript,
}


class ColorMap:
    green: str = '\033[0;32m'
    red: str = '\033[0;31m'
    yellow: str = '\033[0;33m'
    blue: str = '\033[0;34m'
    magenta: str = '\033[0;35m'
    cyan: str = '\033[0;36m'
    white: str = '\033[0;37m'
    bold: str = '\033[1m'
    reset: str = '\033[0m'
