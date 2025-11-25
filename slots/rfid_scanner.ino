#include <Wire.h>
#include <SPI.h>
#include <MFRC522.h>

// RFID Pins
#define SS_PIN 10
#define RST_PIN 9
MFRC522 myRFID(SS_PIN, RST_PIN);

// LED indicator
int pinLED = 2;


// Scan control
bool waitingForDone = false;

void setup() {
  Serial.begin(9600);
  SPI.begin();
  myRFID.PCD_Init();

  Serial.println("Please scan your RFID card...");
}

void loop() {
  // --- Wait for Python response ---
  if (waitingForDone) {
    if (Serial.available()) {
      String msg = Serial.readStringUntil('\n');
      msg.trim();

      // Balance update received
      if (msg.startsWith("BAL:")) {
        float balance = msg.substring(4).toFloat();

        // Resume scanning
        Serial.println("DONE");
        waitingForDone = false;
        Serial.println("Ready for next scan...");
      }
      // Done signal without balance
      else if (msg.equalsIgnoreCase("DONE")) {
        waitingForDone = false;
        Serial.println("Ready for next scan...");
      }
    }
    return;
  }

  // --- RFID scanning ---
  if (!myRFID.PICC_IsNewCardPresent()) return;
  if (!myRFID.PICC_ReadCardSerial()) return;


  // Read UID
  String content = "";
  Serial.print("USER ID tag :");
  for (byte i = 0; i < myRFID.uid.size; i++) {
    if (myRFID.uid.uidByte[i] < 0x10) Serial.print(" 0");
    else Serial.print(" ");
    Serial.print(myRFID.uid.uidByte[i], HEX);
    content.concat(String(myRFID.uid.uidByte[i] < 0x10 ? "0" : ""));
    content.concat(String(myRFID.uid.uidByte[i], HEX));
  }
  Serial.println();


  // Block further scans until Python sends "DONE"
  waitingForDone = true;
  delay(1000);
  
}
