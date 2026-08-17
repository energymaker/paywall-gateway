"""
A real wallet signer for the x402 client, implementing the SDK's
`ClientEvmSigner` protocol using `eth-account` (the same signing library
web3.py itself uses).

This is a REAL private key / REAL signature -- not mocked. Point it at a
funded wallet on Base mainnet (or a testnet, once you're pointed at a
facilitator that supports one) and it produces a genuinely valid,
verifiable EIP-712 signature. What makes this safe to run in a sandbox is
that it never has to touch the network itself -- signing happens locally;
only the *facilitator verification* step (in the gateway) needs network
access to actually move funds.

NEVER commit a real private key to source control. In a real deployment,
load it from an environment variable or a secrets manager, never hardcode
it (see the __main__ block below for the intended usage pattern).
"""
from eth_account import Account
from eth_account.signers.local import LocalAccount


class EthAccountSigner:
    """Wraps an eth-account LocalAccount to satisfy x402's ClientEvmSigner
    protocol: an `.address` property and a `.sign_typed_data(...)` method.
    """

    def __init__(self, private_key: str):
        self._account: LocalAccount = Account.from_key(private_key)

    @property
    def address(self) -> str:
        return self._account.address

    def sign_typed_data(self, domain, types, primary_type, message) -> bytes:
        signed = Account.sign_typed_data(
            self._account.key,
            domain_data=domain,
            message_types=types,
            message_data=message,
        )
        return signed.signature

    @classmethod
    def generate(cls) -> "EthAccountSigner":
        """Creates a brand-new random wallet -- useful for local testing,
        since it never needs to hold real funds to prove the signing flow.
        """
        acct = Account.create()
        return cls(acct.key.hex())
