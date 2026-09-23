#!/bin/sh
# A4b — corrupt every cart in valkey-cart, twenty times a second, for twelve minutes.
#
# Run it INSIDE the valkey-cart container, fed on stdin so no quoting crosses a shell boundary:
#
#     docker exec -i valkey-cart sh < evals/attempts/a4b-corrupt-loop.sh
#
# Each iteration runs one atomic EVAL that SCANs every key and overwrites the `cart` hash field
# of every hash with four 0xFF bytes — a truncated varint that `Cart.Parser.ParseFrom` cannot
# parse. It prints the clock, the iteration and the number of keys corrupted every 200th
# iteration (about every ten seconds), so the transcript shows the loop ran and at what cadence.
# 13000 iterations at ~55 ms each is ~12 minutes; the loop then ends on its own.
#
# Why 50 ms and not 5 s: A4 (RESULT.md) measured that the load generator reads a cart back
# within milliseconds of writing it, so a sweep every five seconds lands inside a live cart's
# window a few times an hour. Fifty milliseconds is shorter than every multi-item checkout and
# most single ones; see the A4b registration for the arithmetic.

SCRIPT='
local cursor = "0"
local n = 0
repeat
  local r = redis.call("SCAN", cursor, "COUNT", 1000)
  cursor = r[1]
  for _, k in ipairs(r[2]) do
    if redis.call("TYPE", k).ok == "hash" then
      redis.call("HSET", k, "cart", "\255\255\255\255")
      n = n + 1
    end
  end
until cursor == "0"
return n
'

i=0
echo "$(date -u +%H:%M:%S) a4b loop start"
while [ "$i" -lt 13000 ]; do
  n=$(valkey-cli EVAL "$SCRIPT" 0)
  i=$((i + 1))
  if [ $((i % 200)) -eq 0 ]; then
    echo "$(date -u +%H:%M:%S) iter=$i corrupted=$n"
  fi
  sleep 0.05
done
echo "$(date -u +%H:%M:%S) a4b loop end iter=$i corrupted=$n"
