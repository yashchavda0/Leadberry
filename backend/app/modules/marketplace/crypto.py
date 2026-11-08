import argparse
import base64
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ...core.settings import BACKEND_ROOT, Settings
from ..identity.service import AccessError


def associated_data(org: str, account: str, version: int) -> bytes:
    return f"marketplace:{org}:{account}:credentials:{version}".encode("ascii")


def load_public_key(settings: Settings) -> rsa.RSAPublicKey:
    if settings.app_environment == "production":
        raise AccessError(503, "marketplace_managed_keys_required")
    key_path = settings.marketplace_public_key_file
    if key_path is None and settings.app_environment == "development":
        key_path = BACKEND_ROOT.parent / ".docker-secrets" / "marketplace-public.pem"
    if key_path is None:
        raise AccessError(503, "marketplace_key_not_configured")
    try:
        public = serialization.load_pem_public_key(key_path.read_bytes())
        if not isinstance(public, rsa.RSAPublicKey) or public.key_size < 3072:
            raise ValueError("Invalid wrapping key")
        return public
    except (OSError, ValueError, TypeError):
        raise AccessError(503, "marketplace_key_unavailable") from None


def encrypt_credentials(settings: Settings, values: dict[str, str], org: str, account: str, version: int) -> dict:
    public = load_public_key(settings)
    try:
        key, nonce = AESGCM.generate_key(bit_length=256), os.urandom(12)
        ciphertext = AESGCM(key).encrypt(nonce, json.dumps(values).encode(), associated_data(org, account, version))
        wrapped = public.encrypt(key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
        return {"ciphertext": base64.b64encode(ciphertext).decode(), "nonce": base64.b64encode(nonce).decode(),
                "wrapped_key": base64.b64encode(wrapped).decode(), "algorithm": "AES-256-GCM/RSA-OAEP-SHA256"}
    except (OSError, ValueError, TypeError):
        raise AccessError(503, "marketplace_key_unavailable") from None


def decrypt_credentials(private: rsa.RSAPrivateKey, envelope: dict, org: str, account: str, version: int) -> dict[str, str]:
    if envelope["algorithm"] != "AES-256-GCM/RSA-OAEP-SHA256":
        raise ValueError("Unsupported credential algorithm")
    key = private.decrypt(base64.b64decode(envelope["wrapped_key"], validate=True),
                          padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    value = AESGCM(key).decrypt(base64.b64decode(envelope["nonce"], validate=True),
                               base64.b64decode(envelope["ciphertext"], validate=True), associated_data(org, account, version))
    return json.loads(value)


def generate_keys(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    private_path, public_path = directory / "marketplace-private.pem", directory / "marketplace-public.pem"
    if private_path.exists() or public_path.exists():
        raise RuntimeError("Marketplace keys already exist; refusing to replace them")
    with private_path.open("xb") as output:
        output.write(private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
    os.chmod(private_path, 0o600)
    with public_path.open("xb") as output:
        output.write(private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    print("Development marketplace keys generated. Restrict the private key's Windows ACL to the worker identity.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate-development-keys", type=Path, required=True)
    generate_keys(parser.parse_args().generate_development_keys)