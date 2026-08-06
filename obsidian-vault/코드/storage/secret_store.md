# secret_store

`iris/storage/secret_store.py`

로컬 시크릿 암호화 — Windows DPAPI, 그 외 기기 키 XOR.

## 주요 정의

- `def _device_key`
- `def encrypt_secret`
- `def decrypt_secret`
- `def secret_fingerprint`
