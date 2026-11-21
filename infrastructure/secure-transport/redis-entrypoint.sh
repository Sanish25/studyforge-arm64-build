#!/bin/sh
# Start the stock Redis image with TLS and the SCRUM-134 ACL users. Key and
# ACL material is copied so the redis user owns it with mode 0600.
set -eu

source_dir=/run/studyforge-tls-source
runtime_dir=/run/studyforge-redis
install -d -o redis -g redis -m 700 "$runtime_dir"
install -o redis -g redis -m 600 "$source_dir/redis.key" "$runtime_dir/redis.key"
install -o redis -g redis -m 644 "$source_dir/redis.crt" "$runtime_dir/redis.crt"
install -o redis -g redis -m 644 "$source_dir/ca.crt" "$runtime_dir/ca.crt"
install -o redis -g redis -m 600 /etc/studyforge/redis-users.acl "$runtime_dir/users.acl"

exec docker-entrypoint.sh redis-server /etc/studyforge/redis.conf "$@"
