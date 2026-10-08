#!/bin/sh
set -eu

if [ -z "${REDIS_PASSWORD:-}" ]; then
    echo "REDIS_PASSWORD is required." >&2
    exit 1
fi

password_hash="$(
    printf '%s' "${REDIS_PASSWORD}" |
        sha256sum |
        awk '{print $1}'
)"

cat > /tmp/users.acl <<EOF
user default off
user whatsapp-platform on #${password_hash} ~* +@all
EOF

exec redis-server     --aclfile /tmp/users.acl     --protected-mode yes     --bind 0.0.0.0     --port 6379     --save ""     --appendonly no
