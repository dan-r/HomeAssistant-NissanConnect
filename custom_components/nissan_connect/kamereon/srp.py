import hashlib
import hmac
import os


SRP_MODULUS = int(
    'AC6BDB41324A9A9BF166DE5E1389582FAF72B6651987EE07FC3192943DB5605'
    '0A37329CBB4A099ED8193E0757767A13DD52312AB4B03310DCD7F48A9DA04FD5'
    '0E8083969EDB767B0CF6095179A163AB3661A05FBD5FAAAE82918A9962F0B93B'
    '855F97993EC975EEAA80D740ADBF4FF747359D041D5C33EA71D281E446B14773'
    'BCA97B43A23FB801676BD207A436C6481F1D2B9078717461A5B9D32E688F8774'
    '8544523B524B0D57D5EA77A2775D2ECFA032CFBDBF52FB3786160279004E57AE'
    '6AF874E7303CE53299CCC041C7BC308D82A5698F3A8D0C38271AE35F8E9DBFBB'
    '694B5C803D89F7AE435DE236D525F54759B65E372FCD68EF20FA7111F9E4AFF73',
    16,
)
SRP_GENERATOR = 2
SRP_MODULUS_BYTES = 256
SRP_PRIVATE_BYTES = 32
SRP_SALT_BYTES = 10


class NissanSRPClient:
    def __init__(self, private_ephemeral=None):
        if private_ephemeral is None:
            private_ephemeral = os.urandom(SRP_PRIVATE_BYTES)
        if len(private_ephemeral) != SRP_PRIVATE_BYTES:
            raise ValueError("SRP private value must be 32 bytes")

        self._private_ephemeral = int.from_bytes(private_ephemeral, 'big')
        if self._private_ephemeral == 0:
            raise ValueError("SRP private value must not be zero")
        self._public_ephemeral = pow(
            SRP_GENERATOR,
            self._private_ephemeral,
            SRP_MODULUS,
        )

    @staticmethod
    def _hash(*parts):
        digest = hashlib.sha256()
        for part in parts:
            digest.update(part)
        return digest.digest()

    @staticmethod
    def _minimal_bytes(value):
        return value.to_bytes(max(1, (value.bit_length() + 7) // 8), 'big')

    @staticmethod
    def _padded_bytes(value):
        return value.to_bytes(SRP_MODULUS_BYTES, 'big')

    @classmethod
    def _private_key(cls, salt, user_id, pin):
        inner = cls._hash(
            user_id.encode('utf-8'),
            b':',
            pin.encode('utf-8'),
        )
        return int.from_bytes(cls._hash(salt, inner), 'big')

    @staticmethod
    def _validate_pin(pin):
        if not isinstance(pin, str) or len(pin) != 4 or not pin.isdigit():
            raise ValueError("Remote lock PIN must contain four digits")

    @classmethod
    def enroll(cls, user_id, pin, salt=None):
        cls._validate_pin(pin)
        if not user_id:
            raise ValueError("SRP user ID is required")
        if salt is None:
            salt = os.urandom(SRP_SALT_BYTES)
        if len(salt) != SRP_SALT_BYTES:
            raise ValueError("SRP salt must be 10 bytes")

        private_key = cls._private_key(salt, user_id, pin)
        verifier = pow(SRP_GENERATOR, private_key, SRP_MODULUS)
        return salt.hex(), cls._padded_bytes(verifier).hex()

    def public_ephemeral(self):
        return self._padded_bytes(self._public_ephemeral).hex()

    def proof(self, salt_hex, server_public_hex, user_id, pin, order):
        self._validate_pin(pin)
        if not user_id or not order:
            raise ValueError("SRP user ID and command order are required")

        try:
            salt = bytes.fromhex(salt_hex)
            server_public_bytes = bytes.fromhex(server_public_hex)
        except ValueError as error:
            raise ValueError("Invalid SRP challenge encoding") from error
        if len(salt) != SRP_SALT_BYTES:
            raise ValueError("SRP salt must be 10 bytes")
        if len(server_public_bytes) != SRP_MODULUS_BYTES:
            raise ValueError("SRP server public value must be 256 bytes")

        server_public = int.from_bytes(server_public_bytes, 'big')
        if not 0 < server_public < SRP_MODULUS:
            raise ValueError("Invalid SRP server public value")

        modulus_bytes = self._minimal_bytes(SRP_MODULUS)
        multiplier = int.from_bytes(
            self._hash(modulus_bytes, bytes([SRP_GENERATOR])),
            'big',
        )
        scrambling = int.from_bytes(
            self._hash(
                self._minimal_bytes(self._public_ephemeral),
                server_public_bytes,
            ),
            'big',
        )
        private_key = self._private_key(salt, user_id, pin)
        verifier = pow(SRP_GENERATOR, private_key, SRP_MODULUS)
        shared_secret = pow(
            (server_public - multiplier * verifier) % SRP_MODULUS,
            self._private_ephemeral + scrambling * private_key,
            SRP_MODULUS,
        )
        session_key = self._hash(self._minimal_bytes(shared_secret))
        message = b''.join((
            self._padded_bytes(self._public_ephemeral),
            server_public_bytes,
            user_id.encode('utf-8'),
            salt,
            order.encode('utf-8'),
        ))
        return hmac.new(session_key, message, hashlib.sha256).hexdigest()

    def clear(self):
        self._private_ephemeral = None
        self._public_ephemeral = None