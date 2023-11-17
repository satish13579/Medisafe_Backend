from algosdk.v2client import algod
from algosdk import  mnemonic
from beaker import client, sandbox
import contract
API_KEY="LFIoc7BZFY4CAAHfCC2at53vp5ZabBio5gAQ0ntL"

def create_application():
    algod_address = "https://testnet-algorand.api.purestake.io/ps2"
    algod_token = ""
    headers = {
        "X-API-Key": API_KEY,
    }
    sender="CVPT5JBQ7RCXDVSRW7TSFJPBKRTDCOETDZE6GQKPN7NVEKDXIJWN3FKEAM"
    mnemoni="type deer chief harbor palm wagon resist uphold antenna remain sun feel soccer before napkin noodle net punch pistol polar angle daughter paddle about dwarf"
    private_key = mnemonic.to_private_key(mnemoni)

    with open("artifacts/approval.teal", "r") as f:
        approval_program = f.read()

    with open("artifacts/clear.teal", "r") as f:
        clear_program = f.read()

    acct=sandbox.SandboxAccount(address=sender,private_key=private_key)
    algod_client = algod.AlgodClient(algod_token, algod_address, headers)
    app_client = client.ApplicationClient(
        algod_client, contract.app, signer=acct.signer
    )

    app_id, app_address, _ = app_client.create()
    print(f"Deployed Application ID: {app_id} Address: {app_address}")


create_application()