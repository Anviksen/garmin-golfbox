#!/usr/bin/env python3
"""
Kryptering for brukerdata i multi-bruker-tabellene (`users`, `user_round_state`).

Én symmetrisk nøkkel (Fernet/AES) i ENCRYPTION_KEY – ALDRI i Supabase, kun som
GitHub-secret (og lokalt i .env for provisjonering/test). Krypter creds/tokens FØR
de sendes til Supabase; dekrypter kun i minnet under kjøring. Se
supabase_multiuser_schema.sql og MULTIUSER_PLAN.md for konteksten.

Lag en nøkkel (én gang):
    python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
Legg resultatet i .env som ENCRYPTION_KEY=... og som en ny GitHub-secret med samme
navn. IKKE mist denne – uten den er alt kryptert data ulesbart for alltid.

Bruk:
    from user_crypto import encrypt, decrypt
    row = {"golfbox_password_enc": encrypt(plaintext_password)}
    ...
    plaintext_password = decrypt(row["golfbox_password_enc"])

Selvtest (ingen nettverk, ingenting postes):
    python3 user_crypto.py
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:
    pass

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:
    print("Mangler 'cryptography'. Kjør: pip install -r requirements.txt")
    raise SystemExit(1)


def is_configured() -> bool:
    return bool(os.getenv("ENCRYPTION_KEY"))


def _fernet() -> Fernet:
    key = os.getenv("ENCRYPTION_KEY")
    if not key:
        raise RuntimeError(
            "ENCRYPTION_KEY mangler. Generer én: python3 -c \"from cryptography.fernet "
            "import Fernet; print(Fernet.generate_key().decode())\" – legg den i .env "
            "og som GitHub-secret."
        )
    try:
        return Fernet(key.encode("ascii") if isinstance(key, str) else key)
    except Exception as e:
        raise RuntimeError(f"ENCRYPTION_KEY er ugyldig ({e}). Må være en Fernet-nøkkel "
                            f"generert som over.") from e


def encrypt(plaintext: str | None) -> str | None:
    """Krypter en streng til noe trygt å lagre i Supabase.

    None går gjennom uendret, så valgfrie felt (f.eks. bruker uten GolfBox-passord
    ennå) forblir NULL i databasen i stedet for en kryptert tom streng."""
    if plaintext is None:
        return None
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(ciphertext: str | None) -> str | None:
    """Dekrypter en streng lest fra Supabase. None/tom streng går gjennom uendret."""
    if not ciphertext:
        return None
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as e:
        raise RuntimeError(
            "Kunne ikke dekryptere – feil ENCRYPTION_KEY, eller data kryptert med en "
            "annen nøkkel (nøkkelrotasjon uten re-kryptering av eksisterende rader?)."
        ) from e


if __name__ == "__main__":
    # Selvtest: krypter/dekrypter noen tilfeller. Ingen nettverk, ingenting postes.
    temp_key_used = False
    if not os.getenv("ENCRYPTION_KEY"):
        temp_key_used = True
        os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()
        print("(ingen ENCRYPTION_KEY funnet – bruker en midlertidig testnøkkel, "
              "IKKE til bruk i prod)\n")

    cases = ["korrekt-hest-batteri-stift", "æøå og emoji 🏌️", ""]
    all_ok = True
    for sample in cases:
        enc = encrypt(sample)
        dec = decrypt(enc)
        ok = dec == sample
        all_ok = all_ok and ok
        print(f"  {'✅' if ok else '❌'} {sample!r} -> {'(kryptert)' if enc else enc!r} -> {dec!r}")

    # None skal gå uendret gjennom begge veier.
    ok_none = encrypt(None) is None and decrypt(None) is None
    all_ok = all_ok and ok_none
    print(f"  {'✅' if ok_none else '❌'} None -> None (begge veier)")

    print("\n✅ Alle tester OK" if all_ok else "\n❌ Noe feilet")
    if temp_key_used:
        print("Husk: dette var en midlertidig nøkkel – generer en ekte og lagre den "
              "trygt før du krypterer noe du vil beholde.")
