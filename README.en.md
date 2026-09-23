# SafeNotes (Encrypted Notebook)

**Switch language / 语言切换 / Выбор языка：**
[中文](README.md) · [English](README.en.md) · [Русский](README.ru.md)

Windows desktop encrypted vault: account passwords, text notes, and images stored together in encrypted form.
A master password is required every time you open it; content is decrypted and shown in real time while running, and only ciphertext exists on disk after closing / locking.

Typical use case: a password book — record the passwords of various accounts and enter your master password to unlock and view when needed.

## Quick Start

```bash
pip install -r requirements.txt
python main.py
```

On first run a launcher selector appears; on every subsequent launch you can choose: **Unlock the last-used vault** (Enter to go straight in), **Open another vault file** (including `.bak` backups), or **Create a new vault**.

Build as a single exe:

```bash
pip install pyinstaller
build.bat        # produces dist\加密记事本.exe
```

## Security Architecture

| Stage | Implementation | Notes |
|---|---|---|
| Key derivation | **Argon2id** (256 MiB / 3 passes / 4 threads, RFC 9106 high-security direction) | Memory-hard; each attempt costs 256MB of memory + ~1s of compute, making GPU/ASIC offline brute force extremely expensive |
| Content encryption | **AES-256-GCM** | Authenticated encryption combining confidentiality and integrity; each encryption uses an independent random 96-bit nonce |
| Password verification | GCM authentication tag | The header stores a "verifier" (random 32B encrypted with the master key); decryption succeeding = password correct, **no password hash at all** |
| Downgrade protection | Entire header used as AAD | Tampering with KDF params / salt / version leads to authentication failure |
| Safe writes | Atomic write (temp file + fsync + replace) | No partial files on power loss / crash |

This combination is on the same level as KeePass / Bitwarden / 1Password and is among the strongest practical encryption available today.

### Runtime Protection

- **Idle auto-lock** (default 5 min, configurable 1–10 min or off): locking zeroes the master key and plaintext in memory
- **Automatic clipboard clearing** (default 20 s): after copying a password, it is cleared when the timer elapses (only if content has not been overwritten)
- **Anti-screenshot / anti-recording**: `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)`, so Win+Shift+S, OBS, etc. capture the window region as black
- **Error-attempt backoff**: 4–5 consecutive wrong passwords wait 30 s, ≥6 wait 5 min (against casual attempts; offline brute force is handled by Argon2id)
- Locking also clears the undo stack (which contains plaintext copies)

## Anti-Loss System (six layers)

1. **Text editing undo**: Ctrl+Z inside the input field (built into Qt)
2. **Entry-level undo / redo (50 steps)**: save / create / delete / restore are all undoable (Ctrl+Z, outside the input field)
3. **Entry history versions**: the old content is automatically snapshotted before each save (default 20 versions per entry, configurable 10/20/50), persisted across sessions and stored encrypted; the 🕘 dialog previews and restores any version with one click, with another snapshot taken before restoring — **a wrongly saved password can always be recovered**
4. **Trash**: deletions go to the trash first, reversible / permanent; (Ctrl+Z within the current session can still undo a permanent deletion)
5. **File-level rolling backups**: `.bak.1` ~ `.bak.5` rotate automatically before the first save of each session; a backup is forced before changing the master password
6. **Atomic write + GCM integrity check**

## Threat Model (honest statement)

**Can defend against**: others directly reading the file after device theft, cloud / cloud-drive sync leakage, screenshots and screen recording, clipboard residue, casual shoulder-surfing attempts, and the software itself corrupting data.

**Cannot defend against** (no software can fully defend against these):

- **Master password being known**: the master password is the only key; it cannot be recovered if lost (no backdoor), and its leak means handing over all data
- **Keyloggers / malware planted while running and unlocked**: content is already decrypted in memory
- **Memory forensics**: the Python runtime cannot guarantee complete erasure of keys and plaintext (bytes are immutable); overwriting the key bytearray on lock is best-effort
- **Offline brute force of a weak master password**: Argon2id makes each attempt very expensive, but a password that is too weak (e.g. 6 digits) can still be exhausted within a limited number of tries — please use a strong master password of 12+ characters

## File Format

```
"SNVAULT1"(8B) | version u16 | Argon2id params (t,m,p u32×3) | salt 32B
| verifier nonce12+ciphertext48 | payload nonce12 + AES-256-GCM ciphertext (JSON)
```

The payload is the JSON of the whole database: entries (fields / base64 images / history versions) and settings.
`.bak.1` ~ `.bak.5` are rolling backups with the same format and can be opened directly as a vault.

## Project Structure & Testing

```
main.py                    Entry (single instance / unlock flow / --smoke smoke test)
app/crypto/kdf.py          Argon2id derivation
app/crypto/vault.py        File format / atomic write / backup rotation / re-encrypt on password change
app/crypto/secure.py       Key holding and zeroing
app/core/models.py         Entry / history snapshot data models
app/core/database.py       In-memory store: CRUD / search / trash / history versions
app/core/undostack.py      50-step undo manager
app/core/commands.py       Business undo commands
app/core/clipboard.py      Secure copy + timed clearing
app/ui/*                   UI (unlock / three-pane main window / editor / history / generator / settings)
app/utils/strength.py      Password strength evaluation
app/utils/win32.py         Anti-screenshot
tests/                     35 unit / flow tests
```

```bash
python -m pytest tests/          # All tests
python main.py --smoke           # Headless GUI smoke test (temp vault, auto-exits in 3 s)
```

> Note: the `SAFENOTES_LOW_KDF=1` environment variable lowers the KDF to 8MB / 1 pass, only to speed up testing;
> normal startup always uses the full-strength 256MB parameters.