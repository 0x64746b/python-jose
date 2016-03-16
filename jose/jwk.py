
import base64
import hashlib
import hmac
import struct
import six

from builtins import int

import Crypto.Hash.SHA256
import Crypto.Hash.SHA384
import Crypto.Hash.SHA512

from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5

import ecdsa

from jose.constants import ALGORITHMS
from jose.exceptions import JWKError

# PyCryptodome's RSA module doesn't have PyCrypto's _RSAobj class
# Instead it has a class named RsaKey, which serves the same purpose.
if hasattr(RSA, '_RSAobj'):
    _RSAKey = RSA._RSAobj
else:
    _RSAKey = RSA.RsaKey


def int_arr_to_long(arr):
    return int(''.join(["%02x" % byte for byte in arr]), 16)


def base64_to_long(data):
    if isinstance(data, six.text_type):
        data = data.encode("ascii")

    # urlsafe_b64decode will happily convert b64encoded data
    _d = base64.urlsafe_b64decode(bytes(data) + b'==')
    return int_arr_to_long(struct.unpack('%sB' % len(_d), _d))


def construct(key_data, algorithm=None):
    """
    Construct a Key object for the given algorithm with the given
    key_data.
    """

    # Allow for pulling the algorithm off of the passed in jwk.
    if not algorithm and isinstance(key_data, dict):
        algorithm = key_data.get('alg', None)

    if not algorithm:
        raise JWKError('Unable to find a algorithm for key: %s' % key_data)

    if algorithm == ALGORITHMS.HS256:
        return HMACKey(key_data, HMACKey.SHA256)

    if algorithm == ALGORITHMS.HS384:
        return HMACKey(key_data, HMACKey.SHA384)

    if algorithm == ALGORITHMS.HS512:
        return HMACKey(key_data, HMACKey.SHA512)

    if algorithm == ALGORITHMS.RS256:
        return RSAKey(key_data, RSAKey.SHA256)

    if algorithm == ALGORITHMS.RS384:
        return RSAKey(key_data, RSAKey.SHA384)

    if algorithm == ALGORITHMS.RS512:
        return RSAKey(key_data, RSAKey.SHA512)

    if algorithm == ALGORITHMS.ES256:
        return ECKey(key_data, ECKey.SHA256)

    if algorithm == ALGORITHMS.ES384:
        return ECKey(key_data, ECKey.SHA384)

    if algorithm == ALGORITHMS.ES512:
        return ECKey(key_data, ECKey.SHA512)


class Key(object):
    """
    A simple interface for implementing JWK keys.
    """
    prepared_key = None
    hash_alg = None

    def process_jwk(self, jwk_dict):
        raise NotImplementedError()

    def sign(self, msg):
        raise NotImplementedError()

    def verify(self, msg, sig):
        raise NotImplementedError()


class HMACKey(Key):
    """
    Performs signing and verification operations using HMAC
    and the specified hash function.
    """
    SHA256 = hashlib.sha256
    SHA384 = hashlib.sha384
    SHA512 = hashlib.sha512
    valid_hash_algs = (SHA256, SHA384, SHA512)

    prepared_key = None
    hash_alg = None

    def __init__(self, key, hash_alg):
        if hash_alg not in self.valid_hash_algs:
            raise JWKError('hash_alg: %s is not a valid hash algorithm' % hash_alg)
        self.hash_alg = hash_alg

        if not isinstance(key, six.string_types) and not isinstance(key, bytes):
            raise JWKError('Expecting a string- or bytes-formatted key.')

        if isinstance(key, six.text_type):
            key = key.encode('utf-8')

        invalid_strings = [
            b'-----BEGIN PUBLIC KEY-----',
            b'-----BEGIN CERTIFICATE-----',
            b'ssh-rsa'
        ]

        if any([string_value in key for string_value in invalid_strings]):
            raise JWKError(
                'The specified key is an asymmetric key or x509 certificate and'
                ' should not be used as an HMAC secret.')

        self.prepared_key = key

    def sign(self, msg):
        return hmac.new(self.prepared_key, msg, self.hash_alg).digest()

    def verify(self, msg, sig):
        return sig == self.sign(msg)


class RSAKey(Key):
    """
    Performs signing and verification operations using
    RSASSA-PKCS-v1_5 and the specified hash function.
    This class requires PyCrypto package to be installed.
    This is based off of the implementation in PyJWT 0.3.2
    """

    SHA256 = Crypto.Hash.SHA256
    SHA384 = Crypto.Hash.SHA384
    SHA512 = Crypto.Hash.SHA512
    valid_hash_algs = (SHA256, SHA384, SHA512)

    prepared_key = None
    hash_alg = None

    def __init__(self, key, hash_alg):

        if hash_alg not in self.valid_hash_algs:
            raise JWKError('hash_alg: %s is not a valid hash algorithm' % hash_alg)
        self.hash_alg = hash_alg

        if isinstance(key, _RSAKey):
            self.prepared_key = key
            return

        if isinstance(key, dict):
            self.prepared_key = self.process_jwk(key)
            return

        if isinstance(key, six.string_types):
            if isinstance(key, six.text_type):
                key = key.encode('utf-8')

            try:
                self.prepared_key = RSA.importKey(key)
            except Exception as e:
                raise JWKError(e)

            return

        raise JWKError('Unable to parse an RSA_JWK from key: %s' % key)

    def process_jwk(self, jwk_dict):
        if not jwk_dict.get('kty') == 'RSA':
            raise JWKError("Incorrect key type.  Expected: 'RSA', Recieved: %s" % jwk_dict.get('kty'))

        e = base64_to_long(jwk_dict.get('e', 256))
        n = base64_to_long(jwk_dict.get('n'))

        self.prepared_key = RSA.construct((n, e))
        return self.prepared_key

    def sign(self, msg):
        try:
            return PKCS1_v1_5.new(self.prepared_key).sign(self.hash_alg.new(msg))
        except Exception as e:
            raise JWKError(e)

    def verify(self, msg, sig):
        try:
            return PKCS1_v1_5.new(self.prepared_key).verify(self.hash_alg.new(msg), sig)
        except Exception as e:
            raise JWKError(e)


class ECKey(Key):
    """
    Performs signing and verification operations using
    ECDSA and the specified hash function

    This class requires the ecdsa package to be installed.

    This is based off of the implementation in PyJWT 0.3.2
    """
    SHA256 = hashlib.sha256
    SHA384 = hashlib.sha384
    SHA512 = hashlib.sha512
    valid_hash_algs = (SHA256, SHA384, SHA512)

    prepared_key = None
    hash_alg = None

    def __init__(self, key, hash_alg):
        if hash_alg not in self.valid_hash_algs:
            raise JWKError('hash_alg: %s is not a valid hash algorithm' % hash_alg)
        self.hash_alg = hash_alg

        if isinstance(key, (ecdsa.SigningKey, ecdsa.VerifyingKey)):
            self.prepared_key = key
            return

        if isinstance(key, six.string_types):
            if isinstance(key, six.text_type):
                key = key.encode('utf-8')

            # Attempt to load key. We don't know if it's
            # a Signing Key or a Verifying Key, so we try
            # the Verifying Key first.
            try:
                key = ecdsa.VerifyingKey.from_pem(key)
            except ecdsa.der.UnexpectedDER:
                key = ecdsa.SigningKey.from_pem(key)
            except Exception as e:
                raise JWKError(e)

            self.prepared_key = key
            return

        raise JWKError('Unable to parse an ECKey from key: %s' % key)

    def sign(self, msg):
        return self.prepared_key.sign(msg, hashfunc=self.hash_alg, sigencode=ecdsa.util.sigencode_string)

    def verify(self, msg, sig):
        try:
            return self.prepared_key.verify(sig, msg, hashfunc=self.hash_alg, sigdecode=ecdsa.util.sigdecode_string)
        except:
            return False
