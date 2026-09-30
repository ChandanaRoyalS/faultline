# A9 - write records that are not an OrderResult onto the `orders` topic, one every 10 s, 12 min.
#
# Run it inside the broker's container, fed on stdin so no quoting crosses a shell boundary (the
# A4 void run's failure mode):
#     docker exec -i kafka sh < evals/attempts/a9-orders-poison.sh
#
# Each value begins with `n` (0x6E): as a protobuf tag that is field 13 with wire type 6, which no
# message has, so both consumers' parsers refuse it on the first byte - Google.Protobuf and
# protobuf-java both raise InvalidProtocolBufferException ("invalid wire type"). The records carry
# no key. The producer is the broker's own console producer on the broker's own listener. It prints
# the clock and a count every 60 s. It ends on its own after 72 records; Ctrl-C ends it sooner.
i=0
while [ "$i" -lt 72 ]; do
  i=$((i + 1))
  echo "nonsense-order-$i"
  if [ $((i % 6)) -eq 0 ]; then echo "$(date -u +%H:%M:%S) a9: $i written" >&2; fi
  sleep 10
done | /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server kafka:9092 --topic orders
echo "$(date -u +%H:%M:%S) a9: done" >&2
