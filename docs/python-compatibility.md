# Python compatibility

DQ requires Python 3.4.10 or newer and is tested on Python 3.4.10 and Python 3.12.5. Use a maintained Python for
normal installations; the private 3.4.10 interpreter is an isolated compatibility
test installation. Python 3.0 and 3.1 are not supported.

Runtime code uses ordinary classes, `os.path`, `str.format`, and standard-library
HTTP, TLS, JSON, INI, and argument parsing. No third-party runtime packages are
required. Packaging metadata is in `setup.py`, with a minimal `pyproject.toml`.

## Private interpreter on this Mac

Location: `/Users/mbennett/.local/share/dq/python-3.4.10/bin/python3.4`

The default `python3` and shell PATH were not changed. Run from the DQ directory:

```sh
/Users/mbennett/.local/share/dq/python-3.4.10/bin/python3.4 bin/dq --version
PYTHONPATH=src /Users/mbennett/.local/share/dq/python-3.4.10/bin/python3.4 -B -m unittest discover -s tests
```

Python 3.4 dates from 2014; 3.4.10 was its final release in 2019.
[Official release](https://www.python.org/downloads/release/python-3410/).
Its old TLS dependencies are another reason to keep it for testing.

## Build notes

Built natively on Apple Silicon with Apple Clang 21 and the macOS 26.5 SDK,
using official Python 3.4.10 source and a private OpenSSL 1.0.2u installation.
Modern macOS is not supported by these old releases; this build required:

- Recognizing `arm64` in the old Python configure script.
- Using SDK copies of `stdint.h` and `Block.h` ahead of conflicting local headers,
  without modifying those local headers.
- Disabling detection of an unavailable gettext library with
  `ac_cv_header_libintl_h=no`.
- Enabling zlib explicitly in `Modules/Setup.local` with `zlib zlibmodule.c -lz`.
- Building ctypes against the SDK's system libffi instead of its bundled old libffi.
- Building private OpenSSL without assembly or shared libraries and with
  `-O0 -fno-strict-aliasing -fwrapv`. The optimized build failed elliptic-curve
  tests; the unoptimized build passed them and real HTTPS verification.
- Copying `/etc/ssl/cert.pem` into the private OpenSSL trust store. This is a
  snapshot, not an automatically updated macOS Keychain integration.
- Installing with `make altinstall` into the private prefix.

Several optional extension modules, including SQLite, curses, readline and bz2,
are unavailable in this private build. DQ does not use them. This is not intended
as a general-purpose replacement Python installation.

## Verification

- Regression tests run on Python 3.4.10 and 3.12.5.
- Live `quick_checkup` report against `my-files`: 2,011,748 documents.
- Cursor export of missing `file_name_s` IDs: 1,005,874 IDs.
- Verified HTTPS to python.org.
- Local HTTPS test: a trusted certificate and correct Basic credentials succeed;
  an untrusted certificate, mismatched hostname, and wrong password fail.
- Wheel build using setuptools 43.0.0 and wheel 0.33.6 under Python 3.4.10.

The standard-library test suite is in `tests/`. The local TLS integration check
uses the system `openssl` command to generate a temporary test certificate;
it does not enable HTTPS on the user's Solr installation.

Run the local HTTPS integration check with a modern Python:

```sh
python3 tests/check_https.py /Users/mbennett/.local/share/dq/python-3.4.10/bin/python3.4 python3
```
