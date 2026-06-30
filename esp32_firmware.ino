#include <WiFi.h>
#include <HTTPClient.h>
#include <DHT.h>
#include <Adafruit_ADXL345_U.h>
#include <ArduinoJson.h>

const char* ssid = "YOUR_SSID";
const char* password = "YOUR_PASSWORD";
const char* serverURL = "http://YOUR_SERVER_IP:8000/api/state";

#define DHT_PIN 4
#define DHT_TYPE DHT11
#define ADXL_SDA 21
#define ADXL_SCL 22

#define RELAY_PIN 25
#define COOLING_FAN_PIN 26

DHT dht(DHT_PIN, DHT_TYPE);
Adafruit_ADXL345_Unified accel = Adafruit_ADXL345_Unified(12345);

float temperature_C = 0.0;
float vib_rms_g = 0.0;
int ml_label = 0;
String ml_label_name = "NORMAL";
float ml_confidence_pct = 0.0;
bool motor_locked = false;
String last_command = "NORMAL";

unsigned long last_sensor_read = 0;
unsigned long last_server_fetch = 0;
const unsigned long SENSOR_INTERVAL = 500;
const unsigned long SERVER_INTERVAL = 2000;

const float ACCEL_X_OFFSET = 0.0;
const float ACCEL_Y_OFFSET = 0.0;
const float ACCEL_Z_OFFSET = 0.0;

void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("\n\n=== PREDIF ESP32 MOTOR FAULT DETECTION ===");
  Serial.println("Initializing sensors and connectivity...\n");
  
  pinMode(RELAY_PIN, OUTPUT);
  pinMode(COOLING_FAN_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, HIGH);
  analogWrite(COOLING_FAN_PIN, 0);
  
  dht.begin();
  Serial.println("[DHT11] Temperature sensor initialized on GPIO " + String(DHT_PIN));
  
  Wire.begin(ADXL_SDA, ADXL_SCL);
  if (!accel.begin()) {
    Serial.println("[ERROR] ADXL345 not found! Check wiring.");
    while (1) delay(10);
  }
  accel.setRange(ADXL345_RANGE_16_G);
  Serial.println("[ADXL345] Accelerometer initialized on I2C SDA=" + String(ADXL_SDA) + " SCL=" + String(ADXL_SCL));
  
  connectToWiFi();
  
  Serial.println("\n[READY] All systems initialized. Starting sensor loop...\n");
}

void loop() {
  if (millis() - last_sensor_read >= SENSOR_INTERVAL) {
    last_sensor_read = millis();
    readSensors();
    printSensorData();
  }
  
  if (millis() - last_server_fetch >= SERVER_INTERVAL) {
    last_server_fetch = millis();
    fetchServerState();
    updateActuation();
  }
  
  delay(50);
}

void readSensors() {
  temperature_C = dht.readTemperature();
  if (isnan(temperature_C)) {
    Serial.println("[DHT11 ERROR] Failed to read temperature!");
    temperature_C = 0.0;
  }
  
  sensors_event_t event;
  accel.getEvent(&event);
  
  float ax = event.acceleration.x - ACCEL_X_OFFSET;
  float ay = event.acceleration.y - ACCEL_Y_OFFSET;
  float az = event.acceleration.z - ACCEL_Z_OFFSET;
  
  vib_rms_g = sqrt((ax * ax + ay * ay + az * az) / 3.0);
  
  if (isnan(vib_rms_g)) vib_rms_g = 0.0;
  if (vib_rms_g < 0) vib_rms_g = 0.0;
}

void printSensorData() {
  Serial.print("[SENSORS] T=");
  Serial.print(temperature_C, 1);
  Serial.print("°C | Vib_RMS=");
  Serial.print(vib_rms_g, 3);
  Serial.print("g | ML_Label=");
  Serial.print(ml_label_name);
  Serial.print(" (");
  Serial.print(ml_confidence_pct, 1);
  Serial.print("%) | Motor=");
  Serial.print(motor_locked ? "LOCKED" : "RUNNING");
  Serial.print(" | Command=");
  Serial.println(last_command);
}

void connectToWiFi() {
  Serial.print("Connecting to WiFi: ");
  Serial.println(ssid);
  
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WiFi OK] Connected!");
    Serial.print("IP Address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n[WiFi ERROR] Failed to connect! Will retry...");
  }
}

void fetchServerState() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WiFi] Disconnected. Attempting reconnection...");
    connectToWiFi();
    return;
  }
  
  HTTPClient http;
  http.begin(serverURL);
  http.addHeader("Content-Type", "application/json");
  
  int httpCode = http.GET();
  
  if (httpCode == HTTP_CODE_OK) {
    String payload = http.getString();
    
    StaticJsonDocument<1024> doc;
    DeserializationError error = deserializeJson(doc, payload);
    
    if (!error) {
      ml_label = doc["ml_label"] | 0;
      ml_label_name = doc["ml_label_name"] | "UNKNOWN";
      ml_confidence_pct = doc["ml_confidence_pct"] | 0.0;
      motor_locked = doc["locked"] | false;
      last_command = doc["command_sent"] | "NORMAL";
      
      Serial.println("[SERVER] State fetched successfully.");
    } else {
      Serial.print("[JSON ERROR] ");
      Serial.println(error.c_str());
    }
  } else {
    Serial.print("[HTTP ERROR] Code: ");
    Serial.println(httpCode);
  }
  
  http.end();
}

void updateActuation() {
  if (motor_locked || ml_label == 1) {
    digitalWrite(RELAY_PIN, LOW);
    analogWrite(COOLING_FAN_PIN, 255);
    
    if (!motor_locked) {
      Serial.println("[ACTUATION] CRITICAL detected! Motor LOCKED, cooling FAN ON.");
      motor_locked = true;
    }
  }
  else {
    digitalWrite(RELAY_PIN, HIGH);
    
    int fan_pwm = (int)((temperature_C - 20.0) / 40.0 * 255);
    fan_pwm = constrain(fan_pwm, 0, 150);
    analogWrite(COOLING_FAN_PIN, fan_pwm);
    
    if (motor_locked) {
      Serial.println("[ACTUATION] Fault cleared. Motor RUNNING, cooling adjusted.");
      motor_locked = false;
    }
  }
}
