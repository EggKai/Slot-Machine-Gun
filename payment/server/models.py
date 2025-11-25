# Code generated with assistance from ChatGPT (OpenAI)
# Date generated: Nov 2025
# Modified for ICT1011 Project


from pydantic import BaseModel

class LoginForm(BaseModel):
    username: str
    password: str

class RFIDRequest(BaseModel):
    rfid_id: str
