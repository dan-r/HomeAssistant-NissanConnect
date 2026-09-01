"""Cross-check our SRP-6a maths against independently-derived test vectors.

These vectors are not derived from this codebase - they come from a
separate, independent reimplementation of the same protocol (see
https://github.com/TNTLarsn/HomeAssistant-NissanConnect, tests/test_srp.py).
Matching them is a strong signal that our handling of natural/minimal
byte-length BigIntegers when hashing (u = H(A|B), K = H(S)) is correct.
"""
import hashlib
from unittest.mock import patch

from custom_components.nissan_connect.kamereon.kamereon import SRP

SALT = bytes.fromhex('00010203040506070809')
PRIVATE_A = bytes(range(1, 33))
PRIVATE_B = int.from_bytes(bytes(range(33, 65)), 'big')
USER_ID = 'synthetic-user'
PIN = '1234'
ORDER = 'SYNTHETICVIN/RLU/Lock'


def _hash(*parts):
    return hashlib.sha256(b''.join(parts)).digest()


def _minimal_bytes(value):
    return value.to_bytes(max(1, (value.bit_length() + 7) // 8), 'big')


def _server_public():
    """Simulate the server side of the exchange to get a B value to test our
    client-side proof() against."""
    private_key = int.from_bytes(
        _hash(SALT, _hash(USER_ID.encode(), b':', PIN.encode())), 'big')
    verifier = pow(SRP.g, private_key, SRP.N)
    multiplier = int.from_bytes(
        _hash(_minimal_bytes(SRP.N), bytes([SRP.g])), 'big')
    value = (multiplier * verifier + pow(SRP.g, PRIVATE_B, SRP.N)) % SRP.N
    return value.to_bytes(256, 'big').hex()


def test_enrollment_vector():
    x = SRP._compute_x(SALT, USER_ID, PIN)
    verifier_hex = pow(SRP.g, x, SRP.N).to_bytes(SRP.N_BYTES, 'big').hex()

    assert len(verifier_hex) == 512
    assert hashlib.sha256(bytes.fromhex(verifier_hex)).hexdigest() == (
        '362638c4ee7f5f0639b0de5b68234ed342e148237de2a57d50c4d15d7b3fe923'
    )


def test_public_ephemeral_vector():
    with patch('custom_components.nissan_connect.kamereon.kamereon.os.urandom',
               return_value=PRIVATE_A):
        srp = SRP()
        public_ephemeral = srp.generate_a()

    assert len(public_ephemeral) == 512
    assert hashlib.sha256(bytes.fromhex(public_ephemeral)).hexdigest() == (
        '1deb90a9791476498029d9d5ef6b16021584b8f369c29140f551e502481c236e'
    )


def test_proof_vector_and_command_binding():
    with patch('custom_components.nissan_connect.kamereon.kamereon.os.urandom',
               return_value=PRIVATE_A):
        srp = SRP()
        srp.generate_a()

    server_public = _server_public()
    proof = srp.generate_proof(SALT.hex(), server_public, USER_ID, PIN, ORDER)

    assert proof == (
        '94c4d6e6b06a724c8dffda642478672957039adb2979bc0fba6d6196bbe5ece6'
    )

    with patch('custom_components.nissan_connect.kamereon.kamereon.os.urandom',
               return_value=PRIVATE_A):
        srp2 = SRP()
        srp2.generate_a()

    assert srp2.generate_proof(
        SALT.hex(), server_public, USER_ID, PIN, 'SYNTHETICVIN/RLU/Unlock',
    ) != proof


def test_minimal_bytes_strips_leading_zero_byte():
    # Just under 2^2040 has a leading 0x00 byte when padded to 256 bytes,
    # but only needs 255 bytes to represent minimally - this is the case the
    # padded-A/padded-S bug got wrong (happens for ~1/256 of random A or S
    # values).
    value = 1 << 2039
    minimal = SRP._minimal_bytes(value)
    assert minimal == value.to_bytes(255, 'big')
    assert minimal == value.to_bytes(256, 'big')[1:]  # same bytes, no pad
    assert len(minimal) == 255


def test_minimal_bytes_matches_padded_bytes_when_top_byte_set():
    value = 1 << 2047
    assert SRP._minimal_bytes(value) == value.to_bytes(256, 'big')
