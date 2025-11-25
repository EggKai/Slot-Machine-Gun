#include <TinyScreen.h>
#include <WiFi101.h>
#include <Wire.h>
#include <SPI.h>
#include "bitmaps.h"

// ---------------- SCREEN ----------------
TinyScreen display = TinyScreen(TinyScreenPlus);
// TinyScreenDefault Or TinyScreenPlus

// ---------------- DEVICE CONFIG ----------------
int devNum = 2; // 2, 3 or 4 for different clients

// ---------------- WIFI CONFIG ----------------
char ssid[] = "SINGTEL_GU31";
char pass[] = "UnderTheWaterfall777";
IPAddress serverIP(10, 102, 150, 117);
int port = 5000;

IPAddress localIp(10, 102, 150, devNum);
IPAddress gateway(10, 102, 150, 31);
IPAddress subnet(255, 255, 255, 0);
WiFiClient client;

// ---------------- SLOT MACHINE ----------------
int topIndex, midIndex, bottomIndex;
int targetIndex;
bool spinning = false;

// SYMBOLS
unsigned char *symbols[] = {
  lemonBitmap, cherryBitmap, cloverBitmap,
  bellBitmap, diamondBitmap, sevenBitmap
};
const int symbolOdds[] = {23, 23, 16, 16, 13, 9};
const int numSymbols = sizeof(symbols) / sizeof(symbols[0]);

// ---------------- FUNCTIONS ----------------
int getRandomSymbolIndex() {
  int roll = random(0, 100);
  int cumulative = 0;
  for (int i = 0; i < numSymbols; i++) {
    cumulative += symbolOdds[i];
    if (roll < cumulative) return i;
  }
  return numSymbols - 1;
}

void drawSlot() {
  display.drawRect(0, 0, 96, 64, TSRectangleFilled, TS_8b_Black);

  int x = (96 - ICON_W) / 2;  // centre horizontally
  int yTop = -15;             // half above screen
  int yMid = 17;              // fully visible, centred
  int yBot = 49;              // half below screen

  // Helper lambda to draw clipped portion of a bitmap
  auto drawSymbol = [&](int bmpIndex, int y) {
    int yStart = max(y, 0);
    int yEnd   = min(y + ICON_H - 1, 63);
    if (yEnd < 0 || yStart > 63) return; // fully outside

    int drawHeight = yEnd - yStart + 1;
    int srcOffset = (yStart - y) * ICON_W; // skip part of bitmap
    display.setX(x, x + ICON_W - 1);
    display.setY(yStart, yEnd);
    display.startData();
    display.writeBuffer(symbols[bmpIndex] + srcOffset, ICON_W * drawHeight);
    display.endTransfer();
  };

  drawSymbol(topIndex, yTop);
  drawSymbol(midIndex, yMid);
  drawSymbol(bottomIndex, yBot);
}


void spinSlot(int targetSymbol) {
  spinning = true;
  int maxRounds = 9 + devNum;
  int minRounds = 2 + devNum;
  bool matched = false;
  int rounds = 0;

  while (rounds < maxRounds && !matched) {
    for (int i = 0; i < 3; i++) {
      bottomIndex = midIndex;
      midIndex = topIndex;
      topIndex = getRandomSymbolIndex();
      drawSlot();
      delay(175);
      if (midIndex == targetSymbol && rounds >= minRounds) {
        matched = true;
        break;
      }
    }
    rounds++;
  }

  if (!matched) {
    bottomIndex = midIndex;
    midIndex = topIndex;
    topIndex = targetSymbol;
    drawSlot();
    delay(175);
    bottomIndex = midIndex;
    midIndex = targetSymbol;
    topIndex = getRandomSymbolIndex();
    drawSlot();
  }

  // Send all 3 slots with client ID
  uint8_t result[4] = { (uint8_t)devNum, (uint8_t)topIndex, (uint8_t)midIndex, (uint8_t)bottomIndex };
  client.write(result, 4);

  spinning = false;
}

/*
 * Flash multiple symbols simultaneously
 *
 * rows: array of symbol rows to flash (0=top,1=middle,2=bottom)
 * numRows: number of rows in the array
 * colors: array of colors to cycle through (TS_8b_ or TS_16b_ constants)
 * numColors: number of colors in the colors array
 * flashes: how many times to repeat the color cycle
 * delayMs: delay in milliseconds between color changes
 */
void flashSymbols(const int* rows, int numRows, const uint8_t* colors, int numColors, int flashes = 3, int delayMs = 150) {
  int x = (96 - ICON_W) / 2;      // perfectly centre horizontally like drawSlot()
  // Dynamic Y
  // int numSlots = 3;                     // top/middle/bottom
  // int displayHeight = display.yMax + 4; // 64 for dynamic height calculation
  // int slotHeight = displayHeight / numSlots;  // 64 / 3 = ~21
  // int yPositions[3];
  // for (int i = 0; i < numSlots; i++) {
  //   // Center each border in its slot
  //   yPositions[i] = i * slotHeight + (slotHeight - ICON_H) / 2;
  // }
  int yPositions[3] = { -15, 17, 49 }; // same vertical offsets as drawSlot()
  int borderPadding = 2;

  auto drawClippedBorder = [&](int y, uint8_t color) {
    int yStart = max(y - borderPadding, 0);
    int yEnd   = min(y + ICON_H - 1 + borderPadding, 63);
    if (yEnd < 0 || yStart > 63) return; // nothing visible

    int x0 = max(0, x - borderPadding);
    int w  = min(ICON_W + borderPadding * 2, 96 - x0);
    int h  = yEnd - yStart + 1;
    display.drawRect(x0, yStart, w, h, TSRectangleNoFill, color);
  };

  for (int f = 0; f < flashes; f++) {
    for (int c = 0; c < numColors; c++) {
      // Draw coloured borders for all flashing rows
      for (int r = 0; r < numRows; r++) {
        drawClippedBorder(yPositions[rows[r]], colors[c]);
      }

      delay(delayMs);

      // Redraw symbols (with clipping) to clear old borders
      for (int r = 0; r < numRows; r++) {
        int y = yPositions[rows[r]];
        int yStart = max(y, 0);
        int yEnd   = min(y + ICON_H - 1, 63);
        if (yEnd < 0 || yStart > 63) continue;

        int drawHeight = yEnd - yStart + 1;
        int srcOffset = (yStart - y) * ICON_W;
        display.setX(x, x + ICON_W - 1);
        display.setY(yStart, yEnd);
        display.startData();

        switch (rows[r]) {
          case 0: display.writeBuffer(symbols[topIndex] + srcOffset, ICON_W * drawHeight); break;
          case 1: display.writeBuffer(symbols[midIndex] + srcOffset, ICON_W * drawHeight); break;
          case 2: display.writeBuffer(symbols[bottomIndex] + srcOffset, ICON_W * drawHeight); break;
        }

        display.endTransfer();
      }
    }
  }

  // Redraw the whole slot reel after the flash sequence
  drawSlot();
}




// ---------------- SETUP ----------------
void setup() {
  SerialUSB.begin(9600);
  Wire.begin();
  display.begin();
  display.setFlip(true);
  randomSeed(analogRead(0));
  display.clearScreen();
  display.setFont(liberationSans_8ptFontInfo);
  display.setCursor(10, 20);
  display.print("Connecting...");

  WiFi.setPins(8, 2, A3, -1);
  WiFi.config(localIp, gateway, subnet);
  WiFi.begin(ssid, pass);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    SerialUSB.print(".");
  }

  topIndex = getRandomSymbolIndex();
  midIndex = getRandomSymbolIndex();
  bottomIndex = getRandomSymbolIndex();
  drawSlot();

  SerialUSB.println("WiFi ready.");
}

// ---------------- LOOP ----------------
void loop() {
  // Reconnect to server if disconnected
  if (!client.connected()) {
    client.stop();
    if (client.connect(serverIP, port)) {
      uint8_t hdr[2] = { 0xFD, (uint8_t)devNum };
      client.write(hdr, 2);
      SerialUSB.println("Connecting to server.");
    } else {
      SerialUSB.println("Connection to server failed.");
      return;
    }
  }

  // Handle messages from server
  if (client.available()) {
    int cmd = client.read();
    SerialUSB.println(cmd);
    if (cmd == 0xFE) {
      // handshake start
      client.write(0xFF);
      SerialUSB.println("Handshake done (sent 0xFF).");
    }
      else if (cmd == 170) {
        SerialUSB.println("Credits left: 0");
        display.clearScreen();         // clears the display
        display.setCursor(0, 0);   // reset cursor to top-left
        display.print("No Credits Left");
      }

      else if (cmd == 171) {
        SerialUSB.println("Waiting for payout credits");
        delay(2000);
        int payout = client.read();
        SerialUSB.println("Your Payout: " + String(payout));
        display.clearScreen();         // clears the display
        display.setCursor(0, 0);   // reset cursor to top-left
        display.print("You win " + String(payout) + " credits!");
        delay(2000);
      }

     else if (cmd >= 0 && cmd <= 5) {
        SerialUSB.print("Target received: ");
        SerialUSB.println(cmd);
        spinSlot(cmd);
      } else if (cmd & 0x80) {
        int rowsToFlash[3];
        int numRows = 0;
        cmd &= 0x7F; // clear high bit
        for (int i = 0; i < 3; i++) {
            if (cmd & (1 << i)) {
                rowsToFlash[numRows++] = i;
            }
        }
        if (numRows > 0) {
            uint8_t colors[] = {TS_8b_Red, TS_8b_Yellow};
            flashSymbols(rowsToFlash, numRows, colors, 2, 9, 150);
        }
      }

  }
  delay(10);
}