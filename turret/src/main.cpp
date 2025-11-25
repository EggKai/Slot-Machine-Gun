#include <Arduino.h>
#include <Stepper.h>

const int STEPS_PER_REV = 2048; // 28BYJ-48 typical

// Motor A wiring: IN1=D8, IN2=D9, IN3=D10, IN4=D11
// NOTE: Stepper constructor pin order is (IN1, IN3, IN2, IN4)
static const uint8_t A_IN1 = 8;
static const uint8_t A_IN2 = 9;
static const uint8_t A_IN3 = 10;
static const uint8_t A_IN4 = 11;
static const int A_DIR = -1; // invert A direction to match wiring
Stepper stepperA(STEPS_PER_REV, A_IN1, A_IN3, A_IN2, A_IN4);

// Motor B wiring: IN1=D4, IN2=D5, IN3=D6, IN4=D7
// NOTE: pass as (IN1, IN3, IN2, IN4)
static const uint8_t B_IN1 = 4;
static const uint8_t B_IN2 = 5;
static const uint8_t B_IN3 = 6;
static const uint8_t B_IN4 = 7;
static const int B_DIR = 1;
Stepper stepperB(STEPS_PER_REV, B_IN1, B_IN3, B_IN2, B_IN4);

// Motor C wiring: IN1=D2, IN2=D3, IN3=D12, IN4=D13
// NOTE: pass as (IN1, IN3, IN2, IN4)
static const uint8_t C_IN1 = 2;
static const uint8_t C_IN2 = 3;
static const uint8_t C_IN3 = 12;
static const uint8_t C_IN4 = 13;
static const int C_DIR = 1;
Stepper stepperC(STEPS_PER_REV, C_IN1, C_IN3, C_IN2, C_IN4);

// Runtime control
static bool enabled = true;       // 'S' to stop, 'R' to resume
static bool demo_mode = false;    // 'DEMO ON/OFF'

// De-energize the coils to stop holding torque and heat
void releaseCoils() {
  digitalWrite(A_IN1, LOW);
  digitalWrite(A_IN2, LOW);
  digitalWrite(A_IN3, LOW);
  digitalWrite(A_IN4, LOW);
  digitalWrite(B_IN1, LOW);
  digitalWrite(B_IN2, LOW);
  digitalWrite(B_IN3, LOW);
  digitalWrite(B_IN4, LOW);
  digitalWrite(C_IN1, LOW);
  digitalWrite(C_IN2, LOW);
  digitalWrite(C_IN3, LOW);
  digitalWrite(C_IN4, LOW);
}

// Step one motor with stop check
void stepMotor(Stepper &m, long steps) {
  int dir = (steps >= 0) ? 1 : -1;
  long count = steps >= 0 ? steps : -steps;
  for (long i = 0; i < count; ++i) {
    if (!enabled) { releaseCoils(); return; }
    m.step(dir);
  }
}

// Step all motors together, optionally different counts
void stepAll(long stepsA, long stepsB, long stepsC) {
  long aStep = stepsA * A_DIR;
  long bStep = stepsB * B_DIR;
  long cStep = stepsC * C_DIR;
  long a = aStep >= 0 ? aStep : -aStep;
  long b = bStep >= 0 ? bStep : -bStep;
  long c = cStep >= 0 ? cStep : -cStep;
  int dirA = (aStep >= 0) ? 1 : -1;
  int dirB = (bStep >= 0) ? 1 : -1;
  int dirC = (cStep >= 0) ? 1 : -1;
  while (a > 0 || b > 0 || c > 0) {
    if (!enabled) { releaseCoils(); return; }
    if (a > 0) { stepperA.step(dirA); --a; }
    if (b > 0) { stepperB.step(dirB); --b; }
    if (c > 0) { stepperC.step(dirC); --c; }
  }
}

static void printHelp() {
  Serial.println(F("Commands:"));
  Serial.println(F(" HELP                - show this help"));
  Serial.println(F(" SPEED <rpm>         - set speed for all motors (RPM)"));
  Serial.println(F(" A <steps>           - step motor A by N steps"));
  Serial.println(F(" B <steps>           - step motor B by N steps"));
  Serial.println(F(" C <steps>           - step motor C by N steps"));
  Serial.println(F(" AB <a> <b>          - step A=a, B=b steps"));
  Serial.println(F(" ABC <a> <b> <c>     - step A=a, B=b, C=c steps"));
  Serial.println(F(" TARGET              - camera-aim macro: C-150, wait, C+150"));
  Serial.println(F(" S | STOP            - stop + release coils"));
  Serial.println(F(" R | RESUME          - resume motion"));
  Serial.println(F(" RELEASE             - release coils (no hold)"));
  Serial.println(F(" DEMO ON|OFF         - toggle demo sweep mode"));
}

static bool parseLong(const String &tok, long &out) {
  if (tok.length() == 0) return false;
  char buf[24]; tok.toCharArray(buf, sizeof(buf));
  char *endp = nullptr;
  long v = strtol(buf, &endp, 10);
  if (endp == buf) return false; // no digits
  out = v; return true;
}

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(25);
  // Ensure pins are outputs so releaseCoils() works immediately
  pinMode(A_IN1, OUTPUT); pinMode(A_IN2, OUTPUT); pinMode(A_IN3, OUTPUT); pinMode(A_IN4, OUTPUT);
  pinMode(B_IN1, OUTPUT); pinMode(B_IN2, OUTPUT); pinMode(B_IN3, OUTPUT); pinMode(B_IN4, OUTPUT);
  pinMode(C_IN1, OUTPUT); pinMode(C_IN2, OUTPUT); pinMode(C_IN3, OUTPUT); pinMode(C_IN4, OUTPUT);
  stepperA.setSpeed(12); // RPM start low
  stepperB.setSpeed(12);
  stepperC.setSpeed(12);
  Serial.println(F("READY ULN2003 28BYJ-48 (A:D8-11, B:D4-7, C:D2,D3,D12,D13)"));
  printHelp();
}

void loop() {
  // Handle line-based serial commands
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.length()) {
      int sp = line.indexOf(' ');
      String cmd = sp >= 0 ? line.substring(0, sp) : line;
      String rest = sp >= 0 ? line.substring(sp + 1) : String();
      cmd.toUpperCase();

      if (cmd == "HELP" || cmd == "H" || cmd == "?") {
        printHelp();
      } else if (cmd == "S" || cmd == "STOP") {
        enabled = false; releaseCoils(); Serial.println(F("OK STOP"));
      } else if (cmd == "R" || cmd == "RESUME") {
        enabled = true; Serial.println(F("OK RESUME"));
      } else if (cmd == "RELEASE") {
        releaseCoils(); Serial.println(F("OK RELEASE"));
      } else if (cmd == "SPEED") {
        long rpm; if (parseLong(rest, rpm) && rpm > 0) {
          stepperA.setSpeed((long)rpm); stepperB.setSpeed((long)rpm); stepperC.setSpeed((long)rpm);
          Serial.println(F("OK SPEED"));
        } else {
          Serial.println(F("ERR SPEED"));
        }
      } else if (cmd == "A") {
        long n; if (parseLong(rest, n)) { stepMotor(stepperA, n * A_DIR); Serial.println(F("OK A")); }
      else Serial.println(F("ERR A"));
      } else if (cmd == "B") {
        long n; if (parseLong(rest, n)) { stepMotor(stepperB, n * B_DIR); Serial.println(F("OK B")); }
      else Serial.println(F("ERR B"));
      } else if (cmd == "C") {
        long n; if (parseLong(rest, n)) { stepMotor(stepperC, n * C_DIR); Serial.println(F("OK C")); }
      else Serial.println(F("ERR C"));
      } else if (cmd == "AB") {
        rest.trim(); int sp2 = rest.indexOf(' ');
        if (sp2 >= 0) {
          String sA = rest.substring(0, sp2); String sB = rest.substring(sp2 + 1); sB.trim();
          long a, b; if (parseLong(sA, a) && parseLong(sB, b)) { stepAll(a, b, 0); Serial.println(F("OK AB")); }
          else Serial.println(F("ERR AB"));
        } else {
          Serial.println(F("ERR AB"));
        }
      } else if (cmd == "ABC") {
        rest.trim(); int sp1 = rest.indexOf(' '); int sp2 = sp1 >= 0 ? rest.indexOf(' ', sp1 + 1) : -1;
        if (sp1 >= 0 && sp2 >= 0) {
          String sA = rest.substring(0, sp1);
          String sB = rest.substring(sp1 + 1, sp2); sB.trim();
          String sC = rest.substring(sp2 + 1); sC.trim();
          long a, b, c; if (parseLong(sA, a) && parseLong(sB, b) && parseLong(sC, c)) { stepAll(a, b, c); Serial.println(F("OK ABC")); }
          else Serial.println(F("ERR ABC"));
        } else {
          Serial.println(F("ERR ABC"));
        }
      } else if (cmd == "DEMO") {
        rest.trim();
        if (rest.equalsIgnoreCase("ON") || rest == "1") { demo_mode = true; Serial.println(F("OK DEMO ON")); }
        else if (rest.equalsIgnoreCase("OFF") || rest == "0") { demo_mode = false; Serial.println(F("OK DEMO OFF")); }
        else { demo_mode = !demo_mode; Serial.println(demo_mode ? F("OK DEMO ON") : F("OK DEMO OFF")); }
      } else if (cmd == "TARGET") {
        if (!enabled) { Serial.println(F("ERR TARGET STOPPED")); }
        else {
          // Simple macro: sweep C back, pause, then return
          stepMotor(stepperC, -150);
          delay(1000);
          stepMotor(stepperC, 150);
          Serial.println(F("OK TARGET"));
        }
      } else {
        Serial.println(F("ERR UNKNOWN"));
      }
    }
  }

  if (!enabled) { delay(2); return; }

  if (demo_mode) {
    stepAll(STEPS_PER_REV, STEPS_PER_REV, STEPS_PER_REV);
    delay(250);
    stepAll(-STEPS_PER_REV, -STEPS_PER_REV, -STEPS_PER_REV);
    delay(250);
  } else {
    delay(5); // idle
  }
}
