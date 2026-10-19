"""Authenticated cross-worker reuse of expensive, already-authorized calculations."""
import hashlib
import hmac
import json
import struct
import time

from stats_response_cache import StatsResponseCache


class SharedCalculations:
    def __init__(self, directory, secret, code):
        self.disk = StatsResponseCache(directory)
        self.secret = secret if isinstance(secret, bytes) else str(secret).encode()
        self.code = code

    def ticket(self, key):
        digest = hashlib.sha256(json.dumps([self.code, key], default=str, sort_keys=True).encode()).hexdigest()
        return digest, [], '[]', None

    def load(self, key):
        ticket = self.ticket(key)
        packed = self.disk.load(ticket)
        if not packed or len(packed) < 40:
            return None
        tag, body = packed[:32], packed[32:]
        expected = hmac.new(self.secret, ticket[0].encode() + body, hashlib.sha256).digest()
        # Unlike in-process pickle bytes, disk contents must be authenticated
        # before deserialization. Include the key to prevent entry substitution.
        if not hmac.compare_digest(tag, expected):
            return None
        expires = struct.unpack('!d', body[:8])[0]
        if expires <= time.time():
            return None
        return body[8:], expires

    def save(self, key, body, ttl=300):
        ticket = self.ticket(key)
        body = struct.pack('!d', time.time() + ttl) + body
        tag = hmac.new(self.secret, ticket[0].encode() + body, hashlib.sha256).digest()
        self.disk.save(ticket, tag + body)

    def clear(self):
        self.disk.clear()
