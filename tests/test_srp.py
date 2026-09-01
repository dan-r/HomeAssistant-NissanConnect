import hashlib

import pytest

from custom_components.nissan_connect.kamereon.srp import (
    NissanSRPClient,
    SRP_GENERATOR,
    SRP_MODULUS,
)


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
    private_key = int.from_bytes(
        _hash(SALT, _hash(USER_ID.encode(), b':', PIN.encode())),
        'big',
    )
    verifier = pow(SRP_GENERATOR, private_key, SRP_MODULUS)
    multiplier = int.from_bytes(
        _hash(_minimal_bytes(SRP_MODULUS), bytes([SRP_GENERATOR])),
        'big',
    )
    value = (
        multiplier * verifier
        + pow(SRP_GENERATOR, PRIVATE_B, SRP_MODULUS)
    ) % SRP_MODULUS
    return value.to_bytes(256, 'big').hex()


def test_enrollment_vector():
    salt, verifier = NissanSRPClient.enroll(USER_ID, PIN, SALT)

    assert salt == SALT.hex()
    assert len(verifier) == 512
    assert hashlib.sha256(bytes.fromhex(verifier)).hexdigest() == (
        '362638c4ee7f5f0639b0de5b68234ed342e148237de2a57d50c4d15d7b3fe923'
    )


def test_public_ephemeral_vector():
    client = NissanSRPClient(PRIVATE_A)

    public_ephemeral = client.public_ephemeral()

    assert len(public_ephemeral) == 512
    assert hashlib.sha256(bytes.fromhex(public_ephemeral)).hexdigest() == (
        '1deb90a9791476498029d9d5ef6b16021584b8f369c29140f551e502481c236e'
    )


def test_proof_vector_and_command_binding():
    client = NissanSRPClient(PRIVATE_A)

    proof = client.proof(
        SALT.hex(),
        _server_public(),
        USER_ID,
        PIN,
        ORDER,
    )

    assert proof == '94c4d6e6b06a724c8dffda642478672957039adb2979bc0fba6d6196bbe5ece6'
    assert client.proof(
        SALT.hex(),
        _server_public(),
        USER_ID,
        PIN,
        'SYNTHETICVIN/RLU/Unlock',
    ) != proof


@pytest.mark.parametrize('server_public', [0, SRP_MODULUS])
def test_rejects_invalid_server_public_value(server_public):
    client = NissanSRPClient(PRIVATE_A)

    with pytest.raises(ValueError, match='Invalid SRP server public value'):
        client.proof(
            SALT.hex(),
            server_public.to_bytes(256, 'big').hex(),
            USER_ID,
            PIN,
            ORDER,
        )


@pytest.mark.parametrize('pin', ['123', '12345', '12ab'])
def test_requires_four_digit_pin(pin):
    with pytest.raises(ValueError, match='four digits'):
        NissanSRPClient.enroll(USER_ID, pin, SALT)