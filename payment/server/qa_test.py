# Code generated with assistance from ChatGPT (OpenAI)
# Date generated: Nov 2025
# Modified for ICT1011 Project


import requests

BASE_URL = "http://127.0.0.1:8000/rfid/deduct"

def simulate_rfid_scan(rfid_id):
    res = requests.post(BASE_URL, json={"rfid_id": rfid_id})
    print(res.json())

if __name__ == "__main__":
    simulate_rfid_scan("454269955")
